from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


class SubprocessGitService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir

    def detect_base_branch(self) -> str:
        origin_head = self._run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], check=False)
        if origin_head.returncode == 0 and origin_head.stdout.strip():
            return origin_head.stdout.strip().split("/", 1)[-1]
        for branch in ("main", "master"):
            if self._run(["git", "rev-parse", "--verify", branch], check=False).returncode == 0:
                return branch
        return "main"

    def ensure_develop(self) -> str:
        self._ensure_identity()
        if self._run(["git", "rev-parse", "--verify", "develop"], check=False).returncode == 0:
            self._run(["git", "checkout", "develop"])
            return "develop"
        base = self.detect_base_branch()
        self._run(["git", "checkout", "-B", "develop", base])
        return "develop"

    def setup_branch(self, branch: str) -> str:
        result = self._run(["git", "checkout", "-b", branch], check=False)
        if result.returncode == 0:
            return branch
        self._run(["git", "checkout", branch])
        return branch

    def stage_files(self, files: list[Path]) -> None:
        if not files:
            return
        self._run(["git", "add", "--", *[str(path) for path in files]])

    def final_commit(self, task_description: str, summary: str) -> None:
        self._ensure_identity()
        staged = self._run(["git", "diff", "--cached", "--quiet"], check=False)
        if staged.returncode == 0:
            return
        subject = f"feat: {task_description[:70].strip()}"
        self._run(["git", "commit", "-m", subject, "-m", summary])

    def run_target_validation(self, project_dir: Path) -> bool:
        script = self._validation_script(project_dir)
        if script is None:
            return False
        if script.suffix.lower() == ".ps1":
            shell = self._powershell()
            args = [shell, "-NoProfile"]
            if shell.lower().endswith("powershell.exe") or shell.lower() == "powershell":
                args.extend(["-ExecutionPolicy", "Bypass"])
            args.extend(["-File", str(script)])
        elif script.suffix.lower() in {".cmd", ".bat"}:
            args = ["cmd.exe", "/c", str(script)]
        else:
            args = [str(script)]
        result = subprocess.run(args, cwd=project_dir, text=True, capture_output=True, timeout=120, check=False)
        return result.returncode == 0

    def merge_to_develop(self, branch: str) -> bool:
        if not self.run_target_validation(self.project_dir):
            return False
        original = self._run(["git", "branch", "--show-current"], check=False).stdout.strip() or branch
        self._run(["git", "checkout", "develop"])
        result = self._run(
            ["git", "merge", "--no-ff", "-m", f"Merge branch '{branch}' into develop", branch],
            check=False,
        )
        if result.returncode == 0:
            return True
        self._run(["git", "merge", "--abort"], check=False)
        self._run(["git", "checkout", original], check=False)
        return False

    def _run(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            cwd=self.project_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {args}")
        return result

    def _ensure_identity(self) -> None:
        name = self._run(["git", "config", "user.name"], check=False).stdout.strip()
        email = self._run(["git", "config", "user.email"], check=False).stdout.strip()
        env_name = os.environ.get("GIT_AUTHOR_NAME", "")
        env_email = os.environ.get("GIT_AUTHOR_EMAIL", "")
        if not name and env_name:
            self._run(["git", "config", "user.name", env_name])
        if not email and env_email:
            self._run(["git", "config", "user.email", env_email])
        name = self._run(["git", "config", "user.name"], check=False).stdout.strip()
        email = self._run(["git", "config", "user.email"], check=False).stdout.strip()
        if not name or not email:
            raise RuntimeError("Git identity missing. Configure user.name/user.email or GIT_AUTHOR_* env vars.")

    @staticmethod
    def _validation_script(project_dir: Path) -> Path | None:
        if platform.system().lower().startswith("win"):
            names = ("mission-validate.cmd", "mission-validate.bat", "mission-validate.ps1", "mission-validate.sh")
        else:
            names = ("mission-validate.sh", "mission-validate.cmd", "mission-validate.bat", "mission-validate.ps1")
        for name in names:
            path = project_dir / name
            if path.exists():
                return path
        return None

    @staticmethod
    def _powershell() -> str:
        for candidate in ("pwsh", "powershell"):
            try:
                result = subprocess.run(
                    [candidate, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"],
                    text=True,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                continue
            if result.returncode == 0:
                return candidate
        return "powershell"

