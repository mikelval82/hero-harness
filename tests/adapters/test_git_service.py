from __future__ import annotations

import platform
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

    def test_changed_files_since_reports_committed_diff_only(self) -> None:
        start = self.service.current_commit()
        self._stage_change("committed.py")
        _git(self.repo, "-c", "commit.gpgsign=false", "commit", "-m", "commit work")
        (self.repo / "untracked.py").write_text("pending", encoding="utf-8")

        self.assertEqual(self.service.changed_files_since(start), ["committed.py"])

    def test_merge_falls_back_after_signed_merge_leaves_merge_state(self) -> None:
        self.service.ensure_develop()
        if platform.system().lower().startswith("win"):
            validation = self.repo / "mission-validate.cmd"
            validation.write_text("@exit /b 0\n", encoding="utf-8")
        else:
            validation = self.repo / "mission-validate.sh"
            validation.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            validation.chmod(0o755)
        self.service.stage_files([validation])
        self.service.final_commit("add validation", "test setup")
        self.service.setup_branch("feature/merge-fallback")
        self._stage_change("feature.py")
        self.service.final_commit("add feature", "test feature")
        _git(self.repo, "config", "commit.gpgsign", "true")
        _git(self.repo, "config", "gpg.program", "definitely-not-a-gpg-binary")

        merged = self.service.merge_to_develop("feature/merge-fallback")

        self.assertTrue(merged)
        self.assertEqual(
            subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "develop",
        )
        self.assertTrue((self.repo / "feature.py").is_file())


if __name__ == "__main__":
    unittest.main()
