from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

VALIDATION_SCRIPTS = (
    "mission-validate.cmd",
    "mission-validate.bat",
    "mission-validate.ps1",
    "mission-validate.sh",
)

POSIX_VALIDATION_SCRIPTS = (
    "mission-validate.sh",
    "mission-validate.cmd",
    "mission-validate.bat",
    "mission-validate.ps1",
)


class GitOperationError(RuntimeError):
    """A Git invariant or state-changing operation failed."""


def _git_detail(result) -> str:
    for attribute in ("stderr", "stdout"):
        value = getattr(result, attribute, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"exit code {getattr(result, 'returncode', 'unknown')}"


def _git_cwd(cwd=None) -> str | None:
    return str(Path(cwd).resolve()) if cwd is not None else None


def require_git_repository(cwd=None) -> Path:
    """Return the repository root or fail before any mission state is changed."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if result.returncode != 0 or not (result.stdout or "").strip():
        raise GitOperationError(f"Target is not a Git repository: {_git_detail(result)}")
    return Path(result.stdout.strip()).resolve()


def require_clean_worktree(cwd=None) -> None:
    """Reject tracked, staged, and untracked changes for a new mutating mission."""
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GitOperationError(f"Could not inspect Git worktree: {_git_detail(result)}")
    if (result.stdout or "").strip():
        raise GitOperationError(
            "Git worktree is not clean; commit, stash, or remove existing changes "
            "before starting a mutating mission"
        )


def require_current_branch(expected: str, cwd=None) -> str:
    """Require an attached HEAD on exactly *expected*; never checkout implicitly."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    actual = (result.stdout or "").strip()
    if result.returncode != 0 or not actual:
        raise GitOperationError(
            f"Cannot resume mission on detached HEAD: {_git_detail(result)}"
        )
    if actual != expected:
        raise GitOperationError(
            f"Cannot resume branch {expected!r}; current branch is {actual!r}"
        )
    return actual


def validate_branch_name(branch: str, cwd=None) -> str:
    """Require an exact Git branch name, rejecting checkout shorthand/options."""
    result = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    normalized = (result.stdout or "").strip()
    if result.returncode != 0 or normalized != branch:
        raise GitOperationError(
            f"Invalid or ambiguous Git branch name {branch!r}: {_git_detail(result)}"
        )
    return normalized


def detect_base_branch(cwd=None) -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/main"],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if result.returncode == 0:
        return "main"
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/master"],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if result.returncode == 0:
        return "master"
    return "main"


def ensure_git_identity(cwd=None) -> None:
    """Require a complete identity, using paired env values only repo-locally."""
    name = os.environ.get("GIT_AUTHOR_NAME", "").strip()
    email = os.environ.get("GIT_AUTHOR_EMAIL", "").strip()
    if bool(name) != bool(email):
        raise GitOperationError(
            "GIT_AUTHOR_NAME and GIT_AUTHOR_EMAIL must be provided together"
        )

    root = _git_cwd(cwd)
    if name and email:
        for key, value in (("user.name", name), ("user.email", email)):
            result = subprocess.run(
                ["git", "config", "--local", key, value],
                cwd=root, capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise GitOperationError(
                    f"Could not configure local Git {key}: {_git_detail(result)}"
                )
        return

    missing = []
    for key in ("user.name", "user.email"):
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=root, capture_output=True, text=True,
        )
        if result.returncode not in (0, 1):
            raise GitOperationError(
                f"Could not inspect Git {key}: {_git_detail(result)}"
            )
        if result.returncode == 1 or not (result.stdout or "").strip():
            missing.append(key)
    if missing:
        raise GitOperationError(
            "Incomplete Git identity; configure " + " and ".join(missing)
            + " or provide GIT_AUTHOR_NAME and GIT_AUTHOR_EMAIL together"
        )


def setup_branch(branch: str, cwd=None) -> str:
    validate_branch_name(branch, cwd)
    result = subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if result.returncode == 0:
        require_current_branch(branch, cwd)
        return "created"
    fallback = subprocess.run(
        ["git", "checkout", branch],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if fallback.returncode != 0:
        raise GitOperationError(
            f"Could not create or checkout branch {branch!r}: "
            f"{_git_detail(fallback)}"
        )
    require_current_branch(branch, cwd)
    return "existing"


def setup_git(branch: str, cwd=None) -> str:
    if cwd is None:
        ensure_git_identity()
        return setup_branch(branch)
    ensure_git_identity(cwd)
    return setup_branch(branch, cwd)


def ensure_develop(cwd=None) -> str:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/develop"],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if result.returncode == 0:
        checkout = subprocess.run(
            ["git", "checkout", "develop"], cwd=_git_cwd(cwd),
            capture_output=True, text=True,
        )
        if checkout.returncode != 0:
            raise GitOperationError(
                f"Could not checkout develop: {_git_detail(checkout)}"
            )
        return "existing"
    if result.returncode not in (0, 1):
        raise GitOperationError(
            f"Could not inspect develop branch: {_git_detail(result)}"
        )
    base = detect_base_branch() if cwd is None else detect_base_branch(cwd)
    created = subprocess.run(
        ["git", "checkout", "-b", "develop", base],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if created.returncode != 0:
        raise GitOperationError(
            f"Could not create develop from {base!r}: {_git_detail(created)}"
        )
    return "created"


def _find_validation_script(project_dir: Path) -> Path | None:
    filenames = VALIDATION_SCRIPTS if os.name == "nt" else POSIX_VALIDATION_SCRIPTS
    for filename in filenames:
        script = project_dir / filename
        if script.is_file():
            return script
    return None


def _validation_command(script: Path, log: Callable) -> list[str] | None:
    suffix = script.suffix.lower()
    if suffix == ".ps1":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            log(f"Cannot run {script.name}: PowerShell not found")
            return None
        command = [shell, "-NoProfile"]
        if Path(shell).name.lower().startswith("powershell"):
            command.extend(["-ExecutionPolicy", "Bypass"])
        command.extend(["-File", str(script)])
        return command
    if suffix == ".sh":
        shell = shutil.which("bash") or shutil.which("sh")
        if shell is None:
            log(f"Cannot run {script.name}: shell not found")
            return None
        return [shell, str(script)]
    return [str(script)]


def run_target_validation(project_dir, log: Callable, timeout: int = 120) -> bool:
    root = Path(project_dir or Path.cwd()).resolve()
    script = _find_validation_script(root)
    if script is None:
        log("No mission-validate script found in target project; skipping merge")
        return False

    command = _validation_command(script, log)
    if command is None:
        log("Target validation could not start; skipping merge")
        return False

    log(f"Running target validation: {script.name}")
    try:
        result = subprocess.run(
            command, cwd=str(root), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log("Target validation TIMED OUT; skipping merge")
        return False

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        tail = output[-1000:] if output else ""
        log(f"Target validation FAILED; skipping merge\n{tail}")
        return False

    if output.strip():
        log(f"Target validation output:\n{output[-1000:]}")
    log("Target validation passed")
    return True


def merge_to_develop(branch: str, log: Callable, project_dir=None) -> bool:
    root = Path(project_dir or Path.cwd()).resolve()
    if not run_target_validation(root, log):
        return False

    log("Merging to develop")
    checkout = subprocess.run(
        ["git", "checkout", "develop"], cwd=str(root), capture_output=True, text=True,
    )
    if checkout.returncode != 0:
        log(f"Checkout develop FAILED (uncommitted changes?): {checkout.stderr.strip()}")
        return False
    result = subprocess.run(
        ["git", "merge", "--no-ff", "-m",
         f"Merge branch '{branch}' into develop", branch],
        cwd=str(root), capture_output=True, text=True,
    )
    if result.returncode != 0:
        log(f"Merge FAILED: {result.stderr}")
        abort = subprocess.run(
            ["git", "merge", "--abort"], cwd=str(root),
            capture_output=True, text=True,
        )
        if abort.returncode != 0:
            log(f"Merge abort FAILED: {_git_detail(abort)}")
        restore = subprocess.run(
            ["git", "checkout", branch], cwd=str(root),
            capture_output=True, text=True,
        )
        if restore.returncode != 0:
            log(f"Branch restore FAILED: {_git_detail(restore)}")
        return False

    log(f"Merged {branch} -> develop")
    return True


def final_commit(task_description: str, task_summary: str, cwd=None) -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=_git_cwd(cwd),
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("WARNING: nothing to commit")
        return False
    if result.returncode != 1:
        raise GitOperationError(
            f"Could not inspect staged changes: {_git_detail(result)}"
        )
    commit = subprocess.run(
        ["git", "commit", "--no-edit", "-m",
         f"feat: {task_description}", "-m", task_summary],
        cwd=_git_cwd(cwd), capture_output=True, text=True,
    )
    if commit.returncode != 0:
        raise GitOperationError(f"Git commit failed: {_git_detail(commit)}")
    return True
