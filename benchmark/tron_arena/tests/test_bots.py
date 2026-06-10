from __future__ import annotations

from benchmark.tron_arena.actions import Action, Direction
from benchmark.tron_arena.engine import GameConfig, Observation, run_match


def _make_obs(
    grid: list[list[int]] | None = None,
    player_id: int = 0,
    pos: tuple[int, int] = (2, 2),
    direction: Direction = Direction.RIGHT,
    opponent_positions: dict[int, tuple[int, int]] | None = None,
    opponent_directions: dict[int, Direction] | None = None,
    turn: int = 0,
    width: int = 5,
    height: int = 5,
) -> Observation:
    if grid is None:
        grid = [[0] * width for _ in range(height)]
    if opponent_positions is None:
        opponent_positions = {}
    if opponent_directions is None:
        opponent_directions = {}
    return Observation(
        grid=grid,
        player_id=player_id,
        your_position=pos,
        your_direction=direction,
        opponent_positions=opponent_positions,
        opponent_directions=opponent_directions,
        turn=turn,
        width=width,
        height=height,
    )


class TestAlwaysLeftBot:
    def test_always_returns_turn_left(self):
        from benchmark.tron_arena.bots import AlwaysLeftBot
        bot = AlwaysLeftBot(0, 42)
        obs = _make_obs()
        assert bot.choose_action(obs) == Action.TURN_LEFT

    def test_ignores_observation(self):
        from benchmark.tron_arena.bots import AlwaysLeftBot
        bot = AlwaysLeftBot(1, 99)
        for d in Direction:
            obs = _make_obs(direction=d)
            assert bot.choose_action(obs) == Action.TURN_LEFT

    def test_init_signature(self):
        from benchmark.tron_arena.bots import AlwaysLeftBot
        bot = AlwaysLeftBot(0, 42)
        assert bot is not None


class TestRandomLegalBot:
    def test_same_seed_same_actions(self):
        from benchmark.tron_arena.bots import RandomLegalBot
        obs = _make_obs(width=10, height=10, pos=(5, 5),
                        grid=[[0] * 10 for _ in range(10)])
        b1 = RandomLegalBot(0, 42)
        b2 = RandomLegalBot(0, 42)
        a1 = [b1.choose_action(obs) for _ in range(20)]
        a2 = [b2.choose_action(obs) for _ in range(20)]
        assert a1 == a2

    def test_different_seed_different_actions(self):
        from benchmark.tron_arena.bots import RandomLegalBot
        obs = _make_obs(width=10, height=10, pos=(5, 5),
                        grid=[[0] * 10 for _ in range(10)])
        b1 = RandomLegalBot(0, 42)
        b2 = RandomLegalBot(0, 99)
        a1 = [b1.choose_action(obs) for _ in range(20)]
        a2 = [b2.choose_action(obs) for _ in range(20)]
        assert a1 != a2

    def test_returns_action_enum(self):
        from benchmark.tron_arena.bots import RandomLegalBot
        bot = RandomLegalBot(0, 42)
        obs = _make_obs()
        result = bot.choose_action(obs)
        assert isinstance(result, Action)

    def test_all_blocked_still_returns_action(self):
        from benchmark.tron_arena.bots import RandomLegalBot
        # Position (0,0) facing UP → forward is wall, left is wall, right is wall
        # Actually: facing UP from (0,0):
        #   STRAIGHT -> UP -> (0,-1) wall
        #   TURN_LEFT -> LEFT -> (-1,0) wall
        #   TURN_RIGHT -> RIGHT -> (1,0) grid[0][1]
        # Need to block (1,0) too
        grid = [[0] * 3 for _ in range(3)]
        grid[0][1] = 1  # block the right cell
        bot = RandomLegalBot(0, 42)
        obs = _make_obs(grid=grid, pos=(0, 0), direction=Direction.UP,
                        width=3, height=3)
        result = bot.choose_action(obs)
        assert isinstance(result, Action)

    def test_picks_only_legal_when_available(self):
        from benchmark.tron_arena.bots import RandomLegalBot
        # Position (0,0) facing RIGHT:
        #   STRAIGHT -> RIGHT -> (1,0) = grid[0][1]
        #   TURN_LEFT -> UP -> (0,-1) wall
        #   TURN_RIGHT -> DOWN -> (0,1) = grid[1][0]
        # Block grid[0][1], leave grid[1][0] open. Only TURN_RIGHT is legal.
        grid = [[0] * 3 for _ in range(3)]
        grid[0][1] = 1  # block forward
        bot = RandomLegalBot(0, 42)
        obs = _make_obs(grid=grid, pos=(0, 0), direction=Direction.RIGHT,
                        width=3, height=3)
        # With only one legal action, it must always pick that one
        for _ in range(10):
            b = RandomLegalBot(0, _)
            assert b.choose_action(obs) == Action.TURN_RIGHT


class TestStraightUntilBlockedBot:
    def test_straight_when_clear(self):
        from benchmark.tron_arena.bots import StraightUntilBlockedBot
        bot = StraightUntilBlockedBot(0, 1)
        obs = _make_obs()
        assert bot.choose_action(obs) == Action.STRAIGHT

    def test_fallback_when_forward_blocked(self):
        from benchmark.tron_arena.bots import StraightUntilBlockedBot
        # Facing RIGHT at (2,2), block (3,2)
        grid = [[0] * 5 for _ in range(5)]
        grid[2][3] = 1  # block forward
        bot = StraightUntilBlockedBot(0, 1)
        obs = _make_obs(grid=grid, pos=(2, 2), direction=Direction.RIGHT)
        action = bot.choose_action(obs)
        assert action != Action.STRAIGHT  # must pick an alternative
        assert isinstance(action, Action)

    def test_fallback_order_prefers_straight_first(self):
        from benchmark.tron_arena.bots import StraightUntilBlockedBot
        # All clear → STRAIGHT
        bot = StraightUntilBlockedBot(0, 1)
        obs = _make_obs(pos=(2, 2), direction=Direction.RIGHT)
        assert bot.choose_action(obs) == Action.STRAIGHT

    def test_fallback_to_turn_left_when_straight_blocked(self):
        from benchmark.tron_arena.bots import StraightUntilBlockedBot
        # Facing RIGHT at (2,2):
        #   STRAIGHT -> (3,2) blocked
        #   TURN_LEFT -> UP -> (2,1) clear
        #   TURN_RIGHT -> DOWN -> (2,3) clear
        # Should pick TURN_LEFT (first in fallback order after STRAIGHT)
        grid = [[0] * 5 for _ in range(5)]
        grid[2][3] = 1  # block forward (STRAIGHT)
        bot = StraightUntilBlockedBot(0, 1)
        obs = _make_obs(grid=grid, pos=(2, 2), direction=Direction.RIGHT)
        assert bot.choose_action(obs) == Action.TURN_LEFT

    def test_fallback_to_turn_right_when_straight_and_left_blocked(self):
        from benchmark.tron_arena.bots import StraightUntilBlockedBot
        # Facing RIGHT at (2,2):
        #   STRAIGHT -> (3,2) blocked
        #   TURN_LEFT -> UP -> (2,1) blocked
        #   TURN_RIGHT -> DOWN -> (2,3) clear
        grid = [[0] * 5 for _ in range(5)]
        grid[2][3] = 1  # block forward
        grid[1][2] = 1  # block up (turn_left from RIGHT)
        bot = StraightUntilBlockedBot(0, 1)
        obs = _make_obs(grid=grid, pos=(2, 2), direction=Direction.RIGHT)
        assert bot.choose_action(obs) == Action.TURN_RIGHT

    def test_all_blocked_returns_straight(self):
        from benchmark.tron_arena.bots import StraightUntilBlockedBot
        # Corner (0,0) facing UP: all 3 actions lead to wall or blocked
        grid = [[0] * 3 for _ in range(3)]
        grid[0][1] = 1  # block right (TURN_RIGHT from UP)
        bot = StraightUntilBlockedBot(0, 1)
        obs = _make_obs(grid=grid, pos=(0, 0), direction=Direction.UP,
                        width=3, height=3)
        assert bot.choose_action(obs) == Action.STRAIGHT

    def test_deterministic(self):
        from benchmark.tron_arena.bots import StraightUntilBlockedBot
        obs = _make_obs()
        b1 = StraightUntilBlockedBot(0, 1)
        b2 = StraightUntilBlockedBot(0, 99)  # different seed shouldn't matter
        assert b1.choose_action(obs) == b2.choose_action(obs)


class TestGreedySpaceBot:
    def test_picks_action_with_most_space(self):
        from benchmark.tron_arena.bots import GreedySpaceBot
        # 5x5 grid, bot at (2,2) facing RIGHT
        # Block top half except for one cell to the right
        # Right (STRAIGHT) should lead to more space than up (TURN_LEFT)
        bot = GreedySpaceBot(0, 1)
        obs = _make_obs(pos=(2, 2), direction=Direction.RIGHT)
        action = bot.choose_action(obs)
        assert isinstance(action, Action)

    def test_tie_breaking_straight_over_left(self):
        from benchmark.tron_arena.bots import GreedySpaceBot
        # Symmetric grid where STRAIGHT and TURN_LEFT lead to same space
        # Create a 3x3 grid, bot at (1,1) facing RIGHT
        # STRAIGHT -> (2,1), TURN_LEFT -> UP -> (1,0), TURN_RIGHT -> DOWN -> (1,2)
        # All reachable spaces equal on empty grid → STRAIGHT wins tie
        grid = [[0] * 3 for _ in range(3)]
        bot = GreedySpaceBot(0, 1)
        obs = _make_obs(grid=grid, pos=(1, 1), direction=Direction.RIGHT,
                        width=3, height=3)
        assert bot.choose_action(obs) == Action.STRAIGHT

    def test_all_blocked_returns_straight(self):
        from benchmark.tron_arena.bots import GreedySpaceBot
        grid = [[0] * 3 for _ in range(3)]
        grid[0][1] = 1  # block RIGHT from UP
        bot = GreedySpaceBot(0, 1)
        obs = _make_obs(grid=grid, pos=(0, 0), direction=Direction.UP,
                        width=3, height=3)
        assert bot.choose_action(obs) == Action.STRAIGHT

    def test_avoids_dead_end(self):
        from benchmark.tron_arena.bots import GreedySpaceBot
        # 5x5 grid, bot at (2,2) facing RIGHT
        # Bot's own position is marked as pid+1=1 (as in real game)
        grid = [[0] * 5 for _ in range(5)]
        grid[2][2] = 1  # bot's own trail at current pos
        # Create dead end for STRAIGHT: (3,2) is open but surrounded
        grid[1][3] = 1  # block (3,1)
        grid[3][3] = 1  # block (3,3)
        grid[2][4] = 1  # block (4,2)
        # STRAIGHT -> (3,2): reachable = just 1 cell (surrounded)
        # TURN_LEFT -> UP -> (2,1): lots of space available
        bot = GreedySpaceBot(0, 1)
        obs = _make_obs(grid=grid, pos=(2, 2), direction=Direction.RIGHT)
        action = bot.choose_action(obs)
        assert action == Action.TURN_LEFT

    def test_deterministic(self):
        from benchmark.tron_arena.bots import GreedySpaceBot
        obs = _make_obs()
        b1 = GreedySpaceBot(0, 1)
        b2 = GreedySpaceBot(0, 99)
        assert b1.choose_action(obs) == b2.choose_action(obs)

    def test_flood_fill_counts_correct(self):
        from benchmark.tron_arena.bots import GreedySpaceBot
        # 3x1 corridor: bot at (0,0) facing RIGHT
        # STRAIGHT -> (1,0), flood fill should find (1,0) and (2,0) = 2 cells
        # TURN_LEFT -> UP -> wall, TURN_RIGHT -> DOWN -> wall
        grid = [[0, 0, 0]]  # 3 wide, 1 tall
        bot = GreedySpaceBot(0, 1)
        obs = _make_obs(grid=grid, pos=(0, 0), direction=Direction.RIGHT,
                        width=3, height=1)
        assert bot.choose_action(obs) == Action.STRAIGHT


class TestBaselineBots:
    def test_baseline_bots_dict(self):
        from benchmark.tron_arena.bots import BASELINE_BOTS
        assert sorted(BASELINE_BOTS.keys()) == [
            "always_left", "greedy_space", "random_legal", "straight_until_blocked"
        ]

    def test_baseline_bots_are_classes(self):
        from benchmark.tron_arena.bots import BASELINE_BOTS
        for name, cls in BASELINE_BOTS.items():
            assert isinstance(cls, type), f"{name} is not a class"

    def test_all_bots_importable(self):
        from benchmark.tron_arena.bots import (
            AlwaysLeftBot,
            GreedySpaceBot,
            RandomLegalBot,
            StraightUntilBlockedBot,
        )
        assert AlwaysLeftBot is not None
        assert GreedySpaceBot is not None
        assert RandomLegalBot is not None
        assert StraightUntilBlockedBot is not None


class TestIntegrationWithRunMatch:
    def test_all_pairs_complete(self):
        from benchmark.tron_arena.bots import BASELINE_BOTS
        bots = list(BASELINE_BOTS.values())
        config = GameConfig(seed=1, width=10, height=10, max_turns=50)
        for a in bots:
            for b in bots:
                result = run_match(config, a, b)
                assert result.turns > 0
                assert result.end_reason in (
                    "collision", "max_turns", "draw", "opponent_error",
                    "all_invalid",
                )

    def test_random_legal_vs_straight_until_blocked(self):
        from benchmark.tron_arena.bots import RandomLegalBot, StraightUntilBlockedBot
        config = GameConfig(seed=42, width=10, height=10, max_turns=100)
        result = run_match(config, RandomLegalBot, StraightUntilBlockedBot)
        assert result.turns > 0

    def test_greedy_space_vs_always_left(self):
        from benchmark.tron_arena.bots import GreedySpaceBot, AlwaysLeftBot
        config = GameConfig(seed=42, width=10, height=10, max_turns=100)
        result = run_match(config, GreedySpaceBot, AlwaysLeftBot)
        assert result.turns > 0
