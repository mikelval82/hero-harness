# Tron Arena Benchmark

A deterministic two-player Tron game engine for benchmarking bot strategies.
Two bots compete on a rectangular grid, each leaving a permanent trail.
A bot loses when it hits a wall, any trail, or returns an invalid action.

## Quick Start

Run a single match:

```bash
python -m benchmark.tron_arena match \
  --bot-a greedy_space --bot-b random_legal --seed 42
```

Run a round-robin tournament:

```bash
python -m benchmark.tron_arena tournament \
  --bots random_legal,straight_until_blocked,greedy_space,always_left \
  --seeds 1,2,3
```

Both commands print JSON to stdout.

## CLI Reference

### `match`

```
python -m benchmark.tron_arena match --bot-a BOT --bot-b BOT --seed INT
    [--width 20] [--height 20] [--max-turns 200]
    [--replay-out replay.json] [--include-replay]
```

Runs a single match. Outputs a `MatchMetrics` JSON object with fields:
`seed`, `bot_names`, `winner`, `turns`, `end_reason`, `invalid_counts`,
`crash_counts`, `timeout_counts`, `replay_hash`.

Optional replay flags:

| Flag | Meaning |
|---|---|
| `--replay-out PATH` | Write the full replay JSON to `PATH`. |
| `--include-replay` | Include the full replay object in stdout JSON. |

### `tournament`

```
python -m benchmark.tron_arena tournament --bots BOT,BOT,... --seeds INT,INT,...
    [--width 20] [--height 20] [--max-turns 200]
    [--replay-dir DIR]
```

Runs every ordered pair of bots against each other for every seed
(N×(N−1) matches per seed). Outputs a `TournamentResult` JSON object with
fields: `bot_names`, `matches_played`, `wins`, `losses`, `draws`,
`win_rates`, `avg_survival_turns`, `illegal_counts`, `crash_counts`,
`timeout_counts`.

When `--replay-dir DIR` is provided, the command writes one replay JSON per
match plus `tournament_summary.json`. The stdout JSON also includes
`replay_dir` and `summary_path`.

### Replay visualization

```bash
python -m benchmark.tron_arena.visualize replay.json
python -m benchmark.tron_arena.visualize replay.json --output replay.png --no-show
python -m benchmark.tron_arena.visualize replay.json --animate
```

Visualization uses `matplotlib` if installed. The core benchmark remains
stdlib-only; replay generation and tests do not require matplotlib.

### Bot specifiers

| Form | Meaning |
|---|---|
| `random_legal` | Built-in baseline bot name |
| `path/to/my_bot.py` | External Python file exporting a `Bot` class |

External bot files must define a top-level `Bot` class that satisfies
`BotProtocol` (see below).

## Bot API

A bot is any class with this signature:

```python
class Bot:
    def __init__(self, player_id: int, seed: int) -> None:
        ...

    def choose_action(self, observation: Observation) -> Action:
        ...
```

This matches the `BotProtocol` defined in `engine.py` (structural typing via
`typing.Protocol` — no inheritance required).

### `Action` enum

Defined in `actions.py`:

| Value | String |
|---|---|
| `Action.STRAIGHT` | `"straight"` |
| `Action.TURN_LEFT` | `"turn_left"` |
| `Action.TURN_RIGHT` | `"turn_right"` |

Actions are relative to the bot's current facing direction.

### `Observation` dataclass

Passed to `choose_action` each turn:

| Field | Type | Description |
|---|---|---|
| `grid` | `List[List[int]]` | 2D grid indexed as `grid[y][x]`. `0` = empty, `pid+1` = trail/head. |
| `player_id` | `int` | Your player id (0 or 1). |
| `your_position` | `Tuple[int, int]` | Your `(x, y)` position. |
| `your_direction` | `Direction` | Your current facing direction. |
| `opponent_positions` | `Dict[int, Tuple[int, int]]` | Alive opponents' positions. |
| `opponent_directions` | `Dict[int, Direction]` | Alive opponents' directions. |
| `turn` | `int` | Current turn number (0-based). |
| `width` | `int` | Grid width. |
| `height` | `int` | Grid height. |

### `Direction` enum

Defined in `actions.py`:

| Value | Delta (dx, dy) |
|---|---|
| `Direction.UP` | `(0, -1)` |
| `Direction.DOWN` | `(0, 1)` |
| `Direction.LEFT` | `(-1, 0)` |
| `Direction.RIGHT` | `(1, 0)` |

Coordinate system: x increases rightward, y increases downward. Origin `(0, 0)` is the top-left corner.

### Error handling

- If `choose_action` raises an exception, the bot is marked as crashed and dies that turn.
- If `choose_action` returns a value that is not an `Action`, the bot is marked as invalid and dies that turn.
- If both bots error on the same turn, the match is a draw with `end_reason = "all_invalid"`.

### Seed usage

The `seed` parameter passed to `__init__` is the match seed. Bots may use it
to initialize a `random.Random(seed)` instance for deterministic randomness.
Do not use `random.random()` or other global RNG — it breaks determinism.

## Grid Rules

- **Grid size**: configurable, default 20×20.
- **Walls**: the grid boundary. Moving outside `[0, width) × [0, height)` is a wall collision.
- **Trails**: every cell a bot has occupied becomes part of its permanent trail.
- **Grid encoding**: `0` = empty, `player_id + 1` = that player's trail or head. Player 0's cells are `1`, player 1's cells are `2`.

### Initial positions

Fixed symmetric placement (not randomized):

- Player 0 starts at `(1, height // 2)` facing `RIGHT`.
- Player 1 starts at `(width - 2, height // 2)` facing `LEFT`.

### Turn resolution

Each turn is simultaneous:

1. Both alive bots receive an `Observation` and return an `Action`.
2. Old positions are added to trails.
3. New positions are computed from the action.
4. Collision checks run in order: wall → trail → head-to-head → swap.
5. Surviving bots' new positions are added to their trails.

### Collision types

| Type | Condition | Result |
|---|---|---|
| Wall | New position outside grid bounds | Bot dies |
| Trail | New position on any trail cell | Bot dies |
| Head-to-head | Both bots move to the same cell | Both die |
| Swap | Bots swap positions (A→B's old, B→A's old) | Both die |

### Game over conditions

- **Single survivor**: the surviving bot wins (`end_reason = "collision"`).
- **Both die same turn**: draw (`end_reason = "draw"`).
- **Max turns reached**: draw (`end_reason = "max_turns"`).
- **Both error same turn**: draw (`end_reason = "all_invalid"`).
- **One errors, one alive**: survivor wins (`end_reason = "opponent_error"`).

## Baseline Bots

| Name | Strategy |
|---|---|
| `random_legal` | Picks a random legal action using seeded RNG. |
| `straight_until_blocked` | Goes straight if legal, otherwise tries left then right. |
| `greedy_space` | Picks the legal action leading to the largest flood-fill region. |
| `always_left` | Always returns `TURN_LEFT`. Weak calibration baseline. |

Action tie-breaking priority (where applicable): `STRAIGHT`, `TURN_LEFT`, `TURN_RIGHT`.

## Determinism Guarantees

Given the same `seed`, grid dimensions, `max_turns`, and bot classes:

1. **Initial state** is deterministic (fixed symmetric positions, no seed randomization).
2. **Turn order** is deterministic (player ids processed in sorted order).
3. **Bot RNG** is deterministic when bots use `random.Random(seed)`.
4. **Collision resolution** is deterministic (wall → trail → head-to-head → swap, always in that order).
5. **Replay hash** is a SHA-256 of canonical JSON (`sort_keys=True`, compact separators), stable across runs.

The `match` CLI command with identical arguments always produces identical JSON output, including the same `replay_hash`.

## Replay Format

Each match produces a `Replay` (via `replay.py`) with:

| Field | Type | Description |
|---|---|---|
| `version` | `str` | Format version (`"1"`). |
| `seed` | `int` | Match seed. |
| `width` | `int` | Grid width. |
| `height` | `int` | Grid height. |
| `max_turns` | `int` | Turn limit. |
| `initial_positions` | `Dict[int, Tuple[int, int]]` | Starting `(x, y)` per player. |
| `initial_directions` | `Dict[int, Direction]` | Starting direction per player. |
| `bot_names` | `Dict[int, str]` | Bot name per player. |
| `action_history` | `List[Dict[int, Action]]` | Per-turn actions. |
| `winner` | `Optional[int]` | Winner player id, or `null` for draw. |
| `turns` | `int` | Total turns played. |
| `end_reason` | `str` | Why the match ended. |

The replay hash is `SHA-256(canonical_json(replay))` where canonical JSON uses
`sort_keys=True, separators=(",", ":")` for compact, deterministic output.

Write a replay from the CLI:

```bash
python -m benchmark.tron_arena match \
  --bot-a greedy_space --bot-b random_legal --seed 1 \
  --replay-out replay.json
```

Write all tournament replays:

```bash
python -m benchmark.tron_arena tournament \
  --bots greedy_space,random_legal,straight_until_blocked \
  --seeds 1,2,3 \
  --replay-dir replays/run_001
```

## Package Structure

```
benchmark/tron_arena/
  __init__.py
  __main__.py       # Entry point: python -m benchmark.tron_arena
  actions.py        # Direction, Action enums and resolve_direction
  bots.py           # BotProtocol, baseline bots, BASELINE_BOTS registry
  cli.py            # CLI: match and tournament subcommands
  engine.py         # GameConfig, GameState, Observation, step, run_match
  metrics.py        # MatchMetrics, TournamentResult, aggregation
  replay.py         # Replay dataclass, JSON serialization, SHA-256 hash
  tournament.py     # Round-robin tournament runner
  visualize.py      # Matplotlib replay plotting and animation
  README.md         # This file
  tests/
    __init__.py
    conftest.py     # Shared test fixtures
    test_actions.py
    test_bots.py
    test_cli.py
    test_engine.py
    test_metrics.py
    test_replay.py
    test_tournament.py
    test_visualize.py
```

## Running Tests

```bash
python -m pytest benchmark/tron_arena/tests/ -x -q
```

## Examples

### Single match with JSON output

```bash
python -m benchmark.tron_arena match \
  --bot-a greedy_space --bot-b random_legal --seed 1
```

Output (truncated):

```json
{
  "seed": 1,
  "bot_names": {"0": "greedy_space", "1": "random_legal"},
  "winner": 0,
  "turns": 42,
  "end_reason": "collision",
  "replay_hash": "a1b2c3..."
}
```

### Save and visualize a replay

```bash
python -m benchmark.tron_arena match \
  --bot-a greedy_space --bot-b random_legal --seed 1 \
  --replay-out replay.json

python -m benchmark.tron_arena.visualize replay.json --output replay.png --no-show
```

### Tournament across multiple seeds

```bash
python -m benchmark.tron_arena tournament \
  --bots greedy_space,random_legal,straight_until_blocked \
  --seeds 1,2,3,4,5 \
  --replay-dir replays/run_001
```

Output (truncated):

```json
{
  "bot_names": ["greedy_space", "random_legal", "straight_until_blocked"],
  "matches_played": 30,
  "wins": {"greedy_space": 20, "random_legal": 3, "straight_until_blocked": 5},
  "win_rates": {"greedy_space": 0.67, "random_legal": 0.1, "straight_until_blocked": 0.17}
}
```

### Custom grid size

```bash
python -m benchmark.tron_arena match \
  --bot-a always_left --bot-b straight_until_blocked \
  --seed 7 --width 10 --height 10 --max-turns 50
```

### External bot file

Create `my_bot.py`:

```python
from benchmark.tron_arena.actions import Action
from benchmark.tron_arena.engine import Observation


class Bot:
    def __init__(self, player_id: int, seed: int) -> None:
        self.pid = player_id

    def choose_action(self, observation: Observation) -> Action:
        return Action.STRAIGHT
```

Run it:

```bash
python -m benchmark.tron_arena match \
  --bot-a my_bot.py --bot-b greedy_space --seed 1
```
