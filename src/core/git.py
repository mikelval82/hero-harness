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


def detect_base_branch() -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/main"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return "main"
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/master"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return "master"
    return "main"


def ensure_git_identity():
    result = subprocess.run(
        ["git", "config", "user.name"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return
    name = os.environ.get("GIT_AUTHOR_NAME", "")
    email = os.environ.get("GIT_AUTHOR_EMAIL", "")
    if not name or not email:
        raise RuntimeError(
            "Git identity not configured and GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL not set. "
            "Run: git config --global user.name 'Your Name' && "
            "git config --global user.email 'you@example.com'"
        )
    subprocess.run(["git", "config", "--global", "user.name", name])
    subprocess.run(["git", "config", "--global", "user.email", email])


def setup_branch(branch: str) -> str:
    result = subprocess.run(
        ["git", "checkout", "-b", branch],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return "created"
    subprocess.run(
        ["git", "checkout", branch],
        capture_output=True, text=True,
    )
    return "existing"


def setup_git(branch: str) -> str:
    ensure_git_identity()
    return setup_branch(branch)


def ensure_develop() -> str:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/develop"],
        capture_output=True,
    )
    if result.returncode == 0:
        subprocess.run(["git", "checkout", "develop"], capture_output=True, text=True)
        return "existing"
    base = detect_base_branch()
    subprocess.run(
        ["git", "checkout", "-b", "develop", base],
        capture_output=True, text=True, check=True,
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
        subprocess.run(["git", "merge", "--abort"], cwd=str(root), capture_output=True)
        subprocess.run(["git", "checkout", branch], cwd=str(root), capture_output=True, text=True)
        return False

    log(f"Merged {branch} -> develop")
    return True


def final_commit(task_description: str, task_summary: str) -> None:
    result = subprocess.run(["git", "diff", "--cached", "--quiet"],
                            capture_output=True)
    if result.returncode == 0:
        print("WARNING: nothing to commit")
        return
    subprocess.run(["git", "commit", "--no-edit", "-m",
                    f"feat: {task_description}", "-m", task_summary],
                   check=False)
