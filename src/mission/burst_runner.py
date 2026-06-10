from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from src.core.paths import PROMPTS_DIR
from src.core.block_state import BlockKind, BlockReason, BlockState
from src.core.context import PHASE_REGISTRY, PhaseName, MissionContext
from src.core.gate import parse_plan_steps
from src.core.model_policy import select_model_for_phase
from src.agent.tool_schema import TOOL_DEFINITIONS
from src.agent import loop as agent_loop
from src.harness.prompt_renderer import render_prompt
from src.harness.phase_logger import make_tool_callback, _write_metric

if TYPE_CHECKING:
    from src.mission.phase_runner import PhaseRunner


class BurstRunner:

    def __init__(
        self,
        client: Any,
        ctx: MissionContext,
        phase_runner: PhaseRunner,
        blocked: BlockState,
        log: Callable[[str], None],
    ) -> None:
        self.client = client
        self.ctx = ctx
        self.phase_runner = phase_runner
        self.blocked = blocked
        self.log = log

    def run_implement_bursts(
        self,
        task_id: str,
        task_title: str,
        task_vars: dict[str, str] | None = None,
    ) -> None:
        if task_vars is None:
            task = {"id": task_id, "title": task_title}
            task_vars = {
                "TASK_ID": task_id,
                "TASK_TITLE": task_title,
                "TASK_COMPLEXITY": self.ctx.get_task_complexity(task),
                "TASK_PIPELINE": self.ctx.get_task_pipeline_label(task),
                "TASK_COMPLEXITY_REASON": self.ctx.get_task_complexity_reason(task),
            }
        harness = self.ctx.harness
        try:
            plan_text = (harness / "plan.md").read_text(encoding="utf-8")
        except FileNotFoundError:
            plan_text = ""
        steps = parse_plan_steps(plan_text)
        if not steps:
            if self.log:
                self.log("No parseable plan steps — fallback to monolithic implement")
            self.phase_runner.run(
                PHASE_REGISTRY[PhaseName.IMPLEMENT],
                task_vars,
                phase_name_override=f"implement[{task_id}]", log=self.log)
            return

        if self.log:
            step_titles = [s.splitlines()[0].strip() for s in steps]
            self.log(f"Burst mode: {len(steps)} steps — {', '.join(step_titles)}")

        final_text = (
            f"Append surprises and deltas to context-hot.md under ## Implementer ({task_id}).\n"
            "Create status.md from scratch (do not expect an existing one from planner).\n\n"
            "Add a ## Routing section to status.md with `task_complexity:`, "
            "`task_pipeline:`, and `complexity_reason:` copied from Task routing in the prompt.\n\n"
            "If a mission-validate script exists in the project root "
            "(mission-validate.cmd, .bat, .ps1, or .sh), execute it before reporting done. "
            "List all modified/created files in status.md under a ## Files section, one per line.\n\n"
            "Before reporting done, write a ## Self-Verification section in status.md with "
            "tests_run, deterministic_checks_run, acceptance_criteria_checked, "
            "edge_cases_considered, files_touched_reviewed, "
            "harness_artifacts_not_written_to_target, and known_risks."
        )
        progress_file = harness / "_burst_progress.md"
        for i, step in enumerate(steps, 1):
            step_header = step.splitlines()[0].strip() if step.strip() else f"Step {i}"
            if self.log:
                self.log(f"--- Burst {i}/{len(steps)}: {step_header}")
            try:
                progress_content = progress_file.read_text(encoding="utf-8")
            except FileNotFoundError:
                progress_content = ""
            is_last = (i == len(steps))
            variables = {
                **task_vars,
                "TASK_ID": task_id,
                "TASK_TITLE": task_title,
                "PLAN_STEP": step,
                "PROGRESS": progress_content,
                "FINAL_INSTRUCTIONS": final_text if is_last else "",
            }
            gate_override = harness / "status.md" if is_last else None
            try:
                size_before = progress_file.stat().st_size
            except FileNotFoundError:
                size_before = 0
            result = self.phase_runner.run(
                PHASE_REGISTRY[PhaseName.IMPLEMENT_BURSTS], variables,
                gate_file_override=gate_override,
                phase_name_override=f"implement[{task_id}]#{i}",
                log=self.log)
            if result is None:
                if self.log:
                    self.log(f"--- Burst {i}/{len(steps)} FAILED: {step_header}")
                return
            if self.log:
                self.log(f"--- Burst {i}/{len(steps)} done: {step_header}")
            try:
                size_after = progress_file.stat().st_size
            except FileNotFoundError:
                size_after = 0
            if size_after <= size_before:
                with open(progress_file, "a", encoding="utf-8") as f:
                    f.write(f"Step {i}: done\n")
        if self.log:
            self.log(f"All {len(steps)} bursts completed for {task_id}")

    def compact_context(self, task_id: str = "researcher", task_title: str = "Initial exploration") -> None:
        harness = self.ctx.harness
        hot = harness / "context-hot.md"
        if not hot.exists():
            return

        if self.log:
            self.log(f">>> Compacting context for {task_id}")

        user_prompt = render_prompt(
            str(PROMPTS_DIR / "compact-prompt.md"),
            {"TASK_ID": task_id, "TASK_TITLE": task_title},
            {},
            self.ctx.harness_win,
        )
        tools = [t for t in TOOL_DEFINITIONS if t["name"] in {"Read", "Write"}]
        phase_name = f"compact[{task_id}]"
        model_selection = select_model_for_phase(phase_name, mode=self.ctx.mode)
        if self.log:
            self.log(f"Model: {model_selection.model} ({model_selection.tier}, {model_selection.reason})")

        try:
            phase_result = agent_loop.run_phase(
                self.client,
                system_prompt="",
                user_prompt=user_prompt,
                tools=tools,
                phase_name=phase_name,
                project_dir=self.ctx.project_dir,
                harness_dir=harness,
                on_tool_call=make_tool_callback(harness),
                on_log=self.log,
                timeout=PHASE_REGISTRY[PhaseName.COMPACT].timeout,
                model=model_selection.model,
            )
            _write_metric(
                harness,
                phase_name,
                turns=phase_result.turns,
                elapsed=phase_result.elapsed,
                input_tokens=phase_result.input_tokens,
                output_tokens=phase_result.output_tokens,
                model=phase_result.model,
                result="success",
            )
        except agent_loop.PhaseTimeout as exc:
            metrics = {"model": model_selection.model, **(getattr(exc, "metrics", None) or {})}
            _write_metric(harness, phase_name, **metrics, result="timeout")
            self.blocked.reason = BlockReason(BlockKind.TIMEOUT, phase=phase_name)
            return
        except agent_loop.MaxTurnsExceeded as exc:
            metrics = {"model": model_selection.model, **(getattr(exc, "metrics", None) or {})}
            _write_metric(harness, phase_name, **metrics, result="max_turns")
            self.blocked.reason = BlockReason(BlockKind.MAX_TURNS, phase=phase_name)
            return
        except agent_loop.MaxRetriesExceeded as exc:
            metrics = {"model": model_selection.model, **(getattr(exc, "metrics", None) or {})}
            _write_metric(harness, phase_name, **metrics, result="api_retries")
            self.blocked.reason = BlockReason(BlockKind.API_RETRIES, phase=phase_name)
            return

        tmp = harness / "_compact_tmp.md"
        if not tmp.exists():
            print("compact: no output produced, context-hot preserved")
            return
        content_tmp = tmp.read_text(encoding="utf-8")
        tmp_lines = content_tmp.splitlines()
        if len(tmp_lines) < 3:
            print("compact: output too short, context-hot preserved")
            tmp.unlink()
            return

        cold = harness / "context-cold.md"
        with open(cold, "a", encoding="utf-8") as f:
            f.write("\n" + content_tmp + "\n")

        tmp.unlink()
        hot.unlink()

        if self.log:
            self.log(f"<<< Compact done for {task_id}")
