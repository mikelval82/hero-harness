from __future__ import annotations

import json

from benchmark.tron_arena.actions import Action, Direction
from benchmark.tron_arena.bots import StraightUntilBlockedBot, AlwaysLeftBot
from benchmark.tron_arena.engine import GameConfig, create_initial_state, run_match
from benchmark.tron_arena.replay import (
    Replay,
    load_replay,
    replay_from_json,
    replay_from_match,
    replay_hash,
    replay_to_dict,
    replay_to_json,
    save_replay,
)


def _sample_replay(**overrides: object) -> Replay:
    defaults = dict(
        version="1",
        seed=42,
        width=5,
        height=5,
        max_turns=50,
        initial_positions={0: (1, 2), 1: (3, 2)},
        initial_directions={0: Direction.RIGHT, 1: Direction.LEFT},
        bot_names={0: "bot_a", 1: "bot_b"},
        action_history=[
            {0: Action.STRAIGHT, 1: Action.STRAIGHT},
            {0: Action.TURN_LEFT, 1: Action.TURN_RIGHT},
        ],
        winner=0,
        turns=2,
        end_reason="collision",
    )
    defaults.update(overrides)
    return Replay(**defaults)


class TestReplayHash:
    def test_stability(self) -> None:
        r = _sample_replay()
        h1 = replay_hash(r)
        h2 = replay_hash(r)
        assert h1 == h2
        assert len(h1) == 64
        assert all(c in "0123456789abcdef" for c in h1)

    def test_different_data_produces_different_hash(self) -> None:
        r1 = _sample_replay(seed=1)
        r2 = _sample_replay(seed=2)
        assert replay_hash(r1) != replay_hash(r2)


class TestReplayToJsonRoundTrip:
    def test_round_trip_preserves_fields(self) -> None:
        r = _sample_replay()
        json_str = replay_to_json(r)
        parsed = json.loads(json_str)

        assert parsed["version"] == "1"
        assert parsed["seed"] == 42
        assert parsed["width"] == 5
        assert parsed["height"] == 5
        assert parsed["max_turns"] == 50
        assert parsed["winner"] == 0
        assert parsed["turns"] == 2
        assert parsed["end_reason"] == "collision"

    def test_replay_from_json_restores_types(self) -> None:
        r = replay_from_json(replay_to_json(_sample_replay()))

        assert r.initial_positions[0] == (1, 2)
        assert r.initial_directions[0] is Direction.RIGHT
        assert r.action_history[0][0] is Action.STRAIGHT
        assert r.bot_names[1] == "bot_b"

    def test_save_and_load_replay(self, tmp_path) -> None:
        path = tmp_path / "nested" / "replay.json"
        original = _sample_replay()

        save_replay(original, path)
        loaded = load_replay(path)

        assert loaded == original
        assert path.read_text(encoding="utf-8").endswith("\n")

    def test_int_keys_become_strings(self) -> None:
        r = _sample_replay()
        parsed = json.loads(replay_to_json(r))
        assert "0" in parsed["bot_names"]
        assert "1" in parsed["bot_names"]
        assert "0" in parsed["initial_positions"]
        assert "0" in parsed["initial_directions"]

    def test_positions_become_lists(self) -> None:
        r = _sample_replay()
        parsed = json.loads(replay_to_json(r))
        assert parsed["initial_positions"]["0"] == [1, 2]
        assert parsed["initial_positions"]["1"] == [3, 2]

    def test_enums_become_values(self) -> None:
        r = _sample_replay()
        parsed = json.loads(replay_to_json(r))
        assert parsed["initial_directions"]["0"] == "right"
        assert parsed["initial_directions"]["1"] == "left"
        assert parsed["action_history"][0]["0"] == "straight"
        assert parsed["action_history"][0]["1"] == "straight"


class TestReplayFromMatch:
    def test_populates_from_config_and_result(self) -> None:
        config = GameConfig(seed=1, width=5, height=5, max_turns=50)
        result = run_match(config, StraightUntilBlockedBot, AlwaysLeftBot)
        bot_names = {0: "sub", 1: "al"}
        replay = replay_from_match(config, result, bot_names)

        assert replay.seed == 1
        assert replay.width == 5
        assert replay.height == 5
        assert replay.max_turns == 50
        assert replay.version == "1"
        assert replay.bot_names == {0: "sub", 1: "al"}
        assert replay.winner == result.winner
        assert replay.turns == result.turns
        assert replay.end_reason == result.end_reason
        assert replay.action_history == result.action_history

        state = create_initial_state(config)
        assert replay.initial_positions == state.positions
        assert replay.initial_directions == state.directions


class TestReplayEmptyHistory:
    def test_empty_turn_serializes(self) -> None:
        r = _sample_replay(action_history=[{}])
        json_str = replay_to_json(r)
        parsed = json.loads(json_str)
        assert parsed["action_history"] == [{}]
        h = replay_hash(r)
        assert len(h) == 64

    def test_no_history_serializes(self) -> None:
        r = _sample_replay(action_history=[])
        json_str = replay_to_json(r)
        parsed = json.loads(json_str)
        assert parsed["action_history"] == []
