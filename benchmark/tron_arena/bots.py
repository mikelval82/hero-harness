from __future__ import annotations

import random
from collections import deque

from benchmark.tron_arena.actions import Action, Direction, DIRECTION_DELTAS, resolve_direction
from benchmark.tron_arena.engine import Observation


_ACTION_PRIORITY = [Action.STRAIGHT, Action.TURN_LEFT, Action.TURN_RIGHT]


def _is_legal(obs: Observation, action: Action) -> bool:
    new_dir = resolve_direction(obs.your_direction, action)
    dx, dy = DIRECTION_DELTAS[new_dir]
    nx, ny = obs.your_position[0] + dx, obs.your_position[1] + dy
    if nx < 0 or nx >= obs.width or ny < 0 or ny >= obs.height:
        return False
    return obs.grid[ny][nx] == 0


class AlwaysLeftBot:
    def __init__(self, player_id: int, seed: int) -> None:
        pass

    def choose_action(self, observation: Observation) -> Action:
        return Action.TURN_LEFT


class RandomLegalBot:
    def __init__(self, player_id: int, seed: int) -> None:
        self._rng = random.Random(seed)

    def choose_action(self, observation: Observation) -> Action:
        legal = [a for a in _ACTION_PRIORITY if _is_legal(observation, a)]
        if legal:
            return self._rng.choice(legal)
        return self._rng.choice(_ACTION_PRIORITY)


class StraightUntilBlockedBot:
    def __init__(self, player_id: int, seed: int) -> None:
        pass

    def choose_action(self, observation: Observation) -> Action:
        for action in _ACTION_PRIORITY:
            if _is_legal(observation, action):
                return action
        return Action.STRAIGHT


class GreedySpaceBot:
    def __init__(self, player_id: int, seed: int) -> None:
        pass

    def choose_action(self, observation: Observation) -> Action:
        best_action = Action.STRAIGHT
        best_count = -1

        for action in _ACTION_PRIORITY:
            if not _is_legal(observation, action):
                continue
            new_dir = resolve_direction(observation.your_direction, action)
            dx, dy = DIRECTION_DELTAS[new_dir]
            nx = observation.your_position[0] + dx
            ny = observation.your_position[1] + dy
            count = self._flood_fill(observation, nx, ny)
            if count > best_count:
                best_count = count
                best_action = action

        return best_action

    def _flood_fill(self, obs: Observation, start_x: int, start_y: int) -> int:
        visited = {(start_x, start_y)}
        queue = deque([(start_x, start_y)])
        count = 0

        while queue:
            x, y = queue.popleft()
            count += 1
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in visited:
                    continue
                if nx < 0 or nx >= obs.width or ny < 0 or ny >= obs.height:
                    continue
                if obs.grid[ny][nx] != 0:
                    continue
                visited.add((nx, ny))
                queue.append((nx, ny))

        return count


BASELINE_BOTS = {
    "random_legal": RandomLegalBot,
    "straight_until_blocked": StraightUntilBlockedBot,
    "greedy_space": GreedySpaceBot,
    "always_left": AlwaysLeftBot,
}
