from typing import Any, Dict, List, Optional, Tuple

from spatial_optimizer import run_evolution


class Fixture:
    def __init__(self, name: str, w: float, d: float, clearance: float = 2.0,
                 category: str = "general", side_clearance: float = 0.5):
        self.name = name
        self.w = w                      # width along the wall (ft)
        self.d = d                      # depth away from the wall (ft)
        self.clearance = clearance      # front clearance (ft)
        self.side_clearance = side_clearance
        self.category = category


def solve_layout(room_width: float, room_length: float, fixtures: List[Fixture],
                 wet_wall: str = "North",
                 door: Optional[Tuple] = None,        # (wall, offset_ft[, width_ft])
                 window: Optional[Tuple[str, float]] = None,
                 generations: int = 150, pop_size: int = 80, seed: int = 42) -> Dict[str, Any]:
    """Genetic-algorithm layout: door swing, window, wet wall, toilet sightline, clearances."""
    return run_evolution(fixtures, room_width, room_length, wet_wall=wet_wall, door=door, window=window,
                         generations=generations, pop_size=pop_size, seed=seed)
