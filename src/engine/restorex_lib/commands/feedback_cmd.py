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


def cmd_build_feedback(workspace: Path, run_id: str) -> None:
    """基于“计划动作 vs 实际改名落地”生成反馈与校准。

    该阶段不直接改写源码，只产出下一轮调参依据：
    - action_feedback.*：本轮执行效果
    - portrait_calibration.*：标签权重建议
    """
    paths = run_paths(workspace, run_id)
    actions_obj = _load_json(paths.analysis / "generated_restore_actions.json", {"items": []})
    mapping_obj = _load_json(paths.analysis / "mapping_index.json", {"applied_renames": []})
    verify_obj = _load_json(paths.reports / "verify_report.json", {"ok": False, "issues": []})
    semantic_obj = _load_json(paths.analysis / "js_semantic_profile.json", {"summary": {}})

    actions = actions_obj.get("items", []) if isinstance(actions_obj.get("items", []), list) else []
    applied = mapping_obj.get("applied_renames", []) if isinstance(mapping_obj.get("applied_renames", []), list) else []

    applied_by_file: dict[str, int] = {}
    for x in applied:
        f = str(x.get("file", "")).strip()
        if not f:
            continue
        applied_by_file[f] = applied_by_file.get(f, 0) + 1

    tag_stats: dict[str, dict[str, Any]] = {}
    file_feedback: list[dict[str, Any]] = []
    for action in actions:
        f = str(action.get("file", "")).strip()
        tags = [str(t).strip() for t in action.get("action_tags", []) if str(t).strip()]
        file_applied = int(applied_by_file.get(f, 0))
        file_success = file_applied > 0
        file_feedback.append(
            {
                "file": f,
                "action_tags": tags,
                "planned_score": int(action.get("score", 0) or 0),
                "applied_renames": file_applied,
                "success": file_success,
            }
        )
        for t in tags:
            st = tag_stats.setdefault(
                t,
                {"tag": t, "planned_actions": 0, "successful_actions": 0, "applied_renames_total": 0},
            )
            st["planned_actions"] += 1
            st["applied_renames_total"] += file_applied
            if file_success:
                st["successful_actions"] += 1

    tag_items: list[dict[str, Any]] = []
    for t, st in sorted(tag_stats.items(), key=lambda kv: kv[0]):
        planned = int(st["planned_actions"])
        success = int(st["successful_actions"])
        rate = (success / planned) if planned > 0 else 0.0
        st["success_rate"] = round(rate, 4)
        tag_items.append(st)

    # 简单校准策略：成功率高则上调，低则下调，作为下一轮脚本计划参考权重。
    calibration_weights: dict[str, float] = {}
    for st in tag_items:
        rate = float(st["success_rate"])
        if rate >= 0.8:
            w = 1.15
        elif rate >= 0.5:
            w = 1.0
        elif rate > 0:
            w = 0.9
        else:
            w = 0.8
        calibration_weights[st["tag"]] = w

    feedback = {
        "run_id": run_id,
        "verify_ok": bool(verify_obj.get("ok", False)),
        "issues_total": len(verify_obj.get("issues", [])) if isinstance(verify_obj.get("issues", []), list) else 0,
        "summary": {
            "planned_actions": len(actions),
            "files_with_success": sum(1 for x in file_feedback if x["success"]),
            "files_without_success": sum(1 for x in file_feedback if not x["success"]),
            "applied_renames_total": sum(int(x["applied_renames"]) for x in file_feedback),
        },
        "tag_feedback": tag_items,
        "file_feedback": file_feedback,
    }
    write_json(paths.analysis / "action_feedback.json", feedback)

    calibration = {
        "run_id": run_id,
        "source": "analysis/action_feedback.json",
        "semantic_summary": semantic_obj.get("summary", {}),
        "tag_weights": calibration_weights,
        "next_run_hints": [
            {
                "hint": "favor_high_weight_tags",
                "description": "下轮脚本生成阶段优先高权重 action_tags",
            },
            {
                "hint": "deprioritize_zero_success_tags",
                "description": "下轮降低连续零成功标签的动作权重",
            },
        ],
    }
    write_json(paths.analysis / "portrait_calibration.json", calibration)
    # 持久化到非 output 目录，供下一轮清空 output 后继续加载校准权重。
    write_json(workspace / "docs" / "history" / "portrait_calibration_latest.json", calibration)

    md = [
        "# Action Feedback",
        "",
        f"- run_id: `{run_id}`",
        f"- verify_ok: `{feedback['verify_ok']}`",
        f"- planned_actions: `{feedback['summary']['planned_actions']}`",
        f"- files_with_success: `{feedback['summary']['files_with_success']}`",
        f"- applied_renames_total: `{feedback['summary']['applied_renames_total']}`",
        "",
        "## Tag Feedback",
    ]
    if tag_items:
        for st in tag_items:
            md.append(
                f"- {st['tag']} | planned={st['planned_actions']} success={st['successful_actions']} "
                f"rate={st['success_rate']} weight={calibration_weights.get(st['tag'], 1.0)}"
            )
    else:
        md.append("- none")
    write_text(paths.analysis / "action_feedback.md", "\n".join(md))

    cal_md = [
        "# Portrait Calibration",
        "",
        f"- run_id: `{run_id}`",
        "- source: `analysis/action_feedback.json`",
        "",
        "## Tag Weights",
    ]
    if calibration_weights:
        for k in sorted(calibration_weights):
            cal_md.append(f"- {k}: `{calibration_weights[k]}`")
    else:
        cal_md.append("- none")
    write_text(paths.analysis / "portrait_calibration.md", "\n".join(cal_md))
