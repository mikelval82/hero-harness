from __future__ import annotations

from pathlib import Path

from src.core.paths import AGENTS_DIR, PROMPTS_DIR
from src.core.block_state import BlockKind, BlockReason
from src.core.gate import check_gate
from src.core.model_policy import select_model_for_phase
from src.agent.tool_schema import TOOL_DEFINITIONS
from src.agent import loop as agent_loop
from src.harness.prompt_renderer import render_prompt, load_agent_system
from src.harness.phase_logger import make_tool_callback, _write_metric


class PhaseRunner:

    def __init__(self, client, ctx, blocked):
        self.client = client
        self.ctx = ctx
        self.blocked = blocked

    def _resolve_includes(self, config, extra_includes=None):
        resolved = {}
        for key, path in config.includes.items():
            if path.startswith("prompts/"):
                resolved[key] = str(PROMPTS_DIR / path[8:])
            else:
                resolved[key] = str(self.ctx.harness / path)
        if extra_includes:
            resolved.update(extra_includes)
        return resolved

    def _tool_wrote_path(self, block, target) -> bool:
        if block.name != "Write":
            return False
        raw_path = block.input.get("file_path", "")
        if not raw_path:
            return False
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.ctx.harness / candidate
        try:
            return candidate.resolve() == target.resolve()
        except OSError:
            return False

    def _status_artifact_stop_condition(self, config):
        if not config.gate:
            return None
        gate_file = self.ctx.harness / config.gate

        def should_stop(tool_blocks):
            if not any(self._tool_wrote_path(block, gate_file) for block in tool_blocks):
                return False
            if not gate_file.is_file():
                return False
            content = gate_file.read_text(encoding="utf-8", errors="replace")
            return "STATUS: DONE" in content or "STATUS: BLOCKED" in content

        return should_stop

    def _execute_phase(self, phase_name, agent_fn, agent_kwargs, log=None):
        try:
            phase_result = agent_fn(**agent_kwargs)
        except agent_loop.PhaseTimeout as exc:
            _write_metric(self.ctx.harness, phase_name, **(exc.metrics or {}), result="timeout")
            self.blocked.reason = BlockReason(BlockKind.TIMEOUT, phase=phase_name)
            if log:
                log(f"<<< BLOCKED: {self.blocked.value}")
            return None
        except agent_loop.MaxTurnsExceeded as exc:
            _write_metric(self.ctx.harness, phase_name, **(exc.metrics or {}), result="max_turns")
            self.blocked.reason = BlockReason(BlockKind.MAX_TURNS, phase=phase_name)
            if log:
                log(f"<<< BLOCKED: {self.blocked.value}")
            return None
        except agent_loop.MaxRetriesExceeded as exc:
            _write_metric(self.ctx.harness, phase_name, **(exc.metrics or {}), result="api_retries")
            self.blocked.reason = BlockReason(BlockKind.API_RETRIES, phase=phase_name)
            if log:
                log(f"<<< BLOCKED: {self.blocked.value}")
            return None

        _write_metric(self.ctx.harness, phase_name, turns=phase_result.turns,
                      elapsed=phase_result.elapsed, input_tokens=phase_result.input_tokens,
                      output_tokens=phase_result.output_tokens, model=phase_result.model,
                      result="success")
        if log:
            log(f"<<< Phase done: {phase_name}")
        return phase_result

    def run(self, config, variables, extra_includes=None,
            gate_file_override=None, phase_name_override=None,
            timeout_override=None, max_turns_override=None, log=None):
        if self.blocked.reason:
            return None

        phase_name = phase_name_override or config.name
        print(f"Phase: {phase_name}")
        if log:
            log(f">>> Phase: {phase_name}")
        model_selection = select_model_for_phase(
            phase_name,
            mode=self.ctx.mode,
            task_complexity=variables.get("TASK_COMPLEXITY"),
        )
        if log:
            log(f"Model: {model_selection.model} ({model_selection.tier}, {model_selection.reason})")

        includes = self._resolve_includes(config, extra_includes)
        template_path = str(PROMPTS_DIR / config.template)
        user_prompt = render_prompt(template_path, variables, includes, self.ctx.harness_win)

        system_prompt = ""
        if config.agent:
            agent_path = str(AGENTS_DIR / config.agent)
            system_prompt = load_agent_system(agent_path, self.ctx.harness_win)

        PROMPT_TOKEN_BUDGET = 4000
        CHARS_PER_TOKEN = 4
        total_chars = len(user_prompt) + len(system_prompt)
        estimated_tokens = total_chars // CHARS_PER_TOKEN
        if estimated_tokens > PROMPT_TOKEN_BUDGET:
            msg = (f"WARNING: {phase_name} prompt is ~{estimated_tokens} tokens "
                   f"(budget: {PROMPT_TOKEN_BUDGET})")
            print(msg)
            if log:
                log(msg)

        tool_names = {t.strip() for t in config.tools.split(",")}
        tools = [t for t in TOOL_DEFINITIONS if t["name"] in tool_names]
        on_tool_call = make_tool_callback(self.ctx.harness)

        extra = {}
        max_turns = max_turns_override if max_turns_override is not None else config.max_turns
        if max_turns is not None:
            extra["max_turns"] = max_turns
        timeout = timeout_override if timeout_override is not None else config.timeout

        phase_result = self._execute_phase(phase_name, agent_loop.run_phase, {
            "client": self.client,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "tools": tools,
            "phase_name": phase_name,
            "project_dir": self.ctx.project_dir,
            "harness_dir": self.ctx.harness,
            "on_tool_call": on_tool_call,
            "on_log": log,
            "timeout": timeout,
            "model": model_selection.model,
            **extra,
        }, log=log)
        if phase_result is None:
            return None

        gate_file = gate_file_override
        if gate_file is None and config.gate:
            gate_file = self.ctx.harness / config.gate
        if gate_file is not None:
            passed, reason = check_gate(gate_file, phase_name, log=log)
            if not passed:
                _write_metric(self.ctx.harness, phase_name, turns=phase_result.turns,
                              elapsed=phase_result.elapsed, input_tokens=phase_result.input_tokens,
                              output_tokens=phase_result.output_tokens, model=phase_result.model,
                              result="gate_fail")
                self.blocked.reason = BlockReason(BlockKind.GATE_FAIL, phase=phase_name, detail=reason)
                return None

        return phase_result.text

    def run_conversation(self, config, variables, get_input, log=None):
        if self.blocked.reason:
            return None

        phase_name = config.name
        print(f"Phase: {phase_name}")
        if log:
            log(f">>> Phase: {phase_name}")
        model_selection = select_model_for_phase(
            phase_name,
            mode=self.ctx.mode,
            task_complexity=variables.get("TASK_COMPLEXITY"),
        )
        if log:
            log(f"Model: {model_selection.model} ({model_selection.tier}, {model_selection.reason})")

        includes = self._resolve_includes(config)
        template_path = str(PROMPTS_DIR / config.template)
        user_prompt = render_prompt(template_path, variables, includes, self.ctx.harness_win)
        agent_path = str(AGENTS_DIR / config.agent)
        system_prompt = load_agent_system(agent_path, self.ctx.harness_win)

        tool_names = {t.strip() for t in config.tools.split(",")}
        tools = [t for t in TOOL_DEFINITIONS if t["name"] in tool_names]
        on_tool_call = make_tool_callback(self.ctx.harness)

        phase_result = self._execute_phase(phase_name, agent_loop.run_conversation, {
            "client": self.client,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "tools": tools,
            "phase_name": phase_name,
            "project_dir": self.ctx.project_dir,
            "harness_dir": self.ctx.harness,
            "get_human_input": get_input,
            "should_stop_after_tools": self._status_artifact_stop_condition(config),
            "on_tool_call": on_tool_call,
            "on_log": log,
            "timeout": config.timeout,
            "max_turns": config.max_turns,
            "model": model_selection.model,
        }, log=log)
        if phase_result is None:
            return None

        gate_file = None
        if config.gate:
            gate_file = self.ctx.harness / config.gate
        if gate_file is not None:
            passed, reason = check_gate(gate_file, phase_name, log=log)
            if not passed:
                _write_metric(self.ctx.harness, phase_name, turns=phase_result.turns,
                              elapsed=phase_result.elapsed, input_tokens=phase_result.input_tokens,
                              output_tokens=phase_result.output_tokens, model=phase_result.model,
                              result="gate_fail")
                self.blocked.reason = BlockReason(BlockKind.GATE_FAIL, phase=phase_name, detail=reason)
                return None

        return phase_result.text
