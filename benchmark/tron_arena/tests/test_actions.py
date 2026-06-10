from benchmark.tron_arena.actions import (
    Action,
    Direction,
    DIRECTION_DELTAS,
    resolve_direction,
)


class TestDirection:
    def test_all_four_directions_exist(self):
        assert set(Direction) == {
            Direction.UP,
            Direction.DOWN,
            Direction.LEFT,
            Direction.RIGHT,
        }

    def test_direction_is_str_enum(self):
        assert isinstance(Direction.UP, str)
        assert Direction.UP == "up"

    def test_deltas_cover_all_directions(self):
        assert set(DIRECTION_DELTAS.keys()) == set(Direction)

    def test_delta_up(self):
        assert DIRECTION_DELTAS[Direction.UP] == (0, -1)

    def test_delta_down(self):
        assert DIRECTION_DELTAS[Direction.DOWN] == (0, 1)

    def test_delta_left(self):
        assert DIRECTION_DELTAS[Direction.LEFT] == (-1, 0)

    def test_delta_right(self):
        assert DIRECTION_DELTAS[Direction.RIGHT] == (1, 0)

    def test_deltas_are_unit_vectors(self):
        for d, (dx, dy) in DIRECTION_DELTAS.items():
            assert abs(dx) + abs(dy) == 1, f"{d} delta is not a unit vector"


class TestAction:
    def test_all_three_actions_exist(self):
        assert set(Action) == {
            Action.STRAIGHT,
            Action.TURN_LEFT,
            Action.TURN_RIGHT,
        }

    def test_action_is_str_enum(self):
        assert isinstance(Action.STRAIGHT, str)
        assert Action.STRAIGHT == "straight"


class TestResolveDirection:
    def test_straight_preserves_direction(self):
        for d in Direction:
            assert resolve_direction(d, Action.STRAIGHT) is d

    def test_left_turn_from_up(self):
        assert resolve_direction(Direction.UP, Action.TURN_LEFT) is Direction.LEFT

    def test_left_turn_from_left(self):
        assert resolve_direction(Direction.LEFT, Action.TURN_LEFT) is Direction.DOWN

    def test_left_turn_from_down(self):
        assert resolve_direction(Direction.DOWN, Action.TURN_LEFT) is Direction.RIGHT

    def test_left_turn_from_right(self):
        assert resolve_direction(Direction.RIGHT, Action.TURN_LEFT) is Direction.UP

    def test_right_turn_from_up(self):
        assert resolve_direction(Direction.UP, Action.TURN_RIGHT) is Direction.RIGHT

    def test_right_turn_from_right(self):
        assert resolve_direction(Direction.RIGHT, Action.TURN_RIGHT) is Direction.DOWN

    def test_right_turn_from_down(self):
        assert resolve_direction(Direction.DOWN, Action.TURN_RIGHT) is Direction.LEFT

    def test_right_turn_from_left(self):
        assert resolve_direction(Direction.LEFT, Action.TURN_RIGHT) is Direction.UP

    def test_four_left_turns_return_to_original(self):
        for d in Direction:
            result = d
            for _ in range(4):
                result = resolve_direction(result, Action.TURN_LEFT)
            assert result is d

    def test_four_right_turns_return_to_original(self):
        for d in Direction:
            result = d
            for _ in range(4):
                result = resolve_direction(result, Action.TURN_RIGHT)
            assert result is d

    def test_left_then_right_is_identity(self):
        for d in Direction:
            turned = resolve_direction(d, Action.TURN_LEFT)
            back = resolve_direction(turned, Action.TURN_RIGHT)
            assert back is d
