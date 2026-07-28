import subprocess
from unittest.mock import MagicMock

import pytest

import src.core.git as git_mod
from src.core.git import (
    GitOperationError,
    detect_base_branch,
    ensure_develop,
    ensure_git_identity,
    final_commit,
    merge_to_develop,
    require_clean_worktree,
    require_current_branch,
    require_git_repository,
    run_target_validation,
    setup_branch,
    setup_git,
    validate_branch_name,
)


def _write_validation_script(tmp_path):
    script = tmp_path / "mission-validate.cmd"
    script.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    return script


class TestDetectBaseBranch:

    def test_origin_head(self, monkeypatch):
        def fake_run(cmd, **kw):
            m = MagicMock()
            m.returncode = 0
            m.stdout = "refs/remotes/origin/develop\n"
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        assert detect_base_branch() == "develop"

    def test_fallback_main(self, monkeypatch):
        count = [0]
        def fake_run(cmd, **kw):
            count[0] += 1
            m = MagicMock()
            m.returncode = 0 if count[0] == 2 else 1
            m.stdout = ""
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        assert detect_base_branch() == "main"

    def test_fallback_master(self, monkeypatch):
        count = [0]
        def fake_run(cmd, **kw):
            count[0] += 1
            m = MagicMock()
            m.returncode = 0 if count[0] == 3 else 1
            m.stdout = ""
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        assert detect_base_branch() == "master"

    def test_all_fail(self, monkeypatch):
        def fake_run(cmd, **kw):
            m = MagicMock()
            m.returncode = 1
            m.stdout = ""
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        assert detect_base_branch() == "main"


class TestEnsureGitIdentity:

    def test_already_set(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            m = MagicMock()
            m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        ensure_git_identity()
        assert calls == [
            ["git", "config", "--get", "user.name"],
            ["git", "config", "--get", "user.email"],
        ]

    def test_sets_identity_from_env(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            m = MagicMock()
            m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
        ensure_git_identity()
        assert calls == [
            ["git", "config", "--local", "user.name", "Test User"],
            ["git", "config", "--local", "user.email", "test@example.com"],
        ]

    def test_raises_without_env(self, monkeypatch):
        def fake_run(cmd, **kw):
            m = MagicMock()
            m.returncode = 1
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)
        monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
        with pytest.raises(GitOperationError, match="Incomplete Git identity"):
            ensure_git_identity()

    def test_rejects_partial_env_identity(self, monkeypatch):
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
        monkeypatch.delenv("GIT_AUTHOR_EMAIL", raising=False)
        with pytest.raises(GitOperationError, match="provided together"):
            ensure_git_identity()


class TestSetupBranch:

    def test_created(self, monkeypatch):
        def fake_run(cmd, **kw):
            if cmd[:3] == ["git", "check-ref-format", "--branch"]:
                return MagicMock(returncode=0, stdout="feat-x\n", stderr="")
            if cmd[:4] == ["git", "symbolic-ref", "--quiet", "--short"]:
                return MagicMock(returncode=0, stdout="feat-x\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        assert setup_branch("feat-x") == "created"

    def test_existing(self, monkeypatch):
        checkout_count = [0]
        def fake_run(cmd, **kw):
            if cmd[:3] == ["git", "check-ref-format", "--branch"]:
                return MagicMock(returncode=0, stdout="feat-x\n", stderr="")
            if cmd[:4] == ["git", "symbolic-ref", "--quiet", "--short"]:
                return MagicMock(returncode=0, stdout="feat-x\n", stderr="")
            checkout_count[0] += 1
            return MagicMock(
                returncode=1 if checkout_count[0] == 1 else 0,
                stdout="", stderr="",
            )
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        assert setup_branch("feat-x") == "existing"

    def test_create_and_fallback_failure_is_visible(self, monkeypatch):
        def fake_run(cmd, **kw):
            if cmd[:3] == ["git", "check-ref-format", "--branch"]:
                return MagicMock(returncode=0, stdout="feat-x\n", stderr="")
            m = MagicMock(returncode=1, stderr="checkout failed")
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        with pytest.raises(GitOperationError, match="checkout failed"):
            setup_branch("feat-x")

    def test_rejects_checkout_shorthand_before_checkout(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="main\n", stderr="")

        monkeypatch.setattr(git_mod.subprocess, "run", fake_run)
        with pytest.raises(GitOperationError, match="Invalid or ambiguous"):
            setup_branch("@{-1}")
        assert calls == [["git", "check-ref-format", "--branch", "@{-1}"]]

    def test_verifies_effective_branch_after_checkout(self, monkeypatch):
        def fake_run(cmd, **kw):
            if cmd[:3] == ["git", "check-ref-format", "--branch"]:
                return MagicMock(returncode=0, stdout="feat-x\n", stderr="")
            if cmd[:4] == ["git", "symbolic-ref", "--quiet", "--short"]:
                return MagicMock(returncode=0, stdout="other\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(git_mod.subprocess, "run", fake_run)
        with pytest.raises(GitOperationError, match="current branch"):
            setup_branch("feat-x")


class TestSetupGit:

    def test_delegates(self, monkeypatch):
        identity_called = [False]
        monkeypatch.setattr(git_mod, "ensure_git_identity", lambda: setattr(identity_called, '__setitem__', None) or identity_called.__setitem__(0, True))
        monkeypatch.setattr(git_mod, "setup_branch", lambda b: "created")
        monkeypatch.setattr(git_mod, "ensure_git_identity", lambda: identity_called.__setitem__(0, True))
        result = setup_git("feat-x")
        assert identity_called[0]
        assert result == "created"


class TestEnsureDevelop:

    def test_creates(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            m = MagicMock()
            if cmd[:4] == ["git", "show-ref", "--verify", "--quiet"]:
                m.returncode = 1
            else:
                m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        monkeypatch.setattr(git_mod, "detect_base_branch", lambda: "master")
        assert ensure_develop() == "created"

    def test_existing(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            m = MagicMock()
            m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        assert ensure_develop() == "existing"

    def test_existing_checkout_failure_is_visible(self, monkeypatch):
        calls = [0]
        def fake_run(cmd, **kw):
            calls[0] += 1
            return MagicMock(
                returncode=0 if calls[0] == 1 else 1,
                stderr="locked worktree",
            )
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        with pytest.raises(GitOperationError, match="locked worktree"):
            ensure_develop()


class TestGitPreflight:

    def test_branch_name_must_be_exact_not_checkout_expansion(self, monkeypatch):
        monkeypatch.setattr(git_mod.subprocess, "run", lambda *a, **kw: MagicMock(
            returncode=0, stdout="main\n", stderr="",
        ))
        with pytest.raises(GitOperationError, match="Invalid or ambiguous"):
            validate_branch_name("@{-1}")

    def test_repository_required(self, monkeypatch):
        monkeypatch.setattr(git_mod.subprocess, "run", lambda *a, **kw: MagicMock(
            returncode=128, stdout="", stderr="not a git repository",
        ))
        with pytest.raises(GitOperationError, match="not a Git repository"):
            require_git_repository()

    def test_dirty_worktree_includes_untracked(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="?? new.txt\n", stderr="")
        monkeypatch.setattr(git_mod.subprocess, "run", fake_run)
        with pytest.raises(GitOperationError, match="not clean"):
            require_clean_worktree()
        assert "--untracked-files=all" in calls[0]

    def test_current_branch_must_match(self, monkeypatch):
        monkeypatch.setattr(git_mod.subprocess, "run", lambda *a, **kw: MagicMock(
            returncode=0, stdout="other\n", stderr="",
        ))
        with pytest.raises(GitOperationError, match="current branch"):
            require_current_branch("expected")

    def test_detached_head_rejected(self, monkeypatch):
        monkeypatch.setattr(git_mod.subprocess, "run", lambda *a, **kw: MagicMock(
            returncode=1, stdout="", stderr="",
        ))
        with pytest.raises(GitOperationError, match="detached HEAD"):
            require_current_branch("expected")


class TestRunTargetValidation:

    def test_missing_script_skips_merge(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kw):
            raise AssertionError("validation should not run without a script")

        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        logs = []
        assert run_target_validation(tmp_path, logs.append) is False
        assert any("No mission-validate" in m for m in logs)


class TestMergeToDevelop:

    def test_success(self, tmp_path, monkeypatch):
        _write_validation_script(tmp_path)

        def fake_run(cmd, **kw):
            m = MagicMock()
            m.returncode = 0
            m.stdout = "validation passed"
            m.stderr = ""
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        logs = []
        assert merge_to_develop("feat", logs.append, project_dir=tmp_path) is True
        assert any("Merged" in m for m in logs)

    def test_test_fail(self, tmp_path, monkeypatch):
        validation = _write_validation_script(tmp_path)

        def fake_run(cmd, **kw):
            m = MagicMock()
            if str(validation) in cmd:
                m.returncode = 1
                m.stdout = "FAILED"
                m.stderr = ""
            else:
                m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        logs = []
        assert merge_to_develop("feat", logs.append, project_dir=tmp_path) is False

    def test_conflict(self, tmp_path, monkeypatch):
        validation = _write_validation_script(tmp_path)
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            m = MagicMock()
            m.stdout = ""
            m.stderr = ""
            if str(validation) in cmd:
                m.returncode = 0
                m.stdout = "passed"
            elif cmd[:2] == ["git", "merge"] and "--abort" not in cmd:
                m.returncode = 1
                m.stderr = "CONFLICT"
            else:
                m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        logs = []
        assert merge_to_develop("feat", logs.append, project_dir=tmp_path) is False
        assert ["git", "merge", "--abort"] in calls

    def test_conflict_reports_failed_recovery(self, tmp_path, monkeypatch):
        validation = _write_validation_script(tmp_path)

        def fake_run(cmd, **kw):
            if str(validation) in cmd:
                return MagicMock(returncode=0, stdout="passed", stderr="")
            if cmd == ["git", "checkout", "develop"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if cmd[:2] == ["git", "merge"] and "--abort" not in cmd:
                return MagicMock(returncode=1, stdout="", stderr="CONFLICT")
            if cmd == ["git", "merge", "--abort"]:
                return MagicMock(returncode=1, stdout="", stderr="abort locked")
            return MagicMock(returncode=1, stdout="", stderr="restore locked")

        monkeypatch.setattr(git_mod.subprocess, "run", fake_run)
        logs = []

        assert merge_to_develop("feat", logs.append, project_dir=tmp_path) is False
        assert any("Merge abort FAILED: abort locked" in entry for entry in logs)
        assert any("Branch restore FAILED: restore locked" in entry for entry in logs)

    def test_timeout(self, tmp_path, monkeypatch):
        validation = _write_validation_script(tmp_path)

        def fake_run(cmd, **kw):
            if str(validation) in cmd:
                raise subprocess.TimeoutExpired(cmd, 120)
            m = MagicMock()
            m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {
            "run": staticmethod(fake_run),
            "TimeoutExpired": subprocess.TimeoutExpired,
        })())
        logs = []
        assert merge_to_develop("feat", logs.append, project_dir=tmp_path) is False
        assert any("TIMED OUT" in m for m in logs)


class TestFinalCommit:

    def test_with_changes(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            m = MagicMock()
            m.returncode = 1 if "diff" in cmd else 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        final_commit("do stuff", "Total: 1 | Completed: 1")
        assert len(calls) == 2
        assert "commit" in calls[1]

    def test_nothing_staged(self, monkeypatch):
        def fake_run(cmd, **kw):
            m = MagicMock()
            m.returncode = 0
            return m
        monkeypatch.setattr(git_mod, "subprocess", type("M", (), {"run": staticmethod(fake_run)})())
        printed = []
        monkeypatch.setattr("builtins.print", lambda *a, **kw: printed.append(str(a)))
        final_commit("do stuff", "Total: 0")
        assert any("nothing to commit" in s.lower() for s in printed)

    def test_diff_error_is_not_treated_as_changes(self, monkeypatch):
        monkeypatch.setattr(git_mod.subprocess, "run", lambda *a, **kw: MagicMock(
            returncode=2, stderr="index corrupt",
        ))
        with pytest.raises(GitOperationError, match="index corrupt"):
            final_commit("do stuff", "summary")

    def test_commit_failure_is_visible(self, monkeypatch):
        calls = [0]
        def fake_run(cmd, **kw):
            calls[0] += 1
            if calls[0] == 1:
                return MagicMock(returncode=1, stdout="", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="hook rejected")
        monkeypatch.setattr(git_mod.subprocess, "run", fake_run)
        with pytest.raises(GitOperationError, match="hook rejected"):
            final_commit("do stuff", "summary")
