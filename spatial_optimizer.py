"""Genetic-algorithm floor-plan optimizer.

Coordinate system (shared with visualizer.py): origin = top-left corner,
x grows East (right), y grows South (down). North wall is y=0, West wall is x=0.
Every fixture is mounted against one wall; its gene is (wall, position along wall).
"""
import random
from typing import Any, Dict, List, Optional, Tuple

WALLS = ["North", "South", "West", "East"]
OPPOSITE = {"North": "South", "South": "North", "West": "East", "East": "West"}
ROTATION = {"North": 0, "South": 180, "West": 90, "East": 270}
DOOR_WIDTH = 3.0
DOOR_SWING = 3.0
WINDOW_WIDTH = 3.0
PLUMBED_KEYS = ("toilet", "shower", "bath", "vanity", "basin", "sink")
TALL_KEYS = ("shower", "bath")
EPS = 1e-6


def wall_span(wall: str, room_w: float, room_l: float) -> float:
    return room_w if wall in ("North", "South") else room_l


def clamp_offset(offset: float, wall: str, width: float, room_w: float, room_l: float) -> float:
    return max(0.0, min(float(offset), wall_span(wall, room_w, room_l) - width))


def overlap_area(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if (w > EPS and h > EPS) else 0.0


def fixture_box(f, wall, pos, room_w, room_l):
    if wall == "North":
        return (pos, 0.0, pos + f.w, f.d)
    if wall == "South":
        return (pos, room_l - f.d, pos + f.w, room_l)
    if wall == "West":
        return (0.0, pos, f.d, pos + f.w)
    return (room_w - f.d, pos, room_w, pos + f.w)  # East


def clearance_box(f, wall, box):
    c = f.clearance
    x1, y1, x2, y2 = box
    if wall == "North":
        return (x1, y2, x2, y2 + c)
    if wall == "South":
        return (x1, y1 - c, x2, y1)
    if wall == "West":
        return (x2, y1, x2 + c, y2)
    return (x1 - c, y1, x1, y2)  # East


def opening_box(wall, offset, width, depth, room_w, room_l):
    if wall == "North":
        return (offset, 0.0, offset + width, depth)
    if wall == "South":
        return (offset, room_l - depth, offset + width, room_l)
    if wall == "West":
        return (0.0, offset, depth, offset + width)
    return (room_w - depth, offset, room_w, offset + width)  # East


def _is_plumbed(cat: str) -> bool:
    return any(k in cat for k in PLUMBED_KEYS)


def evaluate(genes, fixtures, ctx) -> Tuple[float, List[str]]:
    """Return (fitness, hard_violations). Higher fitness is better."""
    W, L = ctx["W"], ctx["L"]
    room_box = (0.0, 0.0, W, L)
    score = 0.0
    hard: List[str] = []
    boxes, clears = [], []
    for f, (wall, pos) in zip(fixtures, genes):
        b = fixture_box(f, wall, pos, W, L)
        boxes.append(b)
        clears.append(clearance_box(f, wall, b))

    for i, f in enumerate(fixtures):
        wall, pos = genes[i]
        cat = f.category.lower()
        span = wall_span(wall, W, L)

        # Plumbing: reward the wet wall
        if _is_plumbed(cat):
            if wall == ctx["wet_wall"]:
                score += 500 if any(k in cat for k in ("toilet", "shower", "bath")) else 250
            else:
                score -= 200

        # Showers like corners
        if "shower" in cat and (pos < 0.05 or pos > span - f.w - 0.05):
            score += 100

        # Door swing must stay clear
        if ctx["door_box"]:
            ov = overlap_area(boxes[i], ctx["door_box"])
            if ov > 0:
                score -= 2000 + ov * 200
                hard.append(f"{f.name} blocks the door swing")
            # Toilet sightline from the door
            if "toilet" in cat and wall == OPPOSITE[ctx["door_wall"]]:
                if abs((pos + f.w / 2) - ctx["door_center"]) < 2.0:
                    score -= 600

        # Tall fixtures shouldn't cover the window
        if ctx["window_box"] and any(k in cat for k in TALL_KEYS):
            if overlap_area(boxes[i], ctx["window_box"]) > 0:
                score -= 150

        # Front clearance must exist inside the room
        cb = clears[i]
        cb_area = (cb[2] - cb[0]) * (cb[3] - cb[1])
        outside = cb_area - overlap_area(cb, room_box)
        if outside > 0:
            score -= outside * 400
            if outside > 0.5:
                hard.append(f"Not enough front clearance for {f.name}")

        # Clearance must not be blocked by other fixtures
        for j, g in enumerate(fixtures):
            if j == i:
                continue
            ov = overlap_area(cb, boxes[j])
            if ov > 0:
                score -= ov * 300
                if ov > 0.5:
                    hard.append(f"{g.name} blocks the clearance zone of {f.name}")

    # Fixture-vs-fixture
    for i in range(len(fixtures)):
        for j in range(i + 1, len(fixtures)):
            ov = overlap_area(boxes[i], boxes[j])
            if ov > 0:
                score -= 3000 + ov * 500
                hard.append(f"{fixtures[i].name} overlaps {fixtures[j].name}")
                continue
            gap = max(getattr(fixtures[i], "side_clearance", 0.5),
                      getattr(fixtures[j], "side_clearance", 0.5))
            b = boxes[i]
            inflated = (b[0] - gap, b[1] - gap, b[2] + gap, b[3] + gap)
            if overlap_area(inflated, boxes[j]) > 0:
                score -= 200  # soft: side-spacing shortfall
    return score, sorted(set(hard))


def _snap(v: float, lo: float, hi: float) -> float:
    return min(max(round(v * 4) / 4, lo), hi)


def run_evolution(fixtures, room_w: float, room_l: float, wet_wall: str = "North",
                  door: Optional[Tuple[str, float]] = None,
                  window: Optional[Tuple[str, float]] = None,
                  generations: int = 150, pop_size: int = 80, seed: int = 42) -> Dict[str, Any]:
    rng = random.Random(seed)

    allowed = []
    for f in fixtures:
        ok = [w for w in WALLS if wall_span(w, room_w, room_l) >= f.w and
              (room_l if w in ("North", "South") else room_w) >= f.d]
        if not ok:
            return {"error": "SPATIAL_OVERFLOW", "layout": [], "violations": [],
                    "message": f"{f.name} ({f.w} ft wide) does not fit against any wall of a {room_w}x{room_l} ft room."}
        allowed.append(ok)

    ctx = {"W": room_w, "L": room_l, "wet_wall": wet_wall,
           "door_box": None, "door_wall": None, "door_center": 0.0, "window_box": None}
    if door:
        dwl, do = door[0], door[1]
        dwid = door[2] if len(door) > 2 else DOOR_WIDTH   # optional door width (ft)
        do = clamp_offset(do, dwl, dwid, room_w, room_l)
        ctx.update(door_box=opening_box(dwl, do, dwid, dwid, room_w, room_l),
                   door_wall=dwl, door_center=do + dwid / 2)
    if window:
        ww, wo = window
        wo = clamp_offset(wo, ww, WINDOW_WIDTH, room_w, room_l)
        ctx["window_box"] = opening_box(ww, wo, WINDOW_WIDTH, 0.5, room_w, room_l)

    def rand_gene(k):
        f = fixtures[k]
        if _is_plumbed(f.category.lower()) and wet_wall in allowed[k] and rng.random() < 0.5:
            wall = wet_wall
        else:
            wall = rng.choice(allowed[k])
        hi = max(0.0, wall_span(wall, room_w, room_l) - f.w)
        return (wall, _snap(rng.uniform(0, hi), 0.0, hi))

    def jitter(k, gene):
        wall, pos = gene
        hi = max(0.0, wall_span(wall, room_w, room_l) - fixtures[k].w)
        return (wall, _snap(pos + rng.gauss(0, 0.75), 0.0, hi))

    def make(genes):
        s, v = evaluate(genes, fixtures, ctx)
        return (s, genes, v)

    pop = [make([rand_gene(k) for k in range(len(fixtures))]) for _ in range(pop_size)]

    def tournament():
        return max(rng.sample(pop, min(3, len(pop))), key=lambda p: p[0])

    for _ in range(generations):
        pop.sort(key=lambda p: p[0], reverse=True)
        nxt = pop[:4]  # elitism
        while len(nxt) < pop_size:
            a, b = tournament(), tournament()
            child = [a[1][k] if rng.random() < 0.5 else b[1][k] for k in range(len(fixtures))]
            for k in range(len(child)):
                r = rng.random()
                if r < 0.15:
                    child[k] = rand_gene(k)
                elif r < 0.40:
                    child[k] = jitter(k, child[k])
            nxt.append(make(child))
        pop = nxt

    score, genes, violations = max(pop, key=lambda p: p[0])
    layout = []
    for f, (wall, pos) in zip(fixtures, genes):
        b = fixture_box(f, wall, pos, room_w, room_l)
        cb = clearance_box(f, wall, b)
        layout.append({
            "name": f.name, "category": f.category, "wall": wall,
            "rotation": ROTATION[wall],
            "x": round(b[0], 2), "y": round(b[1], 2),
            "w": round(b[2] - b[0], 2), "h": round(b[3] - b[1], 2),
            "clearance": f.clearance,
            "clear": [round(v, 2) for v in cb],
        })
    return {"error": None, "layout": layout, "violations": violations, "score": round(score, 1)}
