from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from mission_orchestrator.adapters.git.service import SubprocessGitService


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "seed.txt").write_text("seed", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-m", "seed")


def _head_subject(repo: Path) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


class GitSigningFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.repo = Path(self._tmp.name)
        _init_repo(self.repo)
        self.service = SubprocessGitService(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _stage_change(self, name: str = "work.txt") -> None:
        (self.repo / name).write_text("work", encoding="utf-8")
        self.service.stage_files([self.repo / name])

    def test_final_commit_falls_back_when_signing_is_unavailable(self) -> None:
        _git(self.repo, "config", "commit.gpgsign", "true")
        _git(self.repo, "config", "gpg.program", "definitely-not-a-gpg-binary")
        self._stage_change()

        self.service.final_commit("add work file", "summary")

        self.assertEqual(_head_subject(self.repo), "feat: add work file")

    def test_final_commit_still_fails_on_non_signing_errors(self) -> None:
        self._stage_change()
        (self.repo / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            self.service.final_commit("add work file", "summary")


if __name__ == "__main__":
    unittest.main()
