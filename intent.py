"""Rule-based understanding of the customer prompt (works offline, and validates LLM output).

Extracts: budget, wanted styles, avoided styles (with negation: "not modern"),
must-have products ("I want a bathtub") and exclusions ("no faucet", "shower only").
"""
import re
from typing import Dict, List, Optional

DEFAULT_BUDGET_INR = 100000.0

STYLE_KEYWORDS = {"minimal": "minimalist", "modern": "modern", "luxur": "luxury",
                  "classic": "classic", "zen": "zen", "japanese": "zen"}
STYLE_VOCAB = ("minimalist", "modern", "luxury", "classic", "zen")

CATEGORY_PATTERNS = {
    "bathtub": r"\b(?:bath\s?tub|tub)\b",
    "shower": r"\bshower\b",
    "toilet": r"\b(?:toilet|wc|commode)\b",
    "vanity": r"\bvanity\b",
    "basin": r"\b(?:basin|sink)\b",
    "faucet": r"\b(?:faucets?|taps?)\b",
}
CATEGORY_VOCAB = tuple(CATEGORY_PATTERNS)
CATEGORY_SYNONYMS = {"tub": "bathtub", "bath": "bathtub", "tap": "faucet", "sink": "basin",
                     "shower enclosure": "shower", "smart toilet": "toilet", "wc": "toilet"}

_NEG = re.compile(r"\b(?:no|not|non|avoid|without|except|exclude|hate|dislike|skip|"
                  r"don'?t\s+want|do\s+not\s+want)\b(?:\s+\w+){0,2}\s*$", re.I)

_UNITS = {"k": 1e3, "l": 1e5, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
          "cr": 1e7, "crore": 1e7, "crores": 1e7}
_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"(?:\s*(k|lakhs?|lacs?|l|crores?|cr)\b)?"
_NOT_DIM = r"(?!\s*(?:x|×|ft\b|feet|sq|by\b|mm|cm|m\b|'))"


def _negated(text: str, pos: int) -> bool:
    return bool(_NEG.search(text[max(0, pos - 35):pos]))


def find_budget(prompt: str) -> Optional[float]:
    """'budget of 2,00,000', 'under 2 lakh', 'Rs 50k', '₹1.5 lakh' -> rupees. None if absent."""
    t = prompt.replace(",", "")
    patterns = [
        r"(?:budget|within|under|upto|up to|maximum|max|limit)\D{0,25}?" + _NUM + _UNIT + _NOT_DIM,
        r"(?:\brs\.?|\binr\b|₹)\s*" + _NUM + _UNIT + _NOT_DIM,
        _NUM + r"\s*(k|lakhs?|lacs?|crores?|cr)\b",
    ]
    for p in patterns:
        for m in re.finditer(p, t, re.IGNORECASE):
            unit = (m.group(2) or "").lower()
            if unit == "l" and float(m.group(1)) > 100:
                continue              # "500 l" is a tank, not 5 crore
            if t[max(0, m.start(1) - 1):m.start(1)] == "-":
                continue              # a negative budget is not a budget
            val = float(m.group(1)) * _UNITS.get(unit, 1)
            if val >= 1000:  # ignore "13" from "13x11 ft"
                return val
    return None


def extract_budget(prompt: str) -> float:
    b = find_budget(prompt)
    return float("inf") if b is None else b


def parse_intent_rules(prompt: str) -> Dict:
    text = prompt.lower()
    styles, avoid, must, exclude = set(), set(), set(), set()
    for kw, canon in STYLE_KEYWORDS.items():
        for m in re.finditer(r"\b" + kw, text):
            (avoid if _negated(text, m.start()) else styles).add(canon)
    for cat, pat in CATEGORY_PATTERNS.items():
        for m in re.finditer(pat, text):
            (exclude if _negated(text, m.start()) else must).add(cat)
    for m in re.finditer(r"\b(shower|tub|bathtub)\s+only\b|\bonly\s+(?:an?\s+)?(shower|tub|bathtub)\b", text):
        keep = "shower" if "shower" in (m.group(1) or m.group(2)) else "bathtub"
        other = "bathtub" if keep == "shower" else "shower"
        must.add(keep)
        must.discard(other)
        exclude.add(other)
    must -= exclude
    must -= {"toilet", "vanity"}          # always part of a bundle
    styles -= avoid
    return {"budget": find_budget(prompt), "styles": sorted(styles), "avoid_styles": sorted(avoid),
            "must_have": sorted(must), "exclude": sorted(exclude)}


def normalize_llm_intent(raw: dict) -> Dict:
    """Never trust LLM output: coerce to the known vocabulary and sane ranges."""
    def cats(v):
        out = []
        for x in (v or []):
            x = CATEGORY_SYNONYMS.get(str(x).strip().lower(), str(x).strip().lower())
            if x in CATEGORY_VOCAB and x not in out:
                out.append(x)
        return out

    def styles(v):
        out = []
        for x in (v or []):
            x = str(x).strip().lower()
            x = {"minimal": "minimalist", "luxurious": "luxury", "japanese": "zen"}.get(x, x)
            if x in STYLE_VOCAB and x not in out:
                out.append(x)
        return out

    budget = raw.get("budget_inr")
    try:
        budget = float(budget)
        budget = budget if 1000 <= budget <= 1e9 else None
    except (TypeError, ValueError):
        budget = None
    return {"budget": budget, "styles": styles(raw.get("styles")),
            "avoid_styles": styles(raw.get("avoid_styles")),
            "must_have": [c for c in cats(raw.get("must_have")) if c not in ("toilet", "vanity")],
            "exclude": cats(raw.get("exclude"))}


def merge_intent(rules: Dict, llm: Optional[Dict] = None) -> Dict:
    llm = llm or {}
    out = {"budget": rules["budget"] if rules["budget"] is not None else llm.get("budget")}
    for k in ("styles", "avoid_styles", "must_have", "exclude"):
        out[k] = sorted(set(rules[k]) | set(llm.get(k, [])))
    out["styles"] = [s for s in out["styles"] if s not in out["avoid_styles"]]
    out["must_have"] = [m for m in out["must_have"] if m not in out["exclude"]]
    return out