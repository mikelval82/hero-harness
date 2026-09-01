from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


MUTATING_MODES = frozenset({"full", "focused", "hotfix"})


@dataclass(frozen=True)
class DirtyBaseline:
    paths: tuple[dict[str, str], ...]


class SubprocessGitService:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self._baseline_paths: frozenset[str] = frozenset()

    def preflight(
        self,
        *,
        branch: str,
        resume: bool,
        allow_dirty: bool,
        mutating: bool,
    ) -> DirtyBaseline | None:
        """Check every mutable Git invariant before workspace creation or checkout."""

        if not mutating:
            return None
        self._require_repository()
        self._validate_branch(branch)
        self._ensure_identity()
        if resume:
            if allow_dirty:
                raise RuntimeError("--allow-dirty cannot be combined with --resume")
            self._require_current_branch(branch)
            return None
        dirty = self._dirty_baseline()
        if dirty.paths and not allow_dirty:
            raise RuntimeError("Git worktree is not clean; rerun with explicit --allow-dirty to preserve it")
        self._baseline_paths = frozenset(item["path"] for item in dirty.paths)
        self.ensure_develop()
        self.setup_branch(branch)
        return dirty if dirty.paths else None

    def detect_base_branch(self) -> str:
        origin_head = self._run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], check=False)
        if origin_head.returncode == 0 and origin_head.stdout.strip():
            return origin_head.stdout.strip().split("/", 1)[-1]
        for branch in ("main", "master"):
            if self._run(["git", "rev-parse", "--verify", branch], check=False).returncode == 0:
                return branch
        return "main"

    def ensure_develop(self) -> str:
        if self._run(["git", "rev-parse", "--verify", "develop"], check=False).returncode == 0:
            self._run(["git", "checkout", "develop"])
            return "develop"
        base = self.detect_base_branch()
        self._run(["git", "checkout", "-B", "develop", base])
        return "develop"

    def setup_branch(self, branch: str) -> str:
        self._validate_branch(branch)
        result = self._run(["git", "checkout", "-b", branch], check=False)
        if result.returncode == 0:
            return branch
        self._run(["git", "checkout", branch])
        return branch

    def current_commit(self) -> str:
        return self._run(["git", "rev-parse", "HEAD"]).stdout.strip()

    def changed_files(self) -> list[str]:
        lines = self._run(["git", "status", "--porcelain", "--untracked-files=all"]).stdout.splitlines()
        return sorted({line[3:].strip().replace("\\", "/") for line in lines if len(line) > 3})

    def changed_files_since(self, commit: str) -> list[str]:
        lines = self._run(
            ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", commit, "HEAD"]
        ).stdout.splitlines()
        return sorted({line.strip().replace("\\", "/") for line in lines if line.strip()})

    def stage_files(self, files: list[Path]) -> None:
        if not files:
            return
        staged = {str(path.resolve().relative_to(self.project_dir.resolve())).replace("\\", "/") for path in files}
        protected = staged & self._baseline_paths
        if protected:
            raise RuntimeError(f"refusing to stage pre-existing dirty paths: {', '.join(sorted(protected))}")
        self._run(["git", "add", "--", *[str(path) for path in files]])

    def final_commit(self, task_description: str, summary: str) -> None:
        self._ensure_identity()
        staged = self._run(["git", "diff", "--cached", "--quiet"], check=False)
        if staged.returncode == 0:
            return
        subject = f"feat: {task_description[:70].strip()}"
        self._commit_with_signing_fallback(["commit", "-m", subject, "-m", summary])

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

    def target_validation_available(self, project_dir: Path) -> bool:
        return self._validation_script(project_dir) is not None

    def merge_to_develop(self, branch: str) -> bool:
        if not self.run_target_validation(self.project_dir):
            return False
        original = self._run(["git", "branch", "--show-current"], check=False).stdout.strip() or branch
        self._run(["git", "checkout", "develop"])
        result = self._run(
            ["git", "merge", "--no-ff", "-m", f"Merge branch '{branch}' into develop", branch],
            check=False,
        )
        if result.returncode != 0 and self._is_signing_failure(result.stderr):
            self._run(["git", "merge", "--abort"], check=False)
            result = self._run(
                ["git", "-c", "commit.gpgsign=false", "merge", "--no-ff", "-m", f"Merge branch '{branch}' into develop", branch],
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

    def _commit_with_signing_fallback(self, args: list[str]) -> None:
        result = self._run(["git", *args], check=False)
        if result.returncode == 0:
            return
        if self._is_signing_failure(result.stderr):
            self._run(["git", "-c", "commit.gpgsign=false", *args])
            return
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: git {args}")

    @staticmethod
    def _is_signing_failure(stderr: str) -> bool:
        lowered = (stderr or "").lower()
        return "gpg" in lowered and "sign" in lowered

    def _ensure_identity(self) -> None:
        name = os.environ.get("GIT_AUTHOR_NAME", "").strip()
        email = os.environ.get("GIT_AUTHOR_EMAIL", "").strip()
        if bool(name) != bool(email):
            raise RuntimeError("GIT_AUTHOR_NAME and GIT_AUTHOR_EMAIL must be provided together")
        if name and email:
            self._run(["git", "config", "--local", "user.name", name])
            self._run(["git", "config", "--local", "user.email", email])
            return
        name = self._run(["git", "config", "--local", "--get", "user.name"], check=False).stdout.strip()
        email = self._run(["git", "config", "--local", "--get", "user.email"], check=False).stdout.strip()
        if not name or not email:
            raise RuntimeError("Git identity missing. Configure local user.name/user.email or paired GIT_AUTHOR_* values.")

    def _require_repository(self) -> None:
        root = self._run(["git", "rev-parse", "--show-toplevel"], check=False)
        if root.returncode != 0 or not root.stdout.strip():
            raise RuntimeError("target is not a Git repository")
        if Path(root.stdout.strip()).resolve() != self.project_dir.resolve():
            raise RuntimeError("project directory must be the Git repository root")

    def _validate_branch(self, branch: str) -> None:
        result = self._run(["git", "check-ref-format", "--branch", branch], check=False)
        if result.returncode != 0 or result.stdout.strip() != branch:
            raise RuntimeError(f"invalid Git branch name: {branch!r}")

    def _require_current_branch(self, expected: str) -> None:
        result = self._run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
        actual = result.stdout.strip()
        if result.returncode != 0 or not actual:
            raise RuntimeError("cannot resume mission on detached HEAD")
        if actual != expected:
            raise RuntimeError(f"cannot resume branch {expected!r}; current branch is {actual!r}")

    def _dirty_baseline(self) -> DirtyBaseline:
        result = self._run(["git", "status", "--porcelain=v1", "--untracked-files=all"], check=False)
        if result.returncode != 0:
            raise RuntimeError("could not inspect Git worktree")
        paths: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            raw = line[3:].strip()
            if " -> " in raw:
                raw = raw.rsplit(" -> ", 1)[-1]
            path = (self.project_dir / raw).resolve()
            relative = str(path.relative_to(self.project_dir.resolve())).replace("\\", "/")
            digest = sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
            paths.append({"path": relative, "sha256": digest, "status": line[:2]})
        return DirtyBaseline(tuple(sorted(paths, key=lambda item: item["path"])))

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
