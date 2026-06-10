"""Tool-call logging callback factory for the mission harness.

Exports PhaseLogger class and backward-compatible factory functions.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.harness.telemetry import write_phase_event

TOOL_LABELS = {
    "Read": "Reading",
    "Write": "Writing",
    "Edit": "Editing",
    "Bash": "Running",
    "Grep": "Searching",
    "Glob": "Finding files",
    "Agent": "Spawning agent",
    "WebFetch": "Fetching URL",
    "WebSearch": "Searching web",
}


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def describe_tool(name, tool_input):
    label = TOOL_LABELS.get(name, name)
    if name in ("Read", "Edit", "Write"):
        fp = tool_input.get("file_path", "")
        short = fp.split("/")[-1] if "/" in fp else fp.split("\\")[-1] if "\\" in fp else fp
        return f"{label} {short}"
    if name == "Bash":
        cmd = tool_input.get("command", "")
        short = cmd[:60] + ("..." if len(cmd) > 60 else "")
        return f"{label}: {short}"
    if name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"{label} '{pattern}'"
    if name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"{label} {pattern}"
    return label


class PhaseLogger:

    def __init__(self, harness_dir: Path, log_file: Path | None = None):
        self.harness_dir = harness_dir
        self.log_file = log_file if log_file is not None else harness_dir / "mission.log"
        self.progress_file = harness_dir / "_progress.txt"

    def log(self, msg: str) -> None:
        ts = timestamp()
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def on_tool_call(self, name: str, tool_input: dict) -> None:
        desc = describe_tool(name, tool_input)
        ts = timestamp()
        line = f"[{ts}]   > {desc}"
        print(line, flush=True)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        try:
            with open(self.progress_file, "w", encoding="utf-8") as f:
                f.write(f"[{ts}] {desc}")
        except Exception:
            pass

    def write_metric(self, phase_name: str, *, turns: int = 0,
                     elapsed: float = 0.0, input_tokens: int = 0,
                     output_tokens: int = 0, model: str | None = None,
                     result: str) -> None:
        try:
            record = {
                "phase": phase_name,
                "model": model,
                "turns": turns,
                "elapsed_s": round(elapsed, 1),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
            with open(self.harness_dir / "_metrics.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            write_phase_event(
                self.harness_dir,
                phase_name,
                turns=turns,
                elapsed=elapsed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                result=result,
            )
        except Exception:
            pass


_INSTANCES: dict[tuple, PhaseLogger] = {}


def _get_logger(harness_dir: Path, log_file: Path | None = None) -> PhaseLogger:
    key = (harness_dir, log_file)
    if key not in _INSTANCES:
        _INSTANCES[key] = PhaseLogger(harness_dir, log_file)
    return _INSTANCES[key]


def make_logger(harness_dir: Path, log_file: Path | None = None) -> Callable[[str], None]:
    return _get_logger(harness_dir, log_file).log


def make_tool_callback(harness_dir: Path, log_file: Path | None = None) -> Callable[[str, dict], None]:
    return _get_logger(harness_dir, log_file).on_tool_call


def _write_metric(harness: Path, phase_name: str, *, turns: int = 0,
                  elapsed: float = 0.0, input_tokens: int = 0,
                  output_tokens: int = 0, model: str | None = None,
                  result: str) -> None:
    _get_logger(harness).write_metric(
        phase_name, turns=turns, elapsed=elapsed,
        input_tokens=input_tokens, output_tokens=output_tokens, model=model, result=result,
    )
