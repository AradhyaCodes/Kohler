<<<<<<< HEAD
# KOHLER AI Bathroom Designer & Planner

Turns a customer request + room constraints into **three feasible, priced bathroom designs** with a 2D plan and an interactive 3D view.

## How it works
1. **Understand** - rule-based parser (budget incl. lakh/k, styles, negation like "not modern", must-haves, "shower only") + optional LLM extraction. LLM output is validated against a fixed vocabulary.
2. **Constrain (Python, deterministic)** - enumerate bundles from `catalog.json`; drop anything over budget or too big for the room.
3. **Choose (LLM, optional)** - picks the best-looking bundle from a shortlist of already-valid ones and writes the narrative. Prices/totals are written by Python; narratives containing money figures are rejected.
4. **Prove it fits** - a genetic algorithm lays out each candidate (door swing, window, wet wall, toilet sightline, clearances). A bundle is only shown if its layout has zero violations; otherwise the next candidate is tried.
5. **Present** - Best style match / Lower-cost / Premium, with SVG plan, 3D view, BOM CSV, power-point notes and an estimated water-use figure.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env        # optional: add OPENROUTER_API_KEY or GEMINI_API_KEY
streamlit run app.py
```
No key = rule-based mode (fully functional). Set `LLM_MODEL` to override the litellm model string.
On Streamlit Cloud put keys in `st.secrets` instead of `.env`.

## Tests
```bash
pip install -r requirements-dev.txt
pytest
```

## Limitations (be upfront in the demo)
- Budget = fixture MRP only (no tiles, labour, GST, installation, carriers/valves).
- Generic clearances, not local building code; rectangular rooms, wall-mounted fixtures only.
- Water figures use assumed typical values unless `flush_volume_l`, `flow_rate_lpm`, `tub_capacity_l` are added to catalog items.
- `getdata.py` needs `PriceBooK.pdf` (not committed) and `requirements-data.txt`.
=======
# Kohler
Kohler AI bathroom planner 
>>>>>>> 2dca0c764b15f1a90eafdc2f19aca53ee707d890
