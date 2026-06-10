from __future__ import annotations

import pytest

from benchmark.tron_arena.actions import Action, Direction
from benchmark.tron_arena.replay import Replay
from benchmark.tron_arena.visualize import replay_frames


def test_replay_frames_reconstruct_player_paths() -> None:
    replay = Replay(
        version="1",
        seed=1,
        width=5,
        height=5,
        max_turns=10,
        initial_positions={0: (1, 2), 1: (3, 2)},
        initial_directions={0: Direction.RIGHT, 1: Direction.LEFT},
        bot_names={0: "a", 1: "b"},
        action_history=[
            {0: Action.STRAIGHT, 1: Action.TURN_RIGHT},
            {0: Action.TURN_LEFT, 1: Action.STRAIGHT},
        ],
        winner=None,
        turns=2,
        end_reason="draw",
    )

    frames = replay_frames(replay)

    assert len(frames) == 3
    assert frames[0].positions[0] == (1, 2)
    assert frames[1].positions[0] == (2, 2)
    assert frames[2].positions[0] == (2, 1)
    assert frames[2].trails[0] == [(1, 2), (2, 2), (2, 1)]
    assert frames[2].positions[1] == (3, 0)


def test_plot_replay_requires_matplotlib_when_missing(monkeypatch) -> None:
    from benchmark.tron_arena import visualize

    replay = Replay(
        version="1",
        seed=1,
        width=5,
        height=5,
        max_turns=10,
        initial_positions={0: (1, 2), 1: (3, 2)},
        initial_directions={0: Direction.RIGHT, 1: Direction.LEFT},
        bot_names={0: "a", 1: "b"},
        action_history=[],
        winner=None,
        turns=0,
        end_reason="draw",
    )

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "matplotlib.pyplot":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="matplotlib"):
        visualize.plot_replay(replay, show=False)
