"""Catalog -> valid product bundles (budget, room fit, user constraints) and ranking."""
from itertools import product
from typing import Dict, List, Optional, Tuple

INTENT_CAT = {"toilet": "toilet", "smart toilet": "toilet", "vanity": "vanity", "basin": "basin",
              "sink": "basin", "shower": "shower", "shower enclosure": "shower",
              "bathtub": "bathtub", "faucet": "faucet"}
NON_FLOOR = {"basin", "faucet"}   # mounted on the vanity: no floor footprint

# A stated budget is a target, not just a ceiling: spending 14% of it is a worse
# answer than a slightly weaker style match that actually uses the money.
TARGET_UTIL = 0.92    # aim to land near 92% of budget, leaving a little headroom
MIN_UTIL = 0.65       # bundles below this are under-spending; shown only as the "lower-cost" tier
UTIL_WEIGHT = 0.6     # how strongly utilisation competes with the style ratio


def inr(v: float) -> str:
    s = str(int(round(v)))
    if len(s) <= 3:
        return "₹" + s
    head, tail, parts = s[:-3], s[-3:], []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return "₹" + ",".join(parts + [tail])


def icat(item: dict) -> str:
    return INTENT_CAT.get(item.get("category", "").lower(), item.get("category", "").lower())


def is_floor_item(item: dict) -> bool:
    return icat(item) not in NON_FLOOR


def fits_room(items: List[dict], room_w: Optional[float], room_l: Optional[float]) -> bool:
    if not room_w or not room_l:
        return True
    floor = [i for i in items if is_floor_item(i)]
    used = sum(i["width_ft"] * (i["depth_ft"] + i.get("clearance_front_ft", 2.0)) for i in floor)
    return used <= 0.6 * room_w * room_l and all(i["width_ft"] <= max(room_w, room_l) for i in floor)


def _hits(items: List[dict], terms: List[str]) -> int:
    return sum(1 for i in items if any(t in i.get("style", "").lower() for t in terms))


def filter_catalog(catalog: List[dict], intent: Dict) -> Tuple[List[dict], List[str]]:
    notes = []
    exclude = set(intent.get("exclude", []))
    if exclude & {"toilet", "vanity"}:
        notes.append("Toilet and vanity are always part of a bundle; that exclusion was ignored.")
    cat = [i for i in catalog if icat(i) not in (exclude - {"toilet", "vanity"})]

    avoid = intent.get("avoid_styles", [])
    if avoid:
        kept = [i for i in cat if not _hits([i], avoid)]
        groups = {icat(i) for i in kept}
        if {"toilet", "vanity"} <= groups and groups & {"shower", "bathtub"}:
            cat = kept
            notes.append(f"Excluded products in the {'/'.join(avoid)} style, as requested.")
        else:
            notes.append(f"Could not fully avoid the {'/'.join(avoid)} style with this catalog; ranked lower instead.")
    return cat, notes


def build_bundles(catalog: List[dict], intent: Dict, room_w=None, room_l=None) -> Tuple[List[dict], List[str]]:
    notes = []
    by = lambda c: [i for i in catalog if icat(i) == c]
    toilets, vanities, showers, tubs = by("toilet"), by("vanity"), by("shower"), by("bathtub")
    basins, faucets = by("basin"), by("faucet")
    must = set(intent.get("must_have", []))

    if "bathtub" in must and "shower" in must and showers and tubs:
        wet_opts = [[s, t] for s in showers for t in tubs]
    elif "bathtub" in must and tubs:
        wet_opts = [[t] for t in tubs]
    elif "shower" in must and showers:
        wet_opts = [[s] for s in showers]
    else:
        wet_opts = [[w] for w in showers + tubs]
        if must & {"bathtub", "shower"}:
            notes.append("Requested shower/bathtub type is unavailable after filtering; showing all options.")

    if not (toilets and vanities and wet_opts):
        return [], notes

    basin_opts = [b for b in basins] if "basin" in must and basins else [None] + basins
    faucet_opts = list(faucets) if "faucet" in must and faucets else [None] + faucets
    wants_faucet = bool(faucets)

    out = []
    for t, v, w, b, f in product(toilets, vanities, wet_opts, basin_opts, faucet_opts):
        items = [t, v, *w] + [x for x in (b, f) if x]
        out.append({"items": items, "total": sum(i["price_inr"] for i in items),
                    "fits": fits_room(items, room_w, room_l),
                    "complete": (f is not None) or not wants_faucet})
    return out, notes


def budget_fit(total: float, budget: Optional[float], use_budget: bool = True) -> float:
    """1.0 when the bundle spends ~TARGET_UTIL of a stated budget, falling off either side."""
    if not use_budget or not budget or budget <= 0 or budget == float("inf"):
        return 0.0
    return max(0.0, 1.0 - abs(total / budget - TARGET_UTIL) / TARGET_UTIL)


def rank_bundles(bundles: List[dict], intent: Dict, budget: float, budget_assumed: bool = False) -> List[dict]:
    """Rank by style match AND budget utilisation. An assumed budget is a ceiling only,
    so utilisation is ignored there and the cheapest option wins ties as before."""
    valid = [b for b in bundles if b["fits"] and b["total"] <= budget]
    styles, avoid = intent.get("styles", []), intent.get("avoid_styles", [])
    use_budget = not budget_assumed
    for b in valid:
        n = len(b["items"])
        b["ratio"] = (_hits(b["items"], styles) / n if styles else 0.0) - 2 * (_hits(b["items"], avoid) / n if avoid else 0.0)
        b["util"] = (b["total"] / budget) if (budget and budget != float("inf")) else 0.0
        b["fit"] = budget_fit(b["total"], budget, use_budget)
        b["score"] = b["ratio"] + UTIL_WEIGHT * b["fit"]
    # tie-break: spend more of a stated budget, spend less of an assumed one
    return sorted(valid, key=lambda b: (not b["complete"], -b["score"],
                                        -b["total"] if use_budget else b["total"]))


def budget_band(ranked: List[dict], budget: Optional[float], budget_assumed: bool, min_n: int = 3) -> List[dict]:
    """Bundles that use a sensible share of a stated budget - what the LLM is allowed to choose from,
    so an aesthetic pick cannot quietly under-spend by lakhs. Falls back to everything if too few."""
    if budget_assumed or not budget or budget == float("inf"):
        return ranked
    band = [b for b in ranked if b["total"] >= MIN_UTIL * budget]
    return band if len(band) >= min_n else ranked


def shortlist(ranked: List[dict], n: int = 25) -> List[dict]:
    if len(ranked) <= n:
        return ranked
    head, rest, k = ranked[:10], ranked[10:], n - 10
    step = len(rest) / k
    return head + [rest[int(i * step)] for i in range(k)]


def tier_candidates(ranked: List[dict]) -> Dict[str, List[dict]]:
    top = max((b["ratio"] for b in ranked), default=0.0)
    thr = top / 2 if top > 0 else 0.0
    value = sorted([b for b in ranked if b["ratio"] >= thr], key=lambda b: (not b["complete"], b["total"]))
    prem_pool = [b for b in ranked if b["ratio"] >= top and b["complete"]] or ranked
    premium = sorted(prem_pool, key=lambda b: -b["total"])
    return {"value": value, "premium": premium}


def floor_signature(bundle: dict) -> tuple:
    return tuple(sorted(i["sku"] for i in bundle["items"] if is_floor_item(i)))