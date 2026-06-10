from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from benchmark.tron_arena.actions import Action, DIRECTION_DELTAS, Direction, resolve_direction
from benchmark.tron_arena.replay import Replay, load_replay


@dataclass
class ReplayFrame:
    turn: int
    positions: Dict[int, Tuple[int, int]]
    directions: Dict[int, Direction]
    trails: Dict[int, List[Tuple[int, int]]]


def replay_frames(replay: Replay) -> List[ReplayFrame]:
    positions = dict(replay.initial_positions)
    directions = dict(replay.initial_directions)
    trails = {pid: [pos] for pid, pos in positions.items()}
    frames = [
        ReplayFrame(
            turn=0,
            positions=dict(positions),
            directions=dict(directions),
            trails={pid: list(path) for pid, path in trails.items()},
        )
    ]

    for turn_index, turn_actions in enumerate(replay.action_history, 1):
        for pid in sorted(positions):
            action = turn_actions.get(pid)
            if action is None:
                continue
            directions[pid] = resolve_direction(directions[pid], action)
            dx, dy = DIRECTION_DELTAS[directions[pid]]
            x, y = positions[pid]
            positions[pid] = (x + dx, y + dy)
            trails[pid].append(positions[pid])
        frames.append(
            ReplayFrame(
                turn=turn_index,
                positions=dict(positions),
                directions=dict(directions),
                trails={pid: list(path) for pid, path in trails.items()},
            )
        )

    return frames


def plot_replay(replay: Replay, *, output: str | Path | None = None, show: bool = True) -> None:
    try:
        if not show or output is not None:
            import matplotlib
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for replay visualization") from exc

    frame = replay_frames(replay)[-1]
    fig, ax = plt.subplots()
    ax.set_xlim(-0.5, replay.width - 0.5)
    ax.set_ylim(replay.height - 0.5, -0.5)
    ax.set_aspect("equal")
    ax.set_xticks(range(replay.width))
    ax.set_yticks(range(replay.height))
    ax.grid(True, linewidth=0.5)

    colors = ["tab:cyan", "tab:orange", "tab:green", "tab:red", "tab:purple"]
    for index, pid in enumerate(sorted(frame.trails)):
        path = frame.trails[pid]
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        color = colors[index % len(colors)]
        ax.plot(xs, ys, color=color, linewidth=2, label=f"{pid}: {replay.bot_names.get(pid, pid)}")
        ax.scatter(xs[-1], ys[-1], color=color, s=80)

    winner = "draw" if replay.winner is None else f"player {replay.winner}"
    ax.set_title(f"seed={replay.seed} turns={replay.turns} winner={winner} reason={replay.end_reason}")
    ax.legend(loc="upper right")

    if output is not None:
        fig.savefig(output, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)


def animate_replay(
    replay: Replay,
    *,
    interval_ms: int = 150,
    output: str | Path | None = None,
    show: bool = True,
) -> None:
    try:
        if not show or output is not None:
            import matplotlib
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for replay animation") from exc

    frames = replay_frames(replay)
    fig, ax = plt.subplots()
    colors = ["tab:cyan", "tab:orange", "tab:green", "tab:red", "tab:purple"]

    def draw(frame_index: int) -> None:
        frame = frames[frame_index]
        ax.clear()
        ax.set_xlim(-0.5, replay.width - 0.5)
        ax.set_ylim(replay.height - 0.5, -0.5)
        ax.set_aspect("equal")
        ax.set_xticks(range(replay.width))
        ax.set_yticks(range(replay.height))
        ax.grid(True, linewidth=0.5)
        for index, pid in enumerate(sorted(frame.trails)):
            path = frame.trails[pid]
            xs = [p[0] for p in path]
            ys = [p[1] for p in path]
            color = colors[index % len(colors)]
            ax.plot(xs, ys, color=color, linewidth=2, label=f"{pid}: {replay.bot_names.get(pid, pid)}")
            ax.scatter(xs[-1], ys[-1], color=color, s=80)
        ax.set_title(f"turn={frame.turn}/{replay.turns} seed={replay.seed} reason={replay.end_reason}")
        ax.legend(loc="upper right")

    animation = FuncAnimation(fig, draw, frames=len(frames), interval=interval_ms, repeat=False)
    if output is not None:
        animation.save(output)
    if show:
        plt.show()
    else:
        plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tron_arena.visualize")
    parser.add_argument("replay")
    parser.add_argument("--animate", action="store_true")
    parser.add_argument("--interval-ms", type=int, default=150)
    parser.add_argument("--output", default=None)
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args(argv)

    replay = load_replay(args.replay)
    if args.animate:
        animate_replay(replay, interval_ms=args.interval_ms, output=args.output, show=not args.no_show)
    else:
        plot_replay(replay, output=args.output, show=not args.no_show)


if __name__ == "__main__":
    main()
