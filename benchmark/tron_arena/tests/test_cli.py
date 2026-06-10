from __future__ import annotations

import json
import subprocess
import sys

import pytest


class TestMatchSmoke:
    def test_match_outputs_valid_json(self):
        result = subprocess.run(
            [
                sys.executable, "-m", "benchmark.tron_arena.cli",
                "match",
                "--bot-a", "random_legal",
                "--bot-b", "straight_until_blocked",
                "--seed", "42",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "seed" in data
        assert data["seed"] == 42
        assert "bot_names" in data
        assert "winner" in data
        assert "turns" in data
        assert "end_reason" in data
        assert "replay_hash" in data
        assert isinstance(data["replay_hash"], str)
        assert len(data["replay_hash"]) == 64

    def test_match_deterministic(self):
        outputs = []
        for _ in range(2):
            result = subprocess.run(
                [
                    sys.executable, "-m", "benchmark.tron_arena.cli",
                    "match",
                    "--bot-a", "greedy_space",
                    "--bot-b", "random_legal",
                    "--seed", "7",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            outputs.append(json.loads(result.stdout))
        assert outputs[0] == outputs[1]

    def test_match_writes_replay_file(self, tmp_path):
        replay_path = tmp_path / "match.json"
        result = subprocess.run(
            [
                sys.executable, "-m", "benchmark.tron_arena.cli",
                "match",
                "--bot-a", "greedy_space",
                "--bot-b", "random_legal",
                "--seed", "7",
                "--replay-out", str(replay_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        assert data["replay_path"] == str(replay_path)
        assert replay["seed"] == 7
        assert replay["bot_names"]["0"] == "greedy_space"
        assert "action_history" in replay

    def test_match_can_include_replay_payload(self):
        result = subprocess.run(
            [
                sys.executable, "-m", "benchmark.tron_arena.cli",
                "match",
                "--bot-a", "greedy_space",
                "--bot-b", "random_legal",
                "--seed", "7",
                "--include-replay",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["replay"]["seed"] == 7
        assert data["replay"]["bot_names"]["1"] == "random_legal"


class TestTournamentSmoke:
    def test_tournament_outputs_valid_json(self):
        result = subprocess.run(
            [
                sys.executable, "-m", "benchmark.tron_arena.cli",
                "tournament",
                "--bots", "random_legal,straight_until_blocked",
                "--seeds", "1,2",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert "bot_names" in data
        assert "matches_played" in data
        assert data["matches_played"] == 4
        assert "wins" in data
        assert "losses" in data
        assert "draws" in data
        assert "win_rates" in data
        assert "random_legal" in data["win_rates"]
        assert "straight_until_blocked" in data["win_rates"]

    def test_tournament_writes_replay_bundle(self, tmp_path):
        replay_dir = tmp_path / "replays"
        result = subprocess.run(
            [
                sys.executable, "-m", "benchmark.tron_arena.cli",
                "tournament",
                "--bots", "random_legal,straight_until_blocked",
                "--seeds", "1,2",
                "--replay-dir", str(replay_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        summary_path = replay_dir / "tournament_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        replay_files = sorted(replay_dir.glob("match_*.json"))

        assert data["replay_dir"] == str(replay_dir)
        assert data["summary_path"] == str(summary_path)
        assert len(replay_files) == 4
        assert len(summary["matches"]) == 4
        assert summary["summary"]["matches_played"] == 4
        assert summary["matches"][0]["replay_hash"]


class TestCliErrors:
    def test_unknown_bot_exits_nonzero(self):
        result = subprocess.run(
            [
                sys.executable, "-m", "benchmark.tron_arena.cli",
                "match",
                "--bot-a", "nonexistent_bot",
                "--bot-b", "random_legal",
                "--seed", "1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "nonexistent_bot" in result.stderr
