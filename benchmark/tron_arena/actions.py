from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


DIRECTION_DELTAS: Dict[Direction, Tuple[int, int]] = {
    Direction.UP: (0, -1),
    Direction.DOWN: (0, 1),
    Direction.LEFT: (-1, 0),
    Direction.RIGHT: (1, 0),
}


class Action(str, Enum):
    STRAIGHT = "straight"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"


_LEFT_TURN: Dict[Direction, Direction] = {
    Direction.UP: Direction.LEFT,
    Direction.LEFT: Direction.DOWN,
    Direction.DOWN: Direction.RIGHT,
    Direction.RIGHT: Direction.UP,
}

_RIGHT_TURN: Dict[Direction, Direction] = {
    Direction.UP: Direction.RIGHT,
    Direction.RIGHT: Direction.DOWN,
    Direction.DOWN: Direction.LEFT,
    Direction.LEFT: Direction.UP,
}


def resolve_direction(facing: Direction, action: Action) -> Direction:
    if action is Action.STRAIGHT:
        return facing
    if action is Action.TURN_LEFT:
        return _LEFT_TURN[facing]
    return _RIGHT_TURN[facing]
