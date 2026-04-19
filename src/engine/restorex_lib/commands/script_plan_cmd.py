from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import read_text, write_json, write_text
from restorex_lib.run_context import run_paths


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return default
    try:
        obj = json.loads(read_text(path))
        return obj if isinstance(obj, dict) else default
    except Exception:
        return default


def cmd_build_restore_script_plan(workspace: Path, run_id: str) -> None:
    """生成“核心画像 + 本轮动作脚本 + 编排索引”三件套。

    - portrait_core.*：稳定能力层（可跨 run 复用）。
    - generated_restore_actions.*：本轮策略输出（随输入与证据变化）。
    - restore_script_plan.*：阶段编排与引用关系（可审计）。
    """
    paths = run_paths(workspace, run_id)
    queue_obj = _load_json(paths.analysis / "restore_priority_queue.json", {"items": [], "count": 0})
    semantic_obj = _load_json(paths.analysis / "js_semantic_profile.json", {"items": [], "summary": {}})
    fp_obj = _load_json(paths.portraits / "file_portraits.json", {"items": [], "count": 0})
    tp_obj = _load_json(paths.analysis / "third_party_fingerprint.json", {"items": [], "stats": {}})
    cal_obj = _load_json(workspace / "docs" / "history" / "portrait_calibration_latest.json", {"tag_weights": {}})

    semantic_by_file = {str(i.get("file", "")): i for i in semantic_obj.get("items", [])}
    fp_by_file = {str(i.get("file", "")): i for i in fp_obj.get("items", [])}

    # 只先消费 high 队列，避免低价值候选扰动首轮动作计划。
    high_items = [i for i in queue_obj.get("items", []) if str(i.get("restore_priority", "low")) == "high"]
    high_items.sort(
        key=lambda x: (
            -int(x.get("score", 0) or 0),
            str(x.get("file", "")),
            str(x.get("entity_name", "")),
            int(x.get("line_min", 0) or 0),
        )
    )

    actions: list[dict[str, Any]] = []
    for it in high_items[:20]:
        f = str(it.get("file", "")).strip()
        if not f:
            continue
        sem = semantic_by_file.get(f, {})
        cls = sem.get("class_profiles", []) if isinstance(sem.get("class_profiles", []), list) else []
        objs = sem.get("object_profiles", []) if isinstance(sem.get("object_profiles", []), list) else []
        fns = sem.get("function_profiles", []) if isinstance(sem.get("function_profiles", []), list) else []

        # action_tags 是“动作语义标签”，供后续反馈阶段按标签做校准权重。
        action_tags: list[str] = []
        if any("logger_like" in c.get("tags", []) for c in cls):
            action_tags.append("extract_logger")
        if any("registry_like" in o.get("tags", []) for o in objs):
            action_tags.append("extract_registry")
        if any("bridge_command_flow" in fn.get("tags", []) for fn in fns):
            action_tags.append("promote_bridge_symbols")
        if any("state_transition_flow" in fn.get("tags", []) or "ui_action_flow" in fn.get("tags", []) for fn in fns):
            action_tags.append("promote_flow_symbols")
        if not action_tags:
            action_tags.append("generic_symbol_promote")

        tag_weights = cal_obj.get("tag_weights", {}) if isinstance(cal_obj.get("tag_weights", {}), dict) else {}
        tag_weight = max([float(tag_weights.get(t, 1.0)) for t in action_tags] + [1.0])
        weighted_score = int(round(float(it.get("score", 0) or 0) * tag_weight))

        actions.append(
            {
                "file": f,
                "origin_label": str(fp_by_file.get(f, {}).get("origin_label", "unknown")),
                "priority": str(it.get("restore_priority", "low")),
                "score": int(it.get("score", 0) or 0),
                "weighted_score": weighted_score,
                "tag_weight": round(tag_weight, 4),
                "action_tags": action_tags,
                "bridge_calls": it.get("bridge_calls", []),
                "entity_name": str(it.get("entity_name", "__module__")),
            }
        )
    actions.sort(
        key=lambda x: (
            -int(x.get("weighted_score", 0) or 0),
            -int(x.get("score", 0) or 0),
            str(x.get("file", "")),
            str(x.get("entity_name", "")),
        )
    )

    core_portrait = {
        "run_id": run_id,
        "core_version": "1.0",
        "semantic_rules_source": "spec/semantic_rules.json",
        "inputs": {
            "file_portraits": "analysis/file_portraits.json",
            "class_portraits": "analysis/class_portraits.json",
            "semantic_profile": "analysis/js_semantic_profile.json",
            "third_party_fingerprint": "analysis/third_party_fingerprint.json",
        },
        "summary": {
            "semantic_summary": semantic_obj.get("summary", {}),
            "third_party_stats": tp_obj.get("stats", {}),
            "high_priority_items": len(high_items),
        },
        "capabilities": [
            "origin_layer_inference",
            "file_and_entity_portraits",
            "semantic_tag_detection",
            "third_party_fingerprint",
        ],
    }

    generated_actions = {
        "run_id": run_id,
        "source": "analysis/restore_priority_queue.json + analysis/js_semantic_profile.json",
        "count": len(actions),
        "items": actions,
    }

    plan = {
        "run_id": run_id,
        "core_portrait_ref": "analysis/portrait_core.json",
        "generated_actions_ref": "analysis/generated_restore_actions.json",
        "stages": [
            {
                "stage": "portrait_core",
                "inputs": [
                    "analysis/file_portraits.json",
                    "analysis/class_portraits.json",
                    "analysis/js_semantic_profile.json",
                    "analysis/third_party_fingerprint.json",
                ],
                "goal": "建立可复用、项目无关的核心画像能力",
            },
            {
                "stage": "generated_script",
                "inputs": ["analysis/restore_priority_queue.json", "analysis/js_semantic_profile.json", "analysis/evidence_matrix.json"],
                "goal": "基于画像生成本轮可执行动作脚本（仅当轮有效）",
                "planned_actions_ref": "analysis/generated_restore_actions.json",
            },
            {
                "stage": "verification",
                "inputs": ["reports/verify_report.json"],
                "goal": "校验契约与一致性，确认输出可执行",
            },
            {
                "stage": "test_diagnosis",
                "inputs": ["reports/verify_report.json", "analysis/js_semantic_profile.json"],
                "goal": "失败归因到画像不足/脚本问题/验证规则问题",
            },
        ],
        "metrics": {
            "high_priority_items": len(high_items),
            "planned_actions": len(actions),
            "semantic_summary": semantic_obj.get("summary", {}),
            "third_party_stats": tp_obj.get("stats", {}),
            "has_calibration": bool(cal_obj.get("tag_weights")),
        },
    }

    write_json(paths.analysis / "portrait_core.json", core_portrait)
    write_json(paths.analysis / "generated_restore_actions.json", generated_actions)
    write_json(paths.analysis / "restore_script_plan.json", plan)

    core_md = [
        "# Portrait Core",
        "",
        f"- run_id: `{run_id}`",
        "- semantic_rules_source: `spec/semantic_rules.json`",
        f"- high_priority_items: `{len(high_items)}`",
        "",
        "## Capabilities",
    ]
    core_md.extend([f"- {x}" for x in core_portrait.get("capabilities", [])])
    write_text(paths.analysis / "portrait_core.md", "\n".join(core_md))

    actions_md = [
        "# Generated Restore Actions",
        "",
        f"- run_id: `{run_id}`",
        f"- count: `{len(actions)}`",
        "",
        "## Actions",
    ]
    if actions:
        for a in actions[:60]:
            actions_md.append(
                f"- {a['file']} | tags={','.join(a['action_tags'])} | priority={a['priority']} | "
                f"score={a['score']} weighted={a['weighted_score']} weight={a['tag_weight']}"
            )
    else:
        actions_md.append("- none")
    write_text(paths.analysis / "generated_restore_actions.md", "\n".join(actions_md))

    md = [
        "# Restore Script Plan",
        "",
        f"- run_id: `{run_id}`",
        f"- high_priority_items: `{len(high_items)}`",
        f"- planned_actions: `{len(actions)}`",
        "- core: `analysis/portrait_core.json`",
        "- generated_actions: `analysis/generated_restore_actions.json`",
        "",
        "## Stage Flow",
        "- portrait_core -> generated_script -> verification -> test_diagnosis",
        "",
        "## Planned Actions (Top)",
    ]
    if actions:
        for a in actions[:30]:
            md.append(
                f"- {a['file']} | tags={','.join(a['action_tags'])} | priority={a['priority']} | "
                f"score={a['score']} weighted={a['weighted_score']} weight={a['tag_weight']}"
            )
    else:
        md.append("- none")
    write_text(paths.analysis / "restore_script_plan.md", "\n".join(md))
