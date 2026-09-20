"""Rough household water-use estimate per bundle.

Uses per-product fields when present in catalog.json (flush_volume_l, flow_rate_lpm,
tub_capacity_l); otherwise falls back to clearly-labelled ASSUMED typical values.
"""
from typing import Dict, List

ASSUMPTIONS = {"people": 4, "flushes_per_person_day": 5, "shower_min_per_person_day": 7,
               "basin_min_per_person_day": 2, "tub_fills_per_week": 2}
DEFAULTS = {"flush_volume_l": 4.5, "shower_flow_lpm": 9.0, "faucet_flow_lpm": 6.0, "tub_capacity_l": 150.0}


def estimate_water(items: List[dict]) -> Dict:
    a, used_default = ASSUMPTIONS, False
    cats = {i["category"].lower(): i for i in items}
    parts = {}

    def spec(item, field, default):
        nonlocal used_default
        if item and item.get(field) is not None:
            return float(item[field])
        used_default = True
        return default

    toilet = next((i for i in items if "toilet" in i["category"].lower()), None)
    shower = next((i for i in items if "shower" in i["category"].lower()), None)
    tub = cats.get("bathtub")
    faucet = cats.get("faucet")
    if toilet:
        parts["Toilet"] = a["people"] * a["flushes_per_person_day"] * 365 * spec(toilet, "flush_volume_l", DEFAULTS["flush_volume_l"])
    if shower:
        parts["Shower"] = a["people"] * a["shower_min_per_person_day"] * 365 * spec(shower, "flow_rate_lpm", DEFAULTS["shower_flow_lpm"])
    if tub:
        parts["Bathtub"] = a["tub_fills_per_week"] * 52 * spec(tub, "tub_capacity_l", DEFAULTS["tub_capacity_l"])
    parts["Basin tap"] = a["people"] * a["basin_min_per_person_day"] * 365 * spec(faucet, "flow_rate_lpm", DEFAULTS["faucet_flow_lpm"])
    return {"annual_litres": round(sum(parts.values())), "breakdown": {k: round(v) for k, v in parts.items()},
            "uses_defaults": used_default,
            "note": f"Estimate for a household of {a['people']}; assumes typical usage. "
                    + ("Some values are assumed defaults - add flush_volume_l / flow_rate_lpm / tub_capacity_l "
                       "to catalog.json for exact figures." if used_default else "Uses catalog specifications.")}
