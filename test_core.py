import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.dont_write_bytecode = True

import pytest

import llm_agent
from bundles import inr, is_floor_item
from designer import design_bathroom
from intent import extract_budget, find_budget, merge_intent, normalize_llm_intent, parse_intent_rules
from spatial_optimizer import overlap_area

CATALOG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "catalog.json"), encoding="utf-8"))
DOOR, WINDOW = ("West", 1.0, 2.5), ("East", 3.0)


def run(prompt, W=13, L=11, wet="North", key=None):
    return design_bathroom(prompt, CATALOG, W, L, wet, DOOR, WINDOW, api_key=key)


@pytest.fixture(autouse=True)
def no_env_keys(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "api_key"):
        monkeypatch.delenv(k, raising=False)


# ---- intent parsing ----
@pytest.mark.parametrize("text,expected", [
    ("I have a budget of 2,00,000", 200000), ("13x11 bathroom, budget 2 lakh", 200000),
    ("under Rs 50k", 50000), ("Rs. 1.5 lakh", 150000), ("budget for a 13x11 bathroom", None),
    ("just make it nice", None)])
def test_budget(text, expected):
    assert find_budget(text) == expected
    assert extract_budget(text) == (expected if expected else float("inf"))


def test_negation_and_musts():
    r = parse_intent_rules("Not modern please, no faucet, I want a bathtub")
    assert "modern" in r["avoid_styles"] and "modern" not in r["styles"]
    assert "faucet" in r["exclude"] and "bathtub" in r["must_have"]


def test_shower_only():
    r = parse_intent_rules("walk-in shower only")
    assert "shower" in r["must_have"] and "bathtub" in r["exclude"]


def test_llm_output_is_sanitised():
    n = normalize_llm_intent({"budget_inr": "12", "styles": ["Zen", "hacker"], "must_have": ["tub", "toilet"], "exclude": ["tap"]})
    assert n["budget"] is None and n["styles"] == ["zen"] and n["must_have"] == ["bathtub"] and n["exclude"] == ["faucet"]


# ---- design invariants ----
def _no_overlaps(layout):
    boxes = [(l["x"], l["y"], l["x"] + l["w"], l["y"] + l["h"]) for l in layout]
    return all(overlap_area(boxes[i], boxes[j]) == 0 for i in range(len(boxes)) for j in range(i + 1, len(boxes)))


def test_budget_never_exceeded_and_layouts_clean():
    r = run("budget of 2,00,000 modern bathroom")
    assert r["error"] is None and r["alternatives"]
    for a in r["alternatives"]:
        assert a["total"] <= 200000
        assert a["violations"] == [] and _no_overlaps(a["layout"])
        assert a["total"] == sum(i["price_inr"] for i in a["items"])


def test_alternatives_are_ordered_by_price_role():
    r = run("budget of 4 lakh modern")
    tiers = {a["tier"]: a["total"] for a in r["alternatives"]}
    best = tiers["Best style match"]
    if "Lower-cost option" in tiers:
        assert tiers["Lower-cost option"] < best
    if "Premium option" in tiers:
        assert tiers["Premium option"] > best


def test_top_pick_actually_uses_a_stated_budget():
    """Regression: a 12-lakh budget used to return a 1.7-lakh 'best match' (14% of budget)."""
    for prompt, budget in [("budget 12 lakh luxury", 1200000), ("budget of 2,00,000 modern bathroom", 200000)]:
        r = run(prompt)
        assert r["error"] is None
        best = next(a for a in r["alternatives"] if a["tier"] == "Best style match")
        assert best["total"] <= budget                      # never over
        assert best["total"] >= 0.65 * budget, (            # and never absurdly under
            f"{prompt}: top pick uses only {100 * best['total'] / budget:.0f}% of the budget")
        assert abs(best["remaining"] - (budget - best["total"])) < 1


def test_assumed_budget_still_prefers_cheaper():
    r = run("modern bathroom")
    best = next(a for a in r["alternatives"] if a["tier"] == "Best style match")
    assert r["budget_assumed"] and best["remaining"] is None


def test_budget_shortfall_message():
    r = run("budget 50k")
    assert r["error"] == "BUDGET_EXCEEDED" and "short" in r["message"]


def test_default_budget_too_low_shows_cheapest():
    r = run("modern bathroom")
    assert r["error"] is None and r["budget_assumed"]
    assert any("assumed" in n for n in r["notes"])


def test_tiny_room_errors():
    assert run("budget 5 lakh", W=5, L=5)["error"] in ("SPATIAL_OVERFLOW", "NO_FEASIBLE_LAYOUT")


def test_must_have_and_exclusions_enforced():
    r = run("budget 5 lakh, I want a bathtub, no faucet")
    assert r["error"] is None
    for a in r["alternatives"]:
        cats = {i["category"] for i in a["items"]}
        assert "bathtub" in cats and "faucet" not in cats


def test_avoid_style_enforced():
    r = run("budget 5 lakh, not modern")
    for a in r["alternatives"]:
        assert all("modern" not in i["style"].lower() for i in a["items"])


# ---- LLM path with a fake model ----
def test_llm_path_verified_by_python(monkeypatch):
    def fake(system, user, key):
        if "structured constraints" in system:
            return '{"budget_inr": null, "styles": ["zen"], "avoid_styles": [], "must_have": [], "exclude": []}'
        return '{"option_id": 0, "design_rationale": "A calm, cohesive set costing Rs 5000 only."}'
    monkeypatch.setattr(llm_agent, "_complete", fake)
    r = run("budget 3 lakh, calm bathroom", key="k")
    assert r["source"] == "llm" and r["error"] is None
    assert "zen" in r["intent"]["styles"]
    assert "Rs 5000" not in r["alternatives"][0]["rationale"]      # unverified money figure rejected


def test_llm_failure_falls_back(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(llm_agent, "_complete", boom)
    r = run("budget 3 lakh modern", key="k")
    assert r["error"] is None and r["llm_error"] and r["source"] == "rule-based"


def test_inr_format():
    assert inr(200000) == "₹2,00,000" and inr(1618000) == "₹16,18,000" and inr(500) == "₹500"