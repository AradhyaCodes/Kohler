"""Orchestrator: intent -> valid bundles -> ranking (+LLM) -> layout feasibility loop -> 3 alternatives."""
from typing import Dict, List, Optional

from bundles import (MIN_UTIL, budget_band, build_bundles, filter_catalog, floor_signature, inr, is_floor_item,
                     rank_bundles, shortlist, tier_candidates)
from intent import DEFAULT_BUDGET_INR, merge_intent, parse_intent_rules
from llm_agent import llm_choose, llm_extract_intent, resolve_key
from planner import Fixture, solve_layout
from sustainability import estimate_water

MAX_ATTEMPTS = 8


def _fixtures(items):
    return [Fixture(name=i["name"], w=i["width_ft"], d=i["depth_ft"],
                    clearance=i.get("clearance_front_ft", 2.0),
                    side_clearance=i.get("clearance_side_ft", 0.5),
                    category=i.get("category", "general")) for i in items if is_floor_item(i)]


def _feasible(res) -> bool:
    return bool(res) and not res["error"] and not res["violations"]


def _layout(bundle, W, L, wet, door, window, cache):
    sig = floor_signature(bundle)
    if sig in cache:
        return cache[sig]
    fx, res = _fixtures(bundle["items"]), None
    for seed in (42, 7):                       # quick screen, then a full polish
        q = solve_layout(W, L, fx, wet, door, window, generations=40, pop_size=40, seed=seed)
        if q["error"]:
            res = q
            break
        if not q["violations"]:
            full = solve_layout(W, L, fx, wet, door, window, seed=seed)
            res = full if _feasible(full) else q
            break
        res = q
    cache[sig] = res
    return res


def _power_notes(items, layout):
    wall_of = {l["name"]: l["wall"] for l in layout}
    return [f"{i['name']} needs a power point (RCD/GFCI-protected) near the {wall_of.get(i['name'], 'installation').lower()} wall."
            for i in items if i.get("requires_power")]


def _error(code, msg, **extra):
    return {"error": code, "message": msg, "alternatives": [], **extra}


def design_bathroom(prompt: str, catalog: List[dict], room_w: float, room_l: float,
                    wet_wall: str = "North", door: Optional[tuple] = None, window: Optional[tuple] = None,
                    api_key: Optional[str] = None) -> Dict:
    key = resolve_key(api_key)
    notes, errors, llm_used = [], [], False

    # 1. Understand the request (rules always; LLM as a second opinion)
    rules = parse_intent_rules(prompt)
    llm_intent = None
    if key:
        try:
            llm_intent, llm_used = llm_extract_intent(prompt, key), True
        except Exception as e:
            errors.append(f"Intent extraction: {type(e).__name__}: {e}")
    intent = merge_intent(rules, llm_intent)

    budget_assumed = intent["budget"] is None
    budget = DEFAULT_BUDGET_INR if budget_assumed else intent["budget"]

    # 2. Hard constraints in Python
    cat, n = filter_catalog(catalog, intent)
    notes += n
    bundles, n = build_bundles(cat, intent, room_w, room_l)
    notes += n
    if not bundles:
        return _error("CATALOG_INCOMPLETE", "The catalog needs at least one toilet, vanity and shower/bathtub.", intent=intent)
    fitting = [b for b in bundles if b["fits"]]
    if not fitting:
        return _error("SPATIAL_OVERFLOW", f"No set of fixtures fits a {room_w}x{room_l} ft room with the required clearances.", intent=intent)

    cheapest = min(fitting, key=lambda b: b["total"])
    if cheapest["total"] > budget:
        if budget_assumed:
            pool = [b for b in fitting if b["complete"]] or fitting   # prefer a set that includes a faucet
            cheapest = min(pool, key=lambda b: b["total"])
            notes.append(f"No budget was stated; the assumed {inr(budget)} is below the cheapest complete bundle, "
                         f"so the cheapest option ({inr(cheapest['total'])}) is shown.")
            budget = cheapest["total"]
        else:
            names = ", ".join(i["name"] for i in cheapest["items"])
            return _error("BUDGET_EXCEEDED",
                          f"Your budget of {inr(budget)} is {inr(cheapest['total'] - budget)} short. The cheapest complete "
                          f"set that fits this room is {inr(cheapest['total'])} ({names}). Raise the budget by that amount "
                          "or relax style/product preferences.", intent=intent)
    elif budget_assumed:
        notes.append(f"No budget was stated, so {inr(budget)} was assumed.")

    # Be honest when the catalog simply cannot absorb the budget (e.g. 1 crore vs a 17-item catalog),
    # instead of silently presenting a design that spends 3% of it.
    ceiling = max(b["total"] for b in fitting)
    if not budget_assumed and ceiling < MIN_UTIL * budget:
        notes.append(f"The most expensive complete set this catalog can build for this room is {inr(ceiling)}, "
                     f"well under your {inr(budget)} budget. The remainder is best allocated to tiling, lighting, "
                     "ventilation, labour and installation, which this tool does not price.")

    ranked = rank_bundles(fitting, intent, budget, budget_assumed)

    # 3. LLM picks the aesthetic winner among pre-validated bundles that also use the budget sensibly
    first, narrative, short = None, None, shortlist(budget_band(ranked, budget, budget_assumed))
    if key:
        try:
            oid, narrative = llm_choose(prompt, short, budget, budget_assumed, room_w, room_l, key)
            first, llm_used = short[oid], True
        except Exception as e:
            errors.append(f"Selection: {type(e).__name__}: {e}")
    best_cands = ([first] + [b for b in ranked if b is not first]) if first else ranked
    tiers = tier_candidates(ranked)

    # 4. Only accept bundles whose layout is actually feasible
    cache, used = {}, set()

    def first_feasible(cands, cond=lambda b: True):
        tries, last = 0, None
        for b in cands:
            if not cond(b) or floor_signature(b) in used:
                continue
            if tries >= MAX_ATTEMPTS:
                break
            tries += 1
            res = _layout(b, room_w, room_l, wet_wall, door, window, cache)
            if _feasible(res):
                used.add(floor_signature(b))
                return b, res, last
            last = (b, res)
        return None, None, last

    best, best_res, last = first_feasible(best_cands)
    if not best:
        detail = ""
        if last and last[1]:
            detail = " Issues: " + "; ".join(last[1].get("violations") or [last[1].get("message", "")])
        return _error("NO_FEASIBLE_LAYOUT",
                      "None of the affordable bundles could be laid out cleanly in this room with the chosen door, window "
                      "and wet wall. Try a larger room, a different door position, or a different wet wall." + detail,
                      intent=intent, notes=notes)

    picks = [("Best style match", best, best_res)]
    v, vr, _ = first_feasible(tiers["value"], lambda b: b["total"] < best["total"])
    if v:
        picks.append(("Lower-cost option", v, vr))
    p, pr, _ = first_feasible(tiers["premium"], lambda b: b["total"] > best["total"])
    if p:
        picks.append(("Premium option", p, pr))

    # 5. Assemble alternatives (facts by Python, only the narrative comes from the LLM)
    alts = []
    for label, b, res in picks:
        total = b["total"]
        used_pct = (100.0 * total / budget) if budget else 0.0
        if label == "Best style match":
            story = narrative or ("Selected for the closest match to the requested style"
                                  + (f" ({'/'.join(intent['styles'])})" if intent["styles"] else "")
                                  + " with compact, well-proportioned fixtures.")
            if budget_assumed:
                story += f" Bundle total {inr(total)}."
            else:
                story += (f" Bundle total {inr(total)} - {used_pct:.0f}% of your {inr(budget)} budget, "
                          f"leaving {inr(budget - total)} unallocated.")
        elif label == "Lower-cost option":
            story = f"Same room and constraints for {inr(best['total'] - total)} less than the top pick."
        else:
            story = f"Higher-end fixtures for {inr(total - best['total'])} more, still within budget."
        alts.append({"tier": label, "items": b["items"], "total": total, "layout": res["layout"],
                     "violations": res["violations"], "rationale": story,
                     "remaining": (budget - total) if not budget_assumed else None,
                     "used_pct": used_pct,
                     "power_notes": _power_notes(b["items"], res["layout"]),
                     "water": estimate_water(b["items"])})

    return {"error": None, "intent": intent, "budget": budget, "budget_assumed": budget_assumed,
            "alternatives": alts, "notes": notes, "llm_error": " | ".join(errors) or None,
            "source": "llm" if llm_used else "rule-based"}