from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Mapping

from mission_orchestrator.application.errors import MaxRetriesExceeded, MaxTurnsExceeded, PhaseTimeout
from mission_orchestrator.application.phase_registry import GRAPH, get_phase_config
from mission_orchestrator.application.services import AppServices
from mission_orchestrator.domain.block import BlockKind, BlockReason
from mission_orchestrator.domain.mission import MissionContext, MissionSnapshot
from mission_orchestrator.domain.phase import PhaseName, PhaseResult
from mission_orchestrator.ports.agent_client import AgentRequest, ConversationRequest
from mission_orchestrator.ports.tool_registry import ToolEnvironment


GRAPH_INSTRUCTIONS = """Use the SQLite code graph when useful.
Database artifact: code_graph.db in the harness workspace.
Structural tables: nodes(id,type,file,name), edges(source,target,relation,file) with defines/imports/inherits.
Lexical usage table: lexical_refs(source,target,relation,file) with calls/references by textual name.
Files table: files(path,mtime_ns). Meta table: meta(key,value) includes observed_revision.
Keep code graph findings as supporting context; source files remain authoritative."""


@dataclass(frozen=True)
class PhaseExecution:
    result: PhaseResult | None = None
    block: BlockReason | None = None


class PhaseExecutor:
    def __init__(self, services: AppServices, context: MissionContext) -> None:
        self.services = services
        self.context = context

    def run(
        self,
        phase: PhaseName,
        *,
        variables: Mapping[str, str] | None = None,
        evaluate_gate: bool = True,
    ) -> PhaseExecution:
        config = get_phase_config(phase)
        self.services.logger.log(f"phase start: {phase.value}")
        self.services.state.update_phase(
            MissionSnapshot(
                phase=phase.value,
                mode=self.context.mode.value,
                gate=self.services.state.get_gate_mode().value,
            )
        )
        request_variables = self._base_variables() | dict(variables or {})
        includes = self._resolve_includes(config.includes)
        user_prompt = self.services.prompts.render_user_prompt(
            config.template_file,
            request_variables,
            includes,
        )
        system_prompt = (
            self.services.prompts.render_system_prompt(config.agent_file) if config.agent_file else ""
        )
        tool_schemas = self.services.tools.schemas_for(config.tools)
        request_cls = ConversationRequest if config.is_conversation else AgentRequest
        request = request_cls(
            phase_name=phase.value,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_names=config.tools,
            tool_schemas=tool_schemas,
            max_turns=config.max_turns,
            timeout_seconds=config.timeout_seconds,
        )
        started = monotonic()
        try:
            if config.is_conversation:
                result = self.services.agent.run_conversation(request)  # type: ignore[arg-type]
            else:
                result = self.services.agent.run_phase(request)
        except PhaseTimeout as exc:
            return PhaseExecution(exc.metrics, BlockReason(BlockKind.TIMEOUT, phase.value, str(exc)))
        except MaxTurnsExceeded as exc:
            return PhaseExecution(exc.metrics, BlockReason(BlockKind.MAX_TURNS, phase.value, str(exc)))
        except MaxRetriesExceeded as exc:
            return PhaseExecution(exc.metrics, BlockReason(BlockKind.API_RETRIES, phase.value, str(exc)))
        except Exception as exc:
            return PhaseExecution(None, BlockReason(BlockKind.API_RETRIES, phase.value, str(exc)))

        self.services.logger.metric(
            {
                "phase": phase.value,
                "turns": result.turns,
                "elapsed_seconds": result.elapsed_seconds or round(monotonic() - started, 3),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }
        )
        if evaluate_gate and config.gate_artifact:
            gate = self.services.gates.evaluate(phase.value, config.gate_artifact)
            if not gate.passed:
                return PhaseExecution(result, BlockReason(BlockKind.GATE_FAIL, phase.value, gate.detail))
        self.services.logger.log(f"phase done: {phase.value}")
        return PhaseExecution(result, None)

    def _base_variables(self) -> dict[str, str]:
        return {
            "TASK": self.context.task,
            "BRANCH": self.context.branch,
            "MODE": self.context.mode.value,
            "PROJECT_DIR": str(self.context.project_dir),
            "HARNESS_PATH": self.context.harness_display_path,
            "MISSION_TAG": self.context.mission_tag,
            "PROJECT_NAME": self.context.project_name,
        }

    def _resolve_includes(self, includes: Mapping[str, str]) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for key, artifact_name in includes.items():
            if artifact_name == GRAPH:
                resolved[key] = GRAPH_INSTRUCTIONS
            else:
                resolved[key] = self.services.artifacts.read_text(
                    artifact_name,
                    default="(not available yet)",
                )
        return resolved

    @property
    def tool_environment(self) -> ToolEnvironment:
        return ToolEnvironment(self.context.project_dir, self.context.harness_dir)

