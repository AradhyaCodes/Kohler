# KOHLER AI Bathroom Designer & Planner

**Track 1 — KOHLER–MITWPU AI Research Lab Program**

Turns a customer request + room constraints into **three feasible, priced bathroom designs** with a 2D plan and an interactive 3D view.

> "I have a budget of 4.5L for a 9x7 ft bathroom. Japanese Zen, definitely not modern.
> Walk-in shower only, no bathtub." → three costed designs, each proven to fit the room.

## How it works
1. **Understand** — rule-based parser (budget incl. lakh/L/k, styles, negation like "not modern", must-haves, "shower only") + optional LLM extraction. LLM output is validated against a fixed vocabulary.
2. **Constrain (Python, deterministic)** — enumerate bundles from `catalog.json`; drop anything over budget or too big for the room, before any model sees them.
3. **Rank on style *and* budget use** — a stated budget is a target, not just a ceiling. `score = style_ratio + 0.6 × budget_fit`, where `budget_fit` peaks at ~92% utilisation. A ₹12 lakh brief returns a ₹11.7 lakh design, not a ₹1.7 lakh one. An *assumed* budget stays a ceiling only.
4. **Choose (LLM, optional)** — picks the best-looking bundle from a shortlist of already-valid ones inside the budget band, and writes the narrative. Prices/totals are written by Python; narratives containing money figures are rejected.
5. **Prove it fits** — a genetic algorithm lays out each candidate (door swing, window, wet wall, toilet sightline, clearances). A bundle is only shown if its layout has zero violations; otherwise the next candidate is tried.
6. **Present** — Best style match / Lower-cost / Premium, with SVG plan, 3D view, BOM CSV, power-point notes, budget utilisation and an estimated annual water-use figure.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env        # optional: add OPENROUTER_API_KEY or GEMINI_API_KEY
streamlit run app.py
```
No key = rule-based mode (fully functional). Set `LLM_MODEL` to override the litellm model string.
On Streamlit Cloud put keys in `st.secrets` instead of `.env`.

### Try this
Room **9 × 7 ft**, door **West @ 0.5 ft (2 ft wide)**, window **North**, wet wall **East**:

```
I have a budget of 4.5L for a 9x7 ft bathroom. Japanese Zen, definitely not modern
and not classic. Walk-in shower only, no bathtub, and I don't want a separate faucet.
```

Change the budget to `1.4L` to see the graceful failure path.

## Tests
```bash
pip install -r requirements-dev.txt
pytest
```
21 tests covering budget parsing, negation, LLM output sanitisation, budget-utilisation bounds, layout invariants and both failure paths.

**Verification sweep:** 96 runs (16 prompts × 6 room geometries) producing 218 designs — zero fixture overlaps, zero out-of-bounds placements, zero blocked clearances, zero budget overruns. 37 distinct bundles, with all 17 catalog items recommended at least once.

## Submission documents
| File | Contents |
|---|---|
| `docs/PROMPTS.pdf` | All system prompts verbatim, prompt-engineering rationale, guardrail table, model routing, development workflow |
| `docs/DECK.pdf` | 4-slide deck — approach, architecture, tech stack, innovation pitch |
| `docs/build_prompts_pdf.py` | Regenerates PROMPTS.pdf (imports prompt text from `llm_agent.py`, so it cannot drift) |
| `docs/build_deck_pdf.py` | Regenerates DECK.pdf |

## Project layout
```
app.py                 Streamlit interface
designer.py            Orchestrator: intent → bundles → ranking → layout retry loop
intent.py              Rule-based prompt parsing (budget, styles, negation, must-haves)
bundles.py             Bundle enumeration, budget-aware ranking, tiering
llm_agent.py           All LLM calls + output validation
planner.py             Layout entry point
spatial_optimizer.py   Genetic-algorithm floor-plan solver
visualizer.py          2D SVG plan (dimensions, clearances, door swing, legend)
viewer3d.py            Interactive three.js 3D view
sustainability.py      Annual water-use estimate
catalog.json           17 Kohler products with dimensions, styles, clearances
getdata.py             Price-book PDF extraction helper
tests/test_core.py     pytest suite
```

## Limitations (stated upfront)
- Budget = fixture MRP only — excludes tiles, labour, GST, installation, in-wall carriers, valves and trims.
- Generic clearances, **not** local building code (NBC India or similar). Have a licensed designer/plumber verify before construction.
- Rectangular rooms, wall-mounted fixtures only; a freestanding tub in the middle of the room is not modelled.
- Basin and faucet are vanity-mounted and so do not appear in the floor plan.
- Water figures use assumed typical values unless `flush_volume_l`, `flow_rate_lpm`, `tub_capacity_l` are added to catalog items.
- The catalog contains a single faucet and a single Classic-style product, so those repeat across designs.
- `getdata.py` needs `PriceBooK.pdf` (not committed) and `requirements-data.txt`.
