"""Agent-facing enrichment for MCP tool responses."""

from __future__ import annotations

from typing import Any, Dict

from backend.execution_quality import assess_from_response_dict, format_agent_notice


def enrich_turn_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Attach execution_quality, agent_notice, and the squad plan to a full-turn
    API payload. A gated (soft-confirm) response ran nothing and already carries
    `plan` + `agent_notice`, so it passes through untouched."""
    if not payload or payload.get("reset"):
        return payload
    if payload.get("requires_confirmation"):
        return payload
    enriched = dict(payload)
    quality = enriched.get("execution_quality") or assess_from_response_dict(enriched)
    enriched["execution_quality"] = quality
    notice = format_agent_notice(quality)
    if notice:
        enriched["agent_notice"] = notice
    # DEC-030: surface the pre-flight squad plan alongside the completed turn.
    plan = (enriched.get("metadata") or {}).get("squad_plan")
    if plan and "plan" not in enriched:
        enriched["plan"] = plan
    return enriched


def enrich_turn_record(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Attach quality to stepwise turn API payloads when execution is present."""
    if not payload:
        return payload
    enriched = dict(payload)
    turn = enriched.get("turn") or {}
    execution = turn.get("execution") or enriched.get("execution")
    if not execution:
        return enriched
    exec_payload = {
        "stage1": (execution.get("stage1") or {}).get("responses")
        if isinstance(execution.get("stage1"), dict)
        else execution.get("stage1"),
        "stage2": execution.get("stage2"),
        "stage3": execution.get("stage3"),
        "metadata": execution.get("metadata") or turn.get("metadata") or {},
    }
    quality = assess_from_response_dict(exec_payload)
    enriched["execution_quality"] = quality
    notice = format_agent_notice(quality)
    if notice:
        enriched["agent_notice"] = notice
    return enriched