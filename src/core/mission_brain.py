"""Central Mission brain contract for auditable planning and dispatch.

This module deliberately contains deterministic policy only. It does not pretend to
replace model reasoning: Mission remains the single coordination authority, while
workers and tools contribute specialist analysis and execution evidence.
"""
from __future__ import annotations

from typing import Any


def build_mission_brain_contract(nodes: list[Any]) -> dict[str, Any]:
    """Build an explicit, serializable central-coordination contract for a plan."""
    decisions: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    workforce_counts: dict[str, int] = {}
    for raw_node in nodes:
        if hasattr(raw_node, "to_dict") and callable(raw_node.to_dict):
            node = raw_node.to_dict()
        elif isinstance(raw_node, dict):
            node = raw_node
        else:
            continue

        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        status = str(node.get("status") or "planned").strip()
        gap_type = str(node.get("gap_type") or "").strip()
        if status == "needs_input":
            decision = "request_missing_input"
        elif status == "reuse_existing" or gap_type == "reuse_existing":
            decision = "reuse_verified_knowledge_first"
        elif status == "needs_learning" or gap_type in {"capability_gap", "experience_gap"}:
            decision = "research_capability_gap"
        elif status == "ready" or gap_type == "knowledge_gap":
            decision = "run_minimal_validating_experiment"
        else:
            decision = "inspect_evidence_before_dispatch"

        counts[decision] = counts.get(decision, 0) + 1
        trace = node.get("decision_trace", [])
        workforce_decision = node.get("workforce_decision")
        if isinstance(workforce_decision, dict):
            workforce_result = str(workforce_decision.get("decision") or "not_evaluated")
            workforce_counts[workforce_result] = workforce_counts.get(workforce_result, 0) + 1
        else:
            workforce_decision = None
        decisions.append({
            "node_id": node_id,
            "status": status,
            "decision": decision,
            "reasoning": [str(item) for item in node.get("reasoning", []) if str(item).strip()],
            "blockers": [str(item) for item in node.get("blockers", []) if str(item).strip()],
            "verified_skill_ids": [
                str(item) for item in node.get("recommended_skill_ids", []) if str(item).strip()
            ],
            "validation_checks": [
                str(item) for item in node.get("validation_checks", []) if str(item).strip()
            ],
            "workforce_decision": workforce_decision,
            "decision_trace": trace if isinstance(trace, list) else [],
        })

    return {
        "schema_version": "mission.brain.contract.v1",
        "decision_owner": "mission",
        "dispatch_mode": "centralized",
        "worker_to_worker_dispatch": "request_mission_coordination",
        "knowledge_policy": "verified_reuse_before_new_research",
        "validation_policy": "evidence_required_before_knowledge_promotion",
        "replanning_policy": "mission_reassesses_after_execution_result_or_blocker",
        "workforce_policy": {
            "decision_owner": "mission",
            "catalog": "workspace/.organization",
            "selection_mode": "capability_match_then_worker_availability",
            "parallelism_policy": "explicit_parallel_safe_only",
            "recommendation_only": True,
            "dispatch_authorized": False,
            "automatic_role_creation": False,
            "automatic_worker_creation": False,
            "automatic_worker_cloning": False,
            "dynamic_dispatch_enabled": False,
            "decision_counts": workforce_counts,
        },
        "node_decisions": decisions,
        "decision_counts": counts,
    }


def index_mission_brain_decisions(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the serialized decisions for runtime action annotation."""
    items = contract.get("node_decisions", []) if isinstance(contract, dict) else []
    return {
        str(item.get("node_id")): item
        for item in items
        if isinstance(item, dict) and str(item.get("node_id") or "").strip()
    }
