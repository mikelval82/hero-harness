from __future__ import annotations

import copy

from benchmark.tron_arena.actions import Action, Direction
from benchmark.tron_arena.engine import (
    GameConfig,
    GameState,
    MatchResult,
    Observation,
    build_observation,
    create_initial_state,
    run_match,
    step,
)


class TestGameConfig:
    def test_defaults(self) -> None:
        c = GameConfig(seed=42)
        assert c.width == 20
        assert c.height == 20
        assert c.max_turns == 200
        assert c.seed == 42


class TestCreateInitialState:
    def test_positions_20x20(self) -> None:
        c = GameConfig(width=20, height=20, seed=1)
        s = create_initial_state(c)
        assert s.positions[0] == (1, 10)
        assert s.positions[1] == (18, 10)

    def test_directions(self) -> None:
        s = create_initial_state(GameConfig(seed=1))
        assert s.directions[0] == Direction.RIGHT
        assert s.directions[1] == Direction.LEFT

    def test_trails_contain_start(self) -> None:
        c = GameConfig(width=20, height=20, seed=1)
        s = create_initial_state(c)
        assert (1, 10) in s.trails[0]
        assert (18, 10) in s.trails[1]

    def test_alive(self) -> None:
        s = create_initial_state(GameConfig(seed=1))
        assert s.alive[0] is True
        assert s.alive[1] is True

    def test_turn_zero(self) -> None:
        s = create_initial_state(GameConfig(seed=1))
        assert s.turn == 0
        assert s.game_over is False
        assert s.winner is None

    def test_small_grid(self) -> None:
        c = GameConfig(width=5, height=5, seed=1)
        s = create_initial_state(c)
        assert s.positions[0] == (1, 2)
        assert s.positions[1] == (3, 2)


class TestBuildObservation:
    def test_grid_encoding(self) -> None:
        c = GameConfig(width=5, height=5, seed=1)
        s = create_initial_state(c)
        obs = build_observation(s, 0, c)
        assert obs.grid[2][1] == 1  # player 0 at (1, 2) -> pid+1=1
        assert obs.grid[2][3] == 2  # player 1 at (3, 2) -> pid+1=2

    def test_self_fields(self) -> None:
        c = GameConfig(width=5, height=5, seed=1)
        s = create_initial_state(c)
        obs = build_observation(s, 0, c)
        assert obs.player_id == 0
        assert obs.your_position == (1, 2)
        assert obs.your_direction == Direction.RIGHT
        assert 0 not in obs.opponent_positions
        assert 1 in obs.opponent_positions
        assert obs.opponent_positions[1] == (3, 2)
        assert obs.opponent_directions[1] == Direction.LEFT

    def test_dimensions(self) -> None:
        c = GameConfig(width=5, height=5, seed=1)
        s = create_initial_state(c)
        obs = build_observation(s, 0, c)
        assert obs.width == 5
        assert obs.height == 5
        assert obs.turn == 0


class TestStepPurity:
    def test_does_not_mutate_input(self) -> None:
        c = GameConfig(seed=1)
        s = create_initial_state(c)
        orig = copy.deepcopy(s)
        step(s, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        assert s.turn == orig.turn
        assert s.positions == orig.positions
        assert s.trails == orig.trails
        assert s.alive == orig.alive
        assert s.directions == orig.directions


class TestStepMovement:
    def test_straight_movement(self) -> None:
        c = GameConfig(width=20, height=20, seed=1)
        s = create_initial_state(c)
        s2 = step(s, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        assert s2.positions[0] == (2, 10)  # RIGHT from (1,10)
        assert s2.positions[1] == (17, 10)  # LEFT from (18,10)
        assert s2.turn == 1

    def test_turn_left(self) -> None:
        c = GameConfig(width=20, height=20, seed=1)
        s = create_initial_state(c)
        s2 = step(s, {0: Action.TURN_LEFT, 1: Action.TURN_LEFT}, c)
        # P0 facing RIGHT, turn_left -> UP, move (0,-1) from (1,10) -> (1,9)
        assert s2.positions[0] == (1, 9)
        assert s2.directions[0] == Direction.UP
        # P1 facing LEFT, turn_left -> DOWN, move (0,1) from (18,10) -> (18,11)
        assert s2.positions[1] == (18, 11)
        assert s2.directions[1] == Direction.DOWN


class TestWallCollision:
    def test_both_hit_wall(self) -> None:
        c = GameConfig(seed=1, width=5, height=5)
        state = GameState(
            positions={0: (0, 2), 1: (4, 2)},
            directions={0: Direction.LEFT, 1: Direction.RIGHT},
            trails={0: {(0, 2)}, 1: {(4, 2)}},
            alive={0: True, 1: True},
            turn=0,
        )
        s2 = step(state, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        assert not s2.alive[0]
        assert not s2.alive[1]
        assert s2.game_over
        assert s2.winner is None

    def test_one_hits_wall(self) -> None:
        c = GameConfig(seed=1, width=5, height=5)
        state = GameState(
            positions={0: (0, 2), 1: (3, 2)},
            directions={0: Direction.LEFT, 1: Direction.RIGHT},
            trails={0: {(0, 2)}, 1: {(3, 2)}},
            alive={0: True, 1: True},
            turn=0,
        )
        s2 = step(state, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        assert not s2.alive[0]
        assert s2.alive[1]
        assert s2.game_over
        assert s2.winner == 1


class TestTrailCollision:
    def test_hit_own_trail(self) -> None:
        c = GameConfig(seed=1, width=10, height=10)
        state = GameState(
            positions={0: (3, 5), 1: (8, 5)},
            directions={0: Direction.RIGHT, 1: Direction.LEFT},
            trails={0: {(3, 5), (4, 5)}, 1: {(8, 5)}},
            alive={0: True, 1: True},
            turn=0,
        )
        s2 = step(state, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        # P0 moves to (4,5) which is in P0's trail
        assert not s2.alive[0]
        assert s2.alive[1]

    def test_hit_opponent_trail(self) -> None:
        c = GameConfig(seed=1, width=10, height=10)
        state = GameState(
            positions={0: (3, 5), 1: (5, 5)},
            directions={0: Direction.RIGHT, 1: Direction.UP},
            trails={0: {(3, 5)}, 1: {(5, 5), (4, 5)}},
            alive={0: True, 1: True},
            turn=0,
        )
        s2 = step(state, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        # P0 moves to (4,5) which is in P1's trail -> P0 dies
        # P1 moves to (5,4) which is clear -> P1 survives
        assert not s2.alive[0]
        assert s2.alive[1]


class TestHeadToHeadCollision:
    def test_same_cell(self) -> None:
        c = GameConfig(seed=1, width=10, height=10)
        state = GameState(
            positions={0: (3, 5), 1: (5, 5)},
            directions={0: Direction.RIGHT, 1: Direction.LEFT},
            trails={0: {(3, 5)}, 1: {(5, 5)}},
            alive={0: True, 1: True},
            turn=0,
        )
        s2 = step(state, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        # Both move to (4, 5)
        assert not s2.alive[0]
        assert not s2.alive[1]
        assert s2.game_over
        assert s2.winner is None


class TestSwapCollision:
    def test_swap_positions(self) -> None:
        c = GameConfig(seed=1, width=10, height=10)
        state = GameState(
            positions={0: (3, 5), 1: (4, 5)},
            directions={0: Direction.RIGHT, 1: Direction.LEFT},
            trails={0: {(3, 5)}, 1: {(4, 5)}},
            alive={0: True, 1: True},
            turn=0,
        )
        s2 = step(state, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        # P0 moves to (4,5), P1 moves to (3,5) — swap!
        assert not s2.alive[0]
        assert not s2.alive[1]
        assert s2.game_over
        assert s2.winner is None


class TestMaxTurns:
    def test_max_turns_draw(self) -> None:
        c = GameConfig(width=20, height=20, max_turns=3, seed=1)
        s = create_initial_state(c)
        s = step(s, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        assert not s.game_over
        s = step(s, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        assert not s.game_over
        s = step(s, {0: Action.STRAIGHT, 1: Action.STRAIGHT}, c)
        assert s.game_over
        assert s.winner is None
        assert s.turn == 3


class TestRunMatch:
    def test_determinism(self) -> None:
        class StraightBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                return Action.STRAIGHT

        c = GameConfig(seed=42)
        r1 = run_match(c, StraightBot, StraightBot)
        r2 = run_match(c, StraightBot, StraightBot)
        assert r1.winner == r2.winner
        assert r1.turns == r2.turns

    def test_invalid_action_loses(self) -> None:
        class GoodBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                return Action.STRAIGHT

        class BadBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                return 42  # type: ignore[return-value]

        c = GameConfig(seed=1)
        r = run_match(c, BadBot, GoodBot)
        assert r.winner == 1
        assert r.invalid_counts[0] == 1

    def test_crash_loses(self) -> None:
        class GoodBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                return Action.STRAIGHT

        class CrashBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                raise ValueError("boom")

        c = GameConfig(seed=1)
        r = run_match(c, GoodBot, CrashBot)
        assert r.winner == 0
        assert r.crash_counts[1] == 1

    def test_both_invalid_draw(self) -> None:
        class BadBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                return "nope"  # type: ignore[return-value]

        c = GameConfig(seed=1)
        r = run_match(c, BadBot, BadBot)
        assert r.winner is None

    def test_max_turns_via_run_match(self) -> None:
        class StraightBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                return Action.STRAIGHT

        c = GameConfig(width=20, height=20, max_turns=5, seed=1)
        r = run_match(c, StraightBot, StraightBot)
        assert r.winner is None
        assert r.turns == 5
        assert r.end_reason == "max_turns"

    def test_match_result_has_action_history(self) -> None:
        class StraightBot:
            def __init__(self, pid: int, seed: int) -> None:
                pass
            def choose_action(self, obs: Observation) -> Action:
                return Action.STRAIGHT

        c = GameConfig(width=20, height=20, max_turns=3, seed=1)
        r = run_match(c, StraightBot, StraightBot)
        assert len(r.action_history) == 3
        for turn_actions in r.action_history:
            assert 0 in turn_actions
            assert 1 in turn_actions
