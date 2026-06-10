from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from benchmark.tron_arena.actions import Action, Direction
from benchmark.tron_arena.engine import GameConfig, MatchResult, create_initial_state


@dataclass
class Replay:
    version: str
    seed: int
    width: int
    height: int
    max_turns: int
    initial_positions: Dict[int, Tuple[int, int]]
    initial_directions: Dict[int, Direction]
    bot_names: Dict[int, str]
    action_history: List[Dict[int, Action]]
    winner: Optional[int]
    turns: int
    end_reason: str


def replay_to_dict(replay: Replay) -> dict:
    return {
        "version": replay.version,
        "seed": replay.seed,
        "width": replay.width,
        "height": replay.height,
        "max_turns": replay.max_turns,
        "initial_positions": {
            str(k): list(v) for k, v in replay.initial_positions.items()
        },
        "initial_directions": {
            str(k): v.value for k, v in replay.initial_directions.items()
        },
        "bot_names": {str(k): v for k, v in replay.bot_names.items()},
        "action_history": [
            {str(k): v.value for k, v in turn.items()}
            for turn in replay.action_history
        ],
        "winner": replay.winner,
        "turns": replay.turns,
        "end_reason": replay.end_reason,
    }


def replay_to_json(replay: Replay) -> str:
    return json.dumps(replay_to_dict(replay), sort_keys=True, separators=(",", ":"))


def replay_from_dict(data: dict) -> Replay:
    return Replay(
        version=str(data["version"]),
        seed=int(data["seed"]),
        width=int(data["width"]),
        height=int(data["height"]),
        max_turns=int(data["max_turns"]),
        initial_positions={
            int(k): (int(v[0]), int(v[1]))
            for k, v in data["initial_positions"].items()
        },
        initial_directions={
            int(k): Direction(v)
            for k, v in data["initial_directions"].items()
        },
        bot_names={int(k): str(v) for k, v in data["bot_names"].items()},
        action_history=[
            {int(k): Action(v) for k, v in turn.items()}
            for turn in data["action_history"]
        ],
        winner=data["winner"],
        turns=int(data["turns"]),
        end_reason=str(data["end_reason"]),
    )


def replay_from_json(text: str) -> Replay:
    return replay_from_dict(json.loads(text))


def save_replay(replay: Replay, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(replay_to_json(replay) + "\n", encoding="utf-8")


def load_replay(path: str | Path) -> Replay:
    return replay_from_json(Path(path).read_text(encoding="utf-8"))


def replay_hash(replay: Replay) -> str:
    return hashlib.sha256(replay_to_json(replay).encode("utf-8")).hexdigest()


def replay_from_match(
    config: GameConfig,
    result: MatchResult,
    bot_names: Dict[int, str],
) -> Replay:
    state = create_initial_state(config)
    return Replay(
        version="1",
        seed=config.seed,
        width=config.width,
        height=config.height,
        max_turns=config.max_turns,
        initial_positions=state.positions,
        initial_directions=state.directions,
        bot_names=bot_names,
        action_history=result.action_history,
        winner=result.winner,
        turns=result.turns,
        end_reason=result.end_reason,
    )
