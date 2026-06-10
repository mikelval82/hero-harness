from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Set, Tuple, runtime_checkable

from benchmark.tron_arena.actions import Action, Direction, DIRECTION_DELTAS, resolve_direction


@dataclass
class GameConfig:
    seed: int
    width: int = 20
    height: int = 20
    max_turns: int = 200


@dataclass
class GameState:
    positions: Dict[int, Tuple[int, int]]
    directions: Dict[int, Direction]
    trails: Dict[int, Set[Tuple[int, int]]]
    alive: Dict[int, bool]
    turn: int
    game_over: bool = False
    winner: Optional[int] = None


@dataclass
class Observation:
    """Per-player view of the game state.

    Grid encoding (ADR-1): 0=empty, player_id+1 for trail/position cells.
    So player 0's cells are 1, player 1's cells are 2, etc.
    """
    grid: List[List[int]]
    player_id: int
    your_position: Tuple[int, int]
    your_direction: Direction
    opponent_positions: Dict[int, Tuple[int, int]]
    opponent_directions: Dict[int, Direction]
    turn: int
    width: int
    height: int


@runtime_checkable
class BotProtocol(Protocol):
    def __init__(self, player_id: int, seed: int) -> None: ...
    def choose_action(self, observation: Observation) -> Action: ...


@dataclass
class MatchResult:
    winner: Optional[int]
    turns: int
    end_reason: str
    action_history: List[Dict[int, Action]]
    invalid_counts: Dict[int, int]
    crash_counts: Dict[int, int]


def create_initial_state(config: GameConfig) -> GameState:
    positions = {
        0: (1, config.height // 2),
        1: (config.width - 2, config.height // 2),
    }
    directions = {
        0: Direction.RIGHT,
        1: Direction.LEFT,
    }
    trails = {pid: {pos} for pid, pos in positions.items()}
    alive = {pid: True for pid in positions}
    return GameState(
        positions=positions,
        directions=directions,
        trails=trails,
        alive=alive,
        turn=0,
    )


def build_observation(state: GameState, player_id: int, config: GameConfig) -> Observation:
    grid = [[0] * config.width for _ in range(config.height)]
    for pid, trail in state.trails.items():
        val = pid + 1
        for x, y in trail:
            if 0 <= x < config.width and 0 <= y < config.height:
                grid[y][x] = val
    for pid, pos in state.positions.items():
        if state.alive[pid]:
            x, y = pos
            if 0 <= x < config.width and 0 <= y < config.height:
                grid[y][x] = pid + 1

    opponent_positions = {
        pid: pos for pid, pos in state.positions.items()
        if pid != player_id and state.alive[pid]
    }
    opponent_directions = {
        pid: d for pid, d in state.directions.items()
        if pid != player_id and state.alive[pid]
    }

    return Observation(
        grid=grid,
        player_id=player_id,
        your_position=state.positions[player_id],
        your_direction=state.directions[player_id],
        opponent_positions=opponent_positions,
        opponent_directions=opponent_directions,
        turn=state.turn,
        width=config.width,
        height=config.height,
    )


def step(state: GameState, actions: Dict[int, Action], config: GameConfig) -> GameState:
    new_directions: Dict[int, Direction] = {}
    new_positions: Dict[int, Tuple[int, int]] = {}
    old_positions: Dict[int, Tuple[int, int]] = {}

    for pid in state.positions:
        if not state.alive[pid]:
            new_directions[pid] = state.directions[pid]
            new_positions[pid] = state.positions[pid]
            continue
        if pid not in actions:
            new_directions[pid] = state.directions[pid]
            new_positions[pid] = state.positions[pid]
            continue
        old_positions[pid] = state.positions[pid]
        new_dir = resolve_direction(state.directions[pid], actions[pid])
        new_directions[pid] = new_dir
        dx, dy = DIRECTION_DELTAS[new_dir]
        ox, oy = state.positions[pid]
        new_positions[pid] = (ox + dx, oy + dy)

    new_trails: Dict[int, Set[Tuple[int, int]]] = {
        pid: set(state.trails[pid]) for pid in state.trails
    }
    for pid, old_pos in old_positions.items():
        new_trails[pid].add(old_pos)

    new_alive: Dict[int, bool] = dict(state.alive)
    moved_pids = list(old_positions.keys())

    # (1) Wall collision
    for pid in moved_pids:
        x, y = new_positions[pid]
        if x < 0 or x >= config.width or y < 0 or y >= config.height:
            new_alive[pid] = False

    # (2) Trail collision
    for pid in moved_pids:
        if not new_alive[pid]:
            continue
        nx, ny = new_positions[pid]
        for trail in new_trails.values():
            if (nx, ny) in trail:
                new_alive[pid] = False
                break

    # (3) Head-to-head collision
    for i, pid_a in enumerate(moved_pids):
        if not new_alive[pid_a]:
            continue
        for pid_b in moved_pids[i + 1:]:
            if not new_alive[pid_b]:
                continue
            if new_positions[pid_a] == new_positions[pid_b]:
                new_alive[pid_a] = False
                new_alive[pid_b] = False

    # (4) Swap collision
    for i, pid_a in enumerate(moved_pids):
        for pid_b in moved_pids[i + 1:]:
            if pid_a in old_positions and pid_b in old_positions:
                if (new_positions[pid_a] == old_positions[pid_b]
                        and new_positions[pid_b] == old_positions[pid_a]):
                    new_alive[pid_a] = False
                    new_alive[pid_b] = False

    # Update positions for surviving moved players: add new position to trail
    for pid in moved_pids:
        if new_alive[pid]:
            new_trails[pid].add(new_positions[pid])

    new_turn = state.turn + 1

    # Determine game_over and winner
    alive_players = [pid for pid, a in new_alive.items() if a]
    game_over = False
    winner: Optional[int] = None

    if len(alive_players) == 0:
        game_over = True
        winner = None
    elif len(alive_players) == 1 and any(
        not new_alive[pid] and state.alive[pid] for pid in new_alive
    ):
        game_over = True
        winner = alive_players[0]
    elif new_turn >= config.max_turns:
        game_over = True
        winner = None

    return GameState(
        positions=new_positions,
        directions=new_directions,
        trails=new_trails,
        alive=new_alive,
        turn=new_turn,
        game_over=game_over,
        winner=winner,
    )


def run_match(
    config: GameConfig,
    bot_cls_a: type,
    bot_cls_b: type,
) -> MatchResult:
    state = create_initial_state(config)
    player_ids = sorted(state.positions.keys())
    bot_map = {player_ids[0]: bot_cls_a, player_ids[1]: bot_cls_b}

    bots: Dict[int, object] = {}
    for pid, cls in bot_map.items():
        bots[pid] = cls(pid, config.seed)

    action_history: List[Dict[int, Action]] = []
    invalid_counts: Dict[int, int] = {pid: 0 for pid in player_ids}
    crash_counts: Dict[int, int] = {pid: 0 for pid in player_ids}
    end_reason = ""

    while not state.game_over:
        turn_actions: Dict[int, Action] = {}
        dead_this_turn: Dict[int, bool] = {}

        for pid in player_ids:
            if not state.alive[pid]:
                continue
            obs = build_observation(state, pid, config)
            try:
                action = bots[pid].choose_action(obs)
            except Exception:
                crash_counts[pid] += 1
                dead_this_turn[pid] = True
                continue

            if not isinstance(action, Action):
                invalid_counts[pid] += 1
                dead_this_turn[pid] = True
                continue

            turn_actions[pid] = action

        action_history.append(dict(turn_actions))

        # Check if all alive players died from invalid/crash
        alive_before_step = [pid for pid in player_ids if state.alive[pid]]
        all_dead_from_errors = all(pid in dead_this_turn for pid in alive_before_step)

        if all_dead_from_errors:
            new_alive = dict(state.alive)
            for pid in dead_this_turn:
                new_alive[pid] = False
            state = GameState(
                positions=state.positions,
                directions=state.directions,
                trails={pid: set(t) for pid, t in state.trails.items()},
                alive=new_alive,
                turn=state.turn,
                game_over=True,
                winner=None,
            )
            end_reason = "all_invalid"
            break

        if dead_this_turn:
            # Some players died from invalid/crash, others are fine
            survivors = [pid for pid in alive_before_step if pid not in dead_this_turn]
            if len(survivors) == 1 and len(alive_before_step) > 1:
                new_alive = dict(state.alive)
                for pid in dead_this_turn:
                    new_alive[pid] = False
                state = GameState(
                    positions=state.positions,
                    directions=state.directions,
                    trails={pid: set(t) for pid, t in state.trails.items()},
                    alive=new_alive,
                    turn=state.turn,
                    game_over=True,
                    winner=survivors[0],
                )
                end_reason = "opponent_error"
                break

        # Mark players who had errors as dead in state before step
        if dead_this_turn:
            new_alive = dict(state.alive)
            for pid in dead_this_turn:
                new_alive[pid] = False
            state = GameState(
                positions=state.positions,
                directions=state.directions,
                trails={pid: set(t) for pid, t in state.trails.items()},
                alive=new_alive,
                turn=state.turn,
                game_over=state.game_over,
                winner=state.winner,
            )

        state = step(state, turn_actions, config)

        if state.game_over:
            if state.winner is not None:
                end_reason = "collision"
            elif state.turn >= config.max_turns:
                end_reason = "max_turns"
            else:
                end_reason = "draw"

    if not end_reason:
        end_reason = "unknown"

    return MatchResult(
        winner=state.winner,
        turns=state.turn,
        end_reason=end_reason,
        action_history=action_history,
        invalid_counts=invalid_counts,
        crash_counts=crash_counts,
    )
