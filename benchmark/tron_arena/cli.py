from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Tuple

from benchmark.tron_arena.bots import BASELINE_BOTS
from benchmark.tron_arena.engine import GameConfig, run_match
from benchmark.tron_arena.metrics import match_metrics_from_result
from benchmark.tron_arena.replay import replay_from_match, replay_hash, save_replay
from benchmark.tron_arena.tournament import run_tournament


def resolve_bot(specifier: str) -> Tuple[str, type]:
    if specifier.endswith(".py"):
        if not os.path.isfile(specifier):
            print(f"Error: bot file not found: {specifier}", file=sys.stderr)
            sys.exit(1)
        mod_name = os.path.splitext(os.path.basename(specifier))[0]
        spec = importlib.util.spec_from_file_location(mod_name, specifier)
        if spec is None or spec.loader is None:
            print(f"Error: cannot load bot file: {specifier}", file=sys.stderr)
            sys.exit(1)
        module = importlib.util.module_from_spec(spec)
        # Register the module in sys.modules before executing it so that tools
        # relying on `sys.modules[cls.__module__]` work — notably @dataclass,
        # whose type resolution looks the module up there. Without this, any bot
        # file that defines a dataclass fails to import.
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            sys.modules.pop(mod_name, None)
            print(f"Error: failed to import bot file {specifier}: {e}", file=sys.stderr)
            sys.exit(1)
        if not hasattr(module, "Bot"):
            print(f"Error: bot file {specifier} does not define a 'Bot' class", file=sys.stderr)
            sys.exit(1)
        return (mod_name, module.Bot)

    if specifier in BASELINE_BOTS:
        return (specifier, BASELINE_BOTS[specifier])

    print(f"Error: unrecognized bot '{specifier}'. Available baselines: {', '.join(sorted(BASELINE_BOTS))}", file=sys.stderr)
    sys.exit(1)


def _add_grid_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--width", type=int, default=20)
    parser.add_argument("--height", type=int, default=20)
    parser.add_argument("--max-turns", type=int, default=200)


def _safe_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tron_arena")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    match_parser = subparsers.add_parser("match")
    match_parser.add_argument("--bot-a", required=True)
    match_parser.add_argument("--bot-b", required=True)
    match_parser.add_argument("--seed", type=int, required=True)
    match_parser.add_argument("--replay-out", default=None)
    match_parser.add_argument("--include-replay", action="store_true")
    _add_grid_args(match_parser)

    tournament_parser = subparsers.add_parser("tournament")
    tournament_parser.add_argument("--bots", required=True)
    tournament_parser.add_argument("--seeds", required=True)
    tournament_parser.add_argument("--replay-dir", default=None)
    _add_grid_args(tournament_parser)

    args = parser.parse_args(argv)

    if args.command == "match":
        name_a, cls_a = resolve_bot(args.bot_a)
        name_b, cls_b = resolve_bot(args.bot_b)
        config = GameConfig(
            seed=args.seed,
            width=args.width,
            height=args.height,
            max_turns=args.max_turns,
        )
        result = run_match(config, cls_a, cls_b)
        bot_names = {0: name_a, 1: name_b}
        replay = replay_from_match(config, result, bot_names)
        hash_val = replay_hash(replay)
        metrics = match_metrics_from_result(result, args.seed, bot_names, replay_hash=hash_val)
        payload = metrics.to_dict()
        if args.replay_out is not None:
            save_replay(replay, args.replay_out)
            payload["replay_path"] = str(args.replay_out)
        if args.include_replay:
            from benchmark.tron_arena.replay import replay_to_dict
            payload["replay"] = replay_to_dict(replay)
        print(json.dumps(payload, indent=2))

    elif args.command == "tournament":
        bot_specs = [s.strip() for s in args.bots.split(",") if s.strip()]
        seed_strs = [s.strip() for s in args.seeds.split(",") if s.strip()]
        if not bot_specs:
            print("Error: --bots must not be empty", file=sys.stderr)
            sys.exit(1)
        if not seed_strs:
            print("Error: --seeds must not be empty", file=sys.stderr)
            sys.exit(1)
        bots = [resolve_bot(s) for s in bot_specs]
        seeds = []
        for s in seed_strs:
            try:
                seeds.append(int(s))
            except ValueError:
                print(f"Error: invalid seed value '{s}'", file=sys.stderr)
                sys.exit(1)
        replay_dir = Path(args.replay_dir) if args.replay_dir else None
        if replay_dir is None:
            _, tournament_result = run_tournament(
                bots, seeds,
                width=args.width,
                height=args.height,
                max_turns=args.max_turns,
            )
            print(json.dumps(tournament_result.to_dict(), indent=2))
            return

        replay_dir.mkdir(parents=True, exist_ok=True)
        all_metrics = []
        matches = []
        match_index = 0
        for seed in seeds:
            config = GameConfig(seed=seed, width=args.width, height=args.height, max_turns=args.max_turns)
            for i, (name_a, cls_a) in enumerate(bots):
                for j, (name_b, cls_b) in enumerate(bots):
                    if i == j:
                        continue
                    match_index += 1
                    result = run_match(config, cls_a, cls_b)
                    bot_names = {0: name_a, 1: name_b}
                    replay = replay_from_match(config, result, bot_names)
                    hash_val = replay_hash(replay)
                    metrics = match_metrics_from_result(result, seed, bot_names, replay_hash=hash_val)
                    all_metrics.append(metrics)
                    filename = (
                        f"match_{match_index:04d}_seed_{seed}_"
                        f"{_safe_name(name_a)}_vs_{_safe_name(name_b)}.json"
                    )
                    replay_path = replay_dir / filename
                    save_replay(replay, replay_path)
                    matches.append({
                        "match_id": f"{match_index:04d}",
                        "seed": seed,
                        "bot_names": {str(k): v for k, v in bot_names.items()},
                        "replay_path": filename,
                        "replay_hash": hash_val,
                        "metrics": metrics.to_dict(),
                    })

        from benchmark.tron_arena.metrics import aggregate_results
        tournament_result = aggregate_results(all_metrics)
        summary = {
            "version": "1",
            "bots": [name for name, _ in bots],
            "seeds": seeds,
            "width": args.width,
            "height": args.height,
            "max_turns": args.max_turns,
            "matches": matches,
            "summary": tournament_result.to_dict(),
        }
        summary_path = replay_dir / "tournament_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload = tournament_result.to_dict()
        payload["replay_dir"] = str(replay_dir)
        payload["summary_path"] = str(summary_path)
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
