from __future__ import annotations

from mission_orchestrator.domain.design import DesignEdge, DesignNode

_NODE_MARKS = (("CREATE", "+"), ("CHANGE", "~"), ("REMOVE", "-"))
_EDGE_MARKS = {"CREATE": "+", "REMOVE": "-"}


def render_map_diff(nodes: list[DesignNode], edges: list[DesignEdge]) -> str:
    lines: list[str] = []
    for intent, mark in _NODE_MARKS:
        for node in sorted((n for n in nodes if n.intent == intent), key=lambda n: n.id):
            entry = f"{mark} {intent} {node.label}"
            if node.locator:
                entry += f" ({node.locator})"
            entry += f" [{node.level}]"
            if node.description:
                entry += f" — {node.description}"
            lines.append(entry)
    for edge in sorted((e for e in edges if e.intent in _EDGE_MARKS), key=lambda e: (e.source, e.target)):
        lines.append(f"{_EDGE_MARKS[edge.intent]} {edge.source} -{edge.relation}-> {edge.target}")
    if not lines:
        return "Design map: no proposed changes."
    keep = sum(1 for node in nodes if node.intent == "KEEP")
    if keep:
        lines.append(f"= KEEP: {keep}")
    return "Design map diff:\n" + "\n".join(lines)
