from __future__ import annotations

from typing import Any

from benchmark.tron_arena.actions import Direction
from benchmark.tron_arena.engine import GameConfig, GameState


def small_config(seed: int = 1, **kwargs: Any) -> GameConfig:
    """Return a 5x5 GameConfig with sensible test defaults."""
    defaults = {"seed": seed, "width": 5, "height": 5, "max_turns": 200}
    defaults.update(kwargs)
    return GameConfig(**defaults)


def make_state(**overrides: Any) -> GameState:
    """Return a 2-player GameState on a 5x5 grid with sensible defaults.

    P0 at (1,2) facing RIGHT, P1 at (3,2) facing LEFT — matches
    create_initial_state(GameConfig(width=5, height=5, seed=1)).
    """
    defaults: dict[str, Any] = {
        "positions": {0: (1, 2), 1: (3, 2)},
        "directions": {0: Direction.RIGHT, 1: Direction.LEFT},
        "trails": {0: {(1, 2)}, 1: {(3, 2)}},
        "alive": {0: True, 1: True},
        "turn": 0,
    }
    defaults.update(overrides)
    return GameState(**defaults)
