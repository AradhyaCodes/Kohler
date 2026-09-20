import csv
import io
import json
import os
import time

import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from bundles import inr
from designer import design_bathroom
from intent import DEFAULT_BUDGET_INR, find_budget
from visualizer import draw_layout_svg, svg_height
from viewer3d import build_3d_html

st.set_page_config(page_title="Kohler AI Designer", layout="wide")
COOLDOWN_S = 6


@st.cache_data
def load_catalog():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def get_api_key():
    key = os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("api_key")
    if not key:
        try:  # Streamlit Cloud secrets
            key = st.secrets.get("OPENROUTER_API_KEY") or st.secrets.get("GEMINI_API_KEY")
        except Exception:
            key = None
    return key


CATALOG = load_catalog()
WALLS = ["North", "South", "East", "West"]

# ---------------- Sidebar ----------------
st.sidebar.title("Room Constraints")
st.sidebar.header("1. Dimensions")
width_ft = st.sidebar.number_input("Width (ft, West-East)", min_value=5.0, max_value=20.0, value=13.0, step=0.5)
length_ft = st.sidebar.number_input("Length (ft, North-South)", min_value=5.0, max_value=20.0, value=11.0, step=0.5)


def wall_len(w):
    return float(width_ft if w in ("North", "South") else length_ft)


st.sidebar.header("2. Structural Elements")
door_wall = st.sidebar.selectbox("Door Wall", WALLS, index=3)
door_width = st.sidebar.slider("Door width (ft)", 2.0, 3.0, 2.5, 0.5)
door_max = wall_len(door_wall) - door_width
door_offset = st.sidebar.slider("Door Offset (ft)", 0.0, door_max, min(1.0, door_max), 0.5)
window_wall = st.sidebar.selectbox("Window Wall", WALLS, index=2)
win_max = wall_len(window_wall) - 3.0
window_offset = st.sidebar.slider("Window Offset (ft)", 0.0, win_max, min(3.0, win_max), 0.5)

st.sidebar.header("3. Plumbing")
wet_wall = st.sidebar.selectbox("Primary Plumbing Wall (Wet Wall)", WALLS, index=0)

# ---------------- Main ----------------
st.title("KOHLER AI Spatial Designer")
st.write("Budget-aware product curation and a door/window/plumbing-aware floor plan, optimized automatically.")
st.caption("Budget = Kohler MRP of the selected fixtures only. It excludes tiles, labour, GST, installation, in-wall carriers, "
           "valves/trims and other accessories. Layouts use generic clearances, not local building code: "
           "have a licensed designer/plumber verify before construction.")

user_prompt = st.text_area(
    "Describe your budget and aesthetic:",
    "I have a budget of 2,00,000. Make me a modern style bathroom design.",
)
b = find_budget(user_prompt)
st.caption(f"Detected budget: {inr(b)}" if b else f"No budget detected - {inr(DEFAULT_BUDGET_INR)} will be assumed.")

if st.button("Generate Architectural Plan", type="primary"):
    key = get_api_key()
    if key and time.time() - st.session_state.get("last_run", 0) < COOLDOWN_S:
        st.warning(f"Please wait a few seconds between requests (limit protects the API quota).")
    else:
        st.session_state["last_run"] = time.time()
        door = (door_wall, door_offset, door_width)
        window = (window_wall, window_offset)
        cache = st.session_state.setdefault("cache", {})
        ck = (user_prompt, width_ft, length_ft, wet_wall, door, window, bool(key))
        with st.spinner("Understanding your request, checking budget and fit, and optimizing layouts..."):
            if ck in cache:
                result = cache[ck]
            else:
                result = design_bathroom(user_prompt, CATALOG, width_ft, length_ft, wet_wall, door, window, api_key=key)
                if not result.get("llm_error"):
                    cache[ck] = result
            for alt in result["alternatives"]:
                alt["svg"] = draw_layout_svg(alt["layout"], width_ft, length_ft, door, window, wet_wall)
                alt["html3d"] = build_3d_html(alt["layout"], width_ft, length_ft, door, window, wet_wall)
        st.session_state["plan"] = {"result": result, "w": width_ft, "l": length_ft}

plan = st.session_state.get("plan")
if plan:
    result = plan["result"]
    if result["error"]:
        st.error(result["message"])
        st.info("Tip: adjust the budget, room size, door/window positions or the wet wall.")
    else:
        it = result["intent"]
        parts = [f"budget {inr(result['budget'])}" + (" (assumed)" if result["budget_assumed"] else "")]
        if it["styles"]:
            parts.append("style: " + ", ".join(it["styles"]))
        if it["avoid_styles"]:
            parts.append("avoiding: " + ", ".join(it["avoid_styles"]))
        if it["must_have"]:
            parts.append("must have: " + ", ".join(it["must_have"]))
        if it["exclude"]:
            parts.append("excluding: " + ", ".join(it["exclude"]))
        st.caption("Understood: " + " | ".join(parts) + f"  -  engine: {result['source']}")
        for n in result["notes"]:
            st.info(n)
        if result.get("llm_error"):
            with st.expander("LLM fallback reason (rule-based logic was used)"):
                st.code(result["llm_error"])

        alts = result["alternatives"]
        tabs = st.tabs([f"{a['tier']} - {inr(a['total'])}" for a in alts])
        for idx, (tab, a) in enumerate(zip(tabs, alts)):
            with tab:
                col1, col2 = st.columns([2, 1])
                with col1:
                    t2d, t3d = st.tabs(["2D plan", "3D view"])
                    with t2d:
                        st.components.v1.html(a["svg"], height=svg_height(plan["l"], plan["w"]) + 20, scrolling=True)
                        st.download_button("Download plan (SVG)", a["svg"], f"bathroom_plan_{idx}.svg",
                                           "image/svg+xml", key=f"svg_{idx}")
                    with t3d:
                        st.components.v1.html(a["html3d"], height=520)
                with col2:
                    st.subheader("Design Rationale")
                    st.info(a["rationale"])
                    for pn in a["power_notes"]:
                        st.warning(pn)

                    st.subheader("Selected Kohler Products")
                    for i in a["items"]:
                        st.write(f"- **{i['name']}** ({i['category']}, {i['style']}) - {inr(i['price_inr'])}")
                    st.markdown(f"### Total Cost: **{inr(a['total'])}**")
                    if not result["budget_assumed"]:
                        used = a["used_pct"]
                        left = result["budget"] - a["total"]
                        c1, c2 = st.columns(2)
                        c1.metric("Budget used", f"{used:.0f}%", f"of {inr(result['budget'])}",
                                  delta_color="off")
                        c2.metric("Unallocated", inr(left), delta_color="off")
                        st.progress(min(1.0, a["total"] / result["budget"]))
                        if used < 70:
                            st.caption("The remainder is real headroom: no bundle in this catalog uses more of "
                                       "the budget without breaking the requested style or the room's clearances.")
                        else:
                            st.caption("Headroom left for tiles, labour, GST, installation, carriers and trims, "
                                       "which this total excludes.")

                    w = a["water"]
                    st.metric("Est. annual water use", f"{w['annual_litres'] / 1000:.0f} kL")
                    st.caption(w["note"])

                    buf = io.StringIO()
                    cw = csv.writer(buf)
                    cw.writerow(["sku", "name", "category", "style", "price_inr"])
                    for i in a["items"]:
                        cw.writerow([i["sku"], i["name"], i["category"], i["style"], i["price_inr"]])
                    cw.writerow(["", "TOTAL", "", "", a["total"]])
                    st.download_button("Download bill of materials (CSV)", buf.getvalue(),
                                       f"bom_{idx}.csv", "text/csv", key=f"bom_{idx}")