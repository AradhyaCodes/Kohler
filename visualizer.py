import html
from typing import List, Optional

from spatial_optimizer import DOOR_WIDTH, WINDOW_WIDTH, clamp_offset

PAD = 85
LABELS = {"toilet": "Toilet", "smart toilet": "Toilet", "vanity": "Vanity", "basin": "Basin",
          "sink": "Basin", "shower": "Shower", "shower enclosure": "Shower", "bathtub": "Bathtub"}
COLORS = {"toilet": "#ffc107", "smart toilet": "#ffc107", "vanity": "#0d6efd", "basin": "#0d6efd",
          "sink": "#0d6efd", "shower": "#20c997", "shower enclosure": "#20c997",
          "bathtub": "#6f42c1", "general": "#6c757d"}
TEXT = {"#ffc107": "#212529"}


def compute_scale(room_w: float, room_l: float) -> float:
    return max(20.0, min(48.0, 560.0 / max(room_w, room_l)))


def svg_height(room_l: float, room_w: float) -> int:
    return int(room_l * compute_scale(room_w, room_l)) + 2 * PAD + 60


def _wall_rect(wall, offset, width, t, W, H, s):
    if wall == "North":
        return offset * s, -t / 2, width * s, t
    if wall == "South":
        return offset * s, H - t / 2, width * s, t
    if wall == "West":
        return -t / 2, offset * s, t, width * s
    return W - t / 2, offset * s, t, width * s  # East


def _door_swing(wall, o, dwid, W, H, s):
    dw, p = dwid * s, o * s
    if wall == "North":
        return f"M {p+dw},0 A {dw},{dw} 0 0 1 {p},{dw} L {p},0", (p + dw / 2, -10, "middle")
    if wall == "South":
        return f"M {p+dw},{H} A {dw},{dw} 0 0 0 {p},{H-dw} L {p},{H}", (p + dw / 2, H + 20, "middle")
    if wall == "West":
        return f"M 0,{p+dw} A {dw},{dw} 0 0 0 {dw},{p} L 0,{p}", (-10, p + dw / 2, "end")
    return f"M {W},{p+dw} A {dw},{dw} 0 0 1 {W-dw},{p} L {W},{p}", (W + 10, p + dw / 2, "start")


def draw_layout_svg(layout: List[dict], room_w: float, room_l: float, door: Optional[tuple],
                    window: Optional[tuple], wet_wall: Optional[str] = None) -> str:
    s = compute_scale(room_w, room_l)
    W, H = room_w * s, room_l * s
    el = [f'<rect x="0" y="0" width="{W}" height="{H}" fill="#f8f9fa" stroke="#343a40" stroke-width="6"/>']

    if wet_wall:
        x, y, w, h = _wall_rect(wet_wall, 0, room_w if wet_wall in ("North", "South") else room_l, 12, W, H, s)
        el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#0d6efd" opacity="0.35"/>')

    if window:
        ww, wo = window
        wo = clamp_offset(wo, ww, WINDOW_WIDTH, room_w, room_l)
        x, y, w, h = _wall_rect(ww, wo, WINDOW_WIDTH, 8, W, H, s)
        el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#a5d8ff" stroke="#1971c2" stroke-width="1.5"/>')

    if door:
        dwl, do = door[0], door[1]
        dwid = door[2] if len(door) > 2 else DOOR_WIDTH
        do = clamp_offset(do, dwl, dwid, room_w, room_l)
        x, y, w, h = _wall_rect(dwl, do, dwid, 8, W, H, s)
        el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#f8f9fa"/>')
        path, (tx, ty, anchor) = _door_swing(dwl, do, dwid, W, H, s)
        el.append(f'<path d="{path}" fill="rgba(13,202,240,0.12)" stroke="#0dcaf0" stroke-width="2" stroke-dasharray="4,3"/>')
        el.append(f'<text x="{tx}" y="{ty}" font-family="Arial" font-size="12" fill="#0a8fa8" text-anchor="{anchor}">Door</text>')

    # wall names
    def tag(n):
        return f"{n} (wet wall)" if n == wet_wall else n
    el.append(f'<text x="{W/2}" y="-30" font-family="Arial" font-size="11" fill="#868e96" text-anchor="middle">{tag("North")}</text>')
    el.append(f'<text x="{W/2}" y="{H+40}" font-family="Arial" font-size="11" fill="#868e96" text-anchor="middle">{tag("South")}</text>')
    el.append(f'<text transform="translate(-26,{H/2}) rotate(-90)" font-family="Arial" font-size="11" fill="#868e96" text-anchor="middle">{tag("West")}</text>')
    el.append(f'<text transform="translate({W+32},{H/2}) rotate(90)" font-family="Arial" font-size="11" fill="#868e96" text-anchor="middle">{tag("East")}</text>')

    # overall dimension lines
    el.append(f'<g stroke="#495057" stroke-width="1"><line x1="0" y1="-62" x2="{W}" y2="-62"/>'
              f'<line x1="0" y1="-67" x2="0" y2="-57"/><line x1="{W}" y1="-67" x2="{W}" y2="-57"/>'
              f'<line x1="-58" y1="0" x2="-58" y2="{H}"/><line x1="-63" y1="0" x2="-53" y2="0"/>'
              f'<line x1="-63" y1="{H}" x2="-53" y2="{H}"/></g>')
    el.append(f'<text x="{W/2}" y="-68" font-family="Arial" font-size="12" fill="#212529" text-anchor="middle">{room_w:g} ft</text>')
    el.append(f'<text transform="translate(-64,{H/2}) rotate(-90)" font-family="Arial" font-size="12" fill="#212529" text-anchor="middle">{room_l:g} ft</text>')

    legend, seen = [], set()
    for it in layout:
        cat = it.get("category", "general").lower()
        color = COLORS.get(cat, COLORS["general"])
        tcol = TEXT.get(color, "#ffffff")
        label = LABELS.get(cat, cat.title())
        x, y, w, h = it["x"] * s, it["y"] * s, it["w"] * s, it["h"] * s
        cx1, cy1, cx2, cy2 = [v * s for v in it["clear"]]
        el.append(f'<rect x="{cx1}" y="{cy1}" width="{max(cx2-cx1,0)}" height="{max(cy2-cy1,0)}" fill="{color}" '
                  f'fill-opacity="0.08" stroke="{color}" stroke-width="2" stroke-dasharray="5,5" opacity="0.7"/>')
        el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" stroke="#212529" stroke-width="2"/>')
        fs = max(9, min(13, w / (len(label) * 0.65)))
        el.append(f'<text x="{x+w/2}" y="{y+h/2}" font-family="Arial" font-size="{fs:.0f}" fill="{tcol}" '
                  f'font-weight="bold" text-anchor="middle">{html.escape(label)}</text>')
        el.append(f'<text x="{x+w/2}" y="{y+h/2+12}" font-family="Arial" font-size="9" fill="{tcol}" '
                  f'text-anchor="middle">{it["w"]:.1f}x{it["h"]:.1f} ft</text>')
        if label not in seen:
            seen.add(label)
            legend.append((color, "none", label))
    legend += [("none", "#6c757d", "Clearance"), ("#cff4fc", "#0dcaf0", "Door swing"), ("#a5d8ff", "#1971c2", "Window")]
    if wet_wall:
        legend.append(("#0d6efd", "none", "Wet wall"))

    # legend (wraps)
    legend_w = max(W, 340)
    lx, ly, rows = 0.0, H + 62, 1
    for fill, stroke, text in legend:
        item_w = 26 + 7 * len(text)
        if lx + item_w > legend_w:
            lx, ly, rows = 0.0, ly + 18, rows + 1
        dash = ' stroke-dasharray="3,2"' if text == "Clearance" else ""
        el.append(f'<rect x="{lx}" y="{ly-10}" width="12" height="12" fill="{fill}" fill-opacity="{0.9 if fill != "none" else 0}" '
                  f'stroke="{stroke if stroke != "none" else "#212529"}" stroke-width="1.5"{dash}/>')
        el.append(f'<text x="{lx+17}" y="{ly}" font-family="Arial" font-size="11" fill="#212529">{html.escape(text)}</text>')
        lx += item_w

    svg_w = max(W + 2 * PAD, legend_w + 2 * PAD)
    svg_h = H + 2 * PAD + (rows - 1) * 18
    return (f'<svg width="{svg_w}" height="{svg_h}" xmlns="http://www.w3.org/2000/svg">\n'
            f'<g transform="translate({PAD}, {PAD})">\n' + "\n".join(el) + '\n</g>\n</svg>')
