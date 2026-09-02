from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        if not platform.system().lower().startswith("win"):
            hook.chmod(0o755)

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

    def test_preflight_rejects_invalid_branch_before_checkout(self) -> None:
        original = subprocess.run(
            ["git", "branch", "--show-current"], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        with self.assertRaisesRegex(RuntimeError, "invalid Git branch"):
            self.service.preflight(
                branch="--orphan", resume=False, allow_dirty=False, mutating=True
            )
        self.assertEqual(
            subprocess.run(
                ["git", "branch", "--show-current"], cwd=self.repo, check=True, capture_output=True, text=True
            ).stdout.strip(),
            original,
        )

    def test_preflight_branches_from_selected_head_not_stale_develop(self) -> None:
        selected_head = self.service.current_commit()
        self.service.ensure_develop()
        (self.repo / "develop-only.txt").write_text("stale", encoding="utf-8")
        _git(self.repo, "add", "develop-only.txt")
        _git(self.repo, "-c", "commit.gpgsign=false", "commit", "-m", "develop only")
        _git(self.repo, "checkout", "--detach", selected_head)

        self.service.preflight(
            branch="feature/from-selected-head",
            resume=False,
            allow_dirty=False,
            mutating=True,
        )

        self.assertEqual(self.service.current_commit(), selected_head)
        self.assertEqual(
            subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "feature/from-selected-head",
        )
        self.assertFalse((self.repo / "develop-only.txt").exists())

    def test_preflight_rejects_dirty_tree_unless_opted_in_and_protects_baseline(self) -> None:
        dirty = self.repo / "user-note.txt"
        dirty.write_text("keep me", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "worktree is not clean"):
            self.service.preflight(branch="feature/dirty", resume=False, allow_dirty=False, mutating=True)

        baseline = self.service.preflight(
            branch="feature/dirty", resume=False, allow_dirty=True, mutating=True
        )
        self.assertIsNotNone(baseline)
        self.assertEqual(baseline.paths[0]["path"], "user-note.txt")
        self.assertTrue(baseline.paths[0]["sha256"])
        with self.assertRaisesRegex(RuntimeError, "pre-existing dirty paths"):
            self.service.stage_files([dirty])

    def test_resume_requires_exact_attached_branch_without_checkout(self) -> None:
        self.service.ensure_develop()
        self.service.setup_branch("feature/resume")
        self.service.preflight(branch="feature/resume", resume=True, allow_dirty=False, mutating=True)

        _git(self.repo, "checkout", "develop")
        with self.assertRaisesRegex(RuntimeError, "current branch"):
            self.service.preflight(branch="feature/resume", resume=True, allow_dirty=False, mutating=True)
        _git(self.repo, "checkout", "--detach")
        with self.assertRaisesRegex(RuntimeError, "detached HEAD"):
            self.service.preflight(branch="feature/resume", resume=True, allow_dirty=False, mutating=True)

    def test_preflight_requires_complete_local_identity_or_paired_environment(self) -> None:
        _git(self.repo, "config", "--local", "--unset", "user.email")
        with patch.dict("os.environ", {"GIT_AUTHOR_NAME": "Only name"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "provided together"):
                self.service.preflight(branch="feature/identity", resume=False, allow_dirty=False, mutating=True)
        with patch.dict(
            "os.environ", {"GIT_AUTHOR_NAME": "Agent", "GIT_AUTHOR_EMAIL": "agent@example.com"}, clear=False
        ):
            self.service.preflight(branch="feature/identity", resume=False, allow_dirty=False, mutating=True)
        self.assertEqual(
            subprocess.run(
                ["git", "config", "--local", "--get", "user.email"], cwd=self.repo,
                check=True, capture_output=True, text=True,
            ).stdout.strip(),
            "agent@example.com",
        )


if __name__ == "__main__":
    unittest.main()
