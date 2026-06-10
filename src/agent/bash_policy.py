from __future__ import annotations

import re
import shlex
from pathlib import Path

from src.agent.path_policy import _validate_access_path

ALLOWED_BASH_COMMANDS = frozenset({
    "python3", "python", "git",
    "ls", "cat", "head", "tail", "wc", "sort",
    "grep", "awk", "sed", "jq", "file", "diff",
    "tr", "cut", "uniq", "tee", "find",
    "mkdir", "cp", "mv", "rm", "touch", "chmod",
    "echo", "printf", "true", "false", "test",
    "cd", "export", "read",
})

_DANGEROUS_PATTERNS = re.compile(r"\$\(|`|<\(|\)\(|<<")
_CONTROL_OPERATORS = {"&&", "||", ";"}
_UNSUPPORTED_SHELL_TOKENS = {"<", ">", ">>", "<<", "&", "&>", ">&", "2>"}


def _strip_token_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _tokenize_bash_command(command: str) -> list[str]:
    lexer = shlex.shlex(
        command.replace("\n", " ; "),
        posix=False,
        punctuation_chars="|&;<>",
    )
    lexer.whitespace_split = True
    tokens = [_strip_token_quotes(token) for token in lexer]
    for token in tokens:
        if token in _UNSUPPORTED_SHELL_TOKENS or "<" in token or ">" in token:
            raise ValueError(
                f"shell token '{token}' is not allowed "
                "(redirection, background jobs, and file descriptor operators are blocked)"
            )
    return tokens


def _split_bash_pipelines(tokens: list[str]) -> list[tuple[str, list[list[str]]]]:
    pipelines: list[tuple[str, list[list[str]]]] = []
    pending_operator = ";"
    pipeline: list[list[str]] = []
    command: list[str] = []

    def flush_command() -> None:
        nonlocal command
        if command:
            pipeline.append(command)
            command = []

    def flush_pipeline() -> None:
        nonlocal pipeline
        flush_command()
        if pipeline:
            pipelines.append((pending_operator, pipeline))
            pipeline = []

    for token in tokens:
        if token == "|":
            flush_command()
            if not pipeline:
                raise ValueError("empty command before pipe")
            continue
        if token in _CONTROL_OPERATORS:
            flush_pipeline()
            pending_operator = token
            continue
        if token in {"||", "&&"}:
            flush_pipeline()
            pending_operator = token
            continue
        command.append(token)

    flush_pipeline()
    if not pipelines and tokens:
        raise ValueError("empty command")
    return pipelines


def _validate_bash_path_token(token: str, cwd: Path, project_dir: Path, harness_dir: Path) -> None:
    if not token or token.startswith("-"):
        return
    token_path = Path(token)
    parts = set(token_path.parts)
    path_like = token_path.is_absolute() or ".." in parts or "/" in token or "\\" in token
    if not path_like:
        return
    path = token_path if token_path.is_absolute() else cwd / token_path
    _validate_access_path(str(path), project_dir, harness_dir)


def _validate_bash_command_args(
    argv: list[str],
    cwd: Path,
    project_dir: Path,
    harness_dir: Path,
) -> None:
    if not argv:
        raise ValueError("empty command")
    basename = Path(argv[0]).name
    if basename not in ALLOWED_BASH_COMMANDS:
        raise ValueError(f"command '{basename}' is not in the allowed list")

    if basename in {"echo", "printf", "true", "false", "test", "export", "read"}:
        return
    if basename in {"python", "python3", "git"}:
        for token in argv[1:]:
            token_path = Path(token)
            if token_path.is_absolute() or ".." in set(token_path.parts):
                _validate_bash_path_token(token, cwd, project_dir, harness_dir)
        return

    for token in argv[1:]:
        _validate_bash_path_token(token, cwd, project_dir, harness_dir)


def _validate_bash_command(
    command: str,
    project_dir: Path | None = None,
    harness_dir: Path | None = None,
) -> list[tuple[str, list[list[str]]]]:
    match = _DANGEROUS_PATTERNS.search(command)
    if match:
        raise ValueError(
            f"shell construct '{match.group()}' is not allowed "
            "(subshells, process substitution, heredocs, and backticks are blocked)"
        )
    tokens = _tokenize_bash_command(command)
    pipelines = _split_bash_pipelines(tokens)
    cwd = project_dir.resolve() if project_dir is not None else Path.cwd()
    if project_dir is not None and harness_dir is not None:
        for _, pipeline in pipelines:
            for argv in pipeline:
                _validate_bash_command_args(argv, cwd, project_dir, harness_dir)
    else:
        for _, pipeline in pipelines:
            for argv in pipeline:
                if not argv:
                    raise ValueError("empty command")
                basename = Path(argv[0]).name
                if basename not in ALLOWED_BASH_COMMANDS:
                    raise ValueError(f"command '{basename}' is not in the allowed list")
    return pipelines
