from __future__ import annotations

import argparse
import json
import signal
import threading
from pathlib import Path

from mission_orchestrator.adapters.control.http_server import ControlHttpServer
from mission_orchestrator.adapters.filesystem.workspace import sanitize
from mission_orchestrator.application.control_plane import control_plane_for
from mission_orchestrator.bootstrap import RuntimeConfig, build_runtime
from mission_orchestrator.cli import load_runtime_env
from mission_orchestrator.domain.mission import GateMode, MissionMode


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_dir = Path(args.project).resolve()
    load_runtime_env(project_dir)
    task = args.task.strip() or "Graph Lab mission"
    branch = args.branch or sanitize(task.lower().replace(" ", "-"), max_len=60)
    runtime = build_runtime(
        RuntimeConfig(
            task=task,
            branch=branch,
            mode=MissionMode.parse(args.mode),
            project_dir=project_dir,
            gate_mode=GateMode.MANUAL if args.gate else GateMode.AUTO,
            no_grill=args.no_grill,
            max_tasks=args.max_tasks,
            resume=args.resume,
            provider=args.provider,
            model=args.model,
        )
    )
    server = ControlHttpServer(
        control_plane_for(runtime),
        host=args.host,
        port=args.port,
        token=args.token,
    )
    server.start()
    print(
        json.dumps(
            {
                "type": "harness_worker_ready",
                "api_version": "v1",
                "url": server.base_url,
                "token": server.token,
                "mission_id": runtime.context.mission_tag,
                "project_dir": str(runtime.context.project_dir),
                "branch": runtime.context.branch,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    stopped = threading.Event()

    def stop(signum, frame) -> None:  # noqa: ANN001
        stopped.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(signum, stop)
        except (OSError, ValueError):
            pass
    try:
        stopped.wait()
    finally:
        server.stop()
        runtime.services.logger.log("worker exit")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mission-worker")
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", default="Graph Lab mission")
    parser.add_argument("--branch")
    parser.add_argument("--mode", choices=[*([mode.value for mode in MissionMode]), "spec-plan"], default="full")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--no-grill", action="store_true")
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--provider", choices=("anthropic", "deepseek"))
    parser.add_argument("--model")
    parser.add_argument("--host", choices=("127.0.0.1", "localhost", "::1"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
