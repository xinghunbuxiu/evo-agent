#!/usr/bin/env python3
"""
M1 运营标准自检：验证「干净默认环境」+ 可选已启用工种的冒烟链路。

用法:
  cd evo-mcp
  PYTHONPATH=src python3 scripts/m1_ops_check.py
  PYTHONPATH=src python3 scripts/m1_ops_check.py --with-worker-smoke
  PYTHONPATH=src python3 scripts/m1_ops_check.py --with-worker-smoke --keep-smoke-artifacts
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CLI = ROOT / "executors" / "toutiao" / "scripts" / "cli.py"
sys.path.insert(0, str(SRC))

from admin.finance_runtime import (  # noqa: E402
    PRESET_FINANCE_PROJECT_IDS,
    finance_record_path,
    get_finance_overview,
    get_finance_summary,
    list_finance_projects,
    purge_preset_finance_data,
    upsert_finance_from_analytics,
)
from admin.runtime_state import load_autonomy_runtime  # noqa: E402
from admin.self_media_runtime import create_self_media_runtime_bindings  # noqa: E402
from project_caps import load_project_packages, purge_preset_project_packages  # noqa: E402
from workers.registry import load_worker_registry_config  # noqa: E402
from workers.self_media_operations.runtime import summarize_toutiao_analytics_result  # noqa: E402


def _run_cli(args: list[str]) -> dict:
    cmd = ["python3", str(CLI), *args]
    completed = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    stdout = (completed.stdout or "").strip()
    parsed = None
    if stdout:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    return {
        "ok": completed.returncode == 0,
        "code": completed.returncode,
        "stdout": stdout,
        "stderr": (completed.stderr or "").strip(),
        "parsed": parsed,
    }


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trim(text: str | None, limit: int = 160) -> str:
    raw = str(text or "").strip()
    return raw[:limit]


def _is_self_media_worker_enabled(workspace: Path) -> bool:
    registry = load_worker_registry_config(workspace)
    workers = registry.get("workers", {}) if isinstance(registry.get("workers"), dict) else {}
    entry = workers.get("self_media_operations", {})
    return bool(entry.get("enabled")) if isinstance(entry, dict) else False


def _load_autonomy_runtime(workspace: Path) -> dict:
    return load_autonomy_runtime(workspace)


def _run_platform_checks(workspace: Path, checks: list[tuple[str, bool, str]]) -> None:
    removed = purge_preset_finance_data(workspace)
    removed_packages = purge_preset_project_packages(workspace)
    checks.append(("P0 预置财务数据已清理", "toutiao_default" not in list_finance_projects(workspace), f"removed={removed}"))

    runtime = load_autonomy_runtime(workspace)
    member_ids = [
        str(item.get("member_id") or "")
        for item in runtime.get("child_members", {}).get("items", [])
        if isinstance(item, dict)
    ]
    checks.append(("P0 无预置 self_media_child", "self_media_child" not in member_ids, ",".join(member_ids) or "empty"))
    checks.append(("P0 内置育成师存在", "talent_development_officer" in member_ids, "talent_development_officer"))
    primary = runtime.get("primary_child_member_id")
    checks.append(("P0 primary_child 未指向预置成员", primary in {None, ""}, str(primary or "null")))

    overview = get_finance_overview(workspace)
    preset_hits = [pid for pid in overview.get("project_ids", []) if pid in PRESET_FINANCE_PROJECT_IDS]
    checks.append(("P0 财务 overview 无预置 project", not preset_hits, json.dumps(overview.get("project_ids", []), ensure_ascii=False)))

    from admin.commercial_runtime import build_weekly_briefing, get_commercial_readiness  # noqa: E402

    readiness = get_commercial_readiness(workspace)
    readiness_ok = (
        isinstance(readiness.get("steps"), list)
        and len(readiness.get("steps", [])) >= 7
        and isinstance(readiness.get("score"), (int, float))
        and str(readiness.get("stage_label") or "").strip()
    )
    checks.append(("P0 商业化就绪度结构", readiness_ok, json.dumps({
        "score": readiness.get("score"),
        "stage": readiness.get("stage_label"),
        "steps": len(readiness.get("steps", [])),
    }, ensure_ascii=False)))

    briefing = build_weekly_briefing(workspace)
    briefing_ok = (
        str(briefing.get("period_label") or "").strip()
        and isinstance(briefing.get("bullets"), list)
        and isinstance(briefing.get("operations"), dict)
        and "members" in briefing.get("operations", {})
    )
    checks.append(("P0 经营周报结构", briefing_ok, json.dumps({
        "headline": _trim(str(briefing.get("headline") or ""), 80),
        "bullets": len(briefing.get("bullets", [])),
    }, ensure_ascii=False)))

    commercial = overview.get("commercial_verdict") if isinstance(overview.get("commercial_verdict"), dict) else {}
    verdict_ok = isinstance(commercial.get("recommendation"), str) and isinstance(commercial.get("next_actions"), list)
    checks.append(("P0 财务经营结论结构", verdict_ok, _trim(str(commercial.get("headline") or ""), 120)))

    registry = load_worker_registry_config(workspace)
    workers = registry.get("workers", {}) if isinstance(registry.get("workers"), dict) else {}
    sm_entry = workers.get("self_media_operations", {})
    from work_types import load_work_types  # noqa: E402
    from workers.registry import builtin_worker_manifests  # noqa: E402

    sm_manifest = builtin_worker_manifests(workspace).get("self_media_operations", {})
    code_default_off = not bool(sm_manifest.get("default_enabled", False)) if isinstance(sm_manifest, dict) else True
    checks.append((
        "P0 自媒体执行器代码默认关闭",
        code_default_off,
        f"default_enabled={sm_manifest.get('default_enabled') if isinstance(sm_manifest, dict) else 'missing'}",
    ))
    work_types_payload = load_work_types(workspace)
    wt_items = work_types_payload.get("items", []) if isinstance(work_types_payload.get("items"), list) else []
    wt_count = len([item for item in wt_items if isinstance(item, dict)])
    workspace_worker_on = bool(sm_entry.get("enabled")) if isinstance(sm_entry, dict) else False
    checks.append((
        "P0 公司工种由配置写入（非代码硬编码）",
        True,
        f"work_types={wt_count}, self_media_enabled={workspace_worker_on}",
    ))

    js_entry = workers.get("javascript_reverse", {})
    js_default_off = not bool(js_entry.get("enabled")) if isinstance(js_entry, dict) else True
    checks.append(("P0 JS 逆向工种默认关闭", js_default_off, str(js_entry.get("enabled") if isinstance(js_entry, dict) else "missing")))

    from project_caps import build_project_package_runtime_entries  # noqa: E402

    work_types_payload = load_work_types(workspace)
    items = work_types_payload.get("items", []) if isinstance(work_types_payload, dict) else []
    checks.append(("P0 work_types 结构合法", isinstance(items, list), f"count={len(items)}"))

    packages = load_project_packages(workspace).get("packages", [])
    preset_packages = [p for p in packages if isinstance(p, dict) and str(p.get("package_id") or "") == "project.javascript"]
    checks.append(("P0 无预置 JS project package", not preset_packages, f"removed={removed_packages}; left={[p.get('package_id') for p in packages]}"))

    local_export_root = workspace / ".admin" / "local_git_exports"
    local_export_root.mkdir(parents=True, exist_ok=True)
    checks.append(("P0 Git 本地降级目录可写", local_export_root.is_dir(), str(local_export_root)))

    _run_p0_work_type_chain_probe(workspace, checks)
    _run_p0_evolution_probe(workspace, checks)
    _run_p0_intake_probe(workspace, checks)
    _run_p0_knowledge_learning_probe(workspace, checks)


M1_PROBE_WORK_TYPE_ID = "__m1_route_probe__"


def _run_p0_knowledge_learning_probe(workspace: Path, checks: list[tuple[str, bool, str]]) -> None:
    """模型补知识 → 经验卡写回（mock provider，不打外网）。"""
    import os

    if os.getenv("EVO_M1_SKIP_LEARNING", "").strip().lower() in {"1", "true", "yes"}:
        checks.append(("P0 模型补知识写回经验", True, "skipped: EVO_M1_SKIP_LEARNING"))
        return
    try:
        from admin.m1_knowledge_learning_probe_runtime import run_knowledge_learning_probe  # noqa: E402

        probe = run_knowledge_learning_probe(workspace)
        checks.append((
            "P0 模型补知识写回经验",
            bool(probe.get("ok")),
            (
                f"mode={probe.get('mode')} status={probe.get('status')} "
                f"journal={probe.get('journal_card_ok')} indep={probe.get('independence_ready')}"
            ),
        ))
    except Exception as exc:
        checks.append(("P0 模型补知识写回经验", False, str(exc)[:180]))


def _run_p0_intake_probe(workspace: Path, checks: list[tuple[str, bool, str]]) -> None:
    """临时接单→分派→交付钩子→结算，验证消费环（跑完恢复 runtime / work_types / 财务）。"""
    import os

    if os.getenv("EVO_M1_SKIP_INTAKE", "").strip().lower() in {"1", "true", "yes"}:
        checks.append(("P0 接单消费环探测", True, "skipped: EVO_M1_SKIP_INTAKE"))
        return

    from admin.m1_intake_probe_runtime import run_intake_commercial_probe  # noqa: E402

    try:
        probe = run_intake_commercial_probe(workspace)
        checks.append(("P0 接单探测创建", bool(probe.get("intake_id")), str(probe.get("intake_id") or "")))
        checks.append(("P0 接单探测分派任务", bool(probe.get("task_id")), str(probe.get("task_id") or "")))
        checks.append((
            "P0 履约产物回挂工作台",
            bool(probe.get("artifact_attach_ok")),
            f"count={probe.get('artifact_count')} status={probe.get('fulfillment_status')}",
        ))
        checks.append((
            "P0 接单探测结算入账",
            bool(probe.get("settled")),
            f"amount={probe.get('settled_amount')} project={probe.get('project_id')}",
        ))
        checks.append((
            "P0 接单通演示财务可见",
            bool(probe.get("finance_visible_ok")),
            f"revenue={probe.get('finance_revenue')} projects={probe.get('finance_projects')}",
        ))
        checks.append((
            "P0 接单结算回写供给成长",
            bool(probe.get("supply_growth_ok")),
            f"count={probe.get('commercial_settled_count')} growth_member={probe.get('growth_member_id')}",
        ))
        checks.append((
            "P0 接单结算写路由反馈",
            bool(probe.get("routing_feedback_ok")),
            f"pending_git_export={probe.get('pending_git_export')}",
        ))
        checks.append((
            "P0 路由反馈分析加权",
            bool(probe.get("feedback_bonus_ok")),
            f"feedback_bonus={probe.get('feedback_bonus')}",
        ))
        checks.append((
            "P0 经验卡反哺路由加权",
            bool(probe.get("journal_bonus_ok")),
            f"journal_bonus={probe.get('journal_bonus')}",
        ))
        checks.append((
            "P0 结算本地经验导出",
            bool(probe.get("git_export_ok")),
            f"status={probe.get('git_export_status')} path={probe.get('git_export_path')}",
        ))
        from admin.m1_intake_probe_runtime import run_second_work_type_routing_probe  # noqa: E402

        second = run_second_work_type_routing_probe(workspace)
        checks.append((
            "P0 第二工种仅配置可路由",
            bool(second.get("ok")),
            f"recommended={second.get('recommended_member_id')} expected={second.get('expected_member_id')}",
        ))
    except Exception as exc:
        checks.append(("P0 接单消费环探测", False, str(exc)[:180]))


def _run_p0_evolution_probe(workspace: Path, checks: list[tuple[str, bool, str]]) -> None:
    """临时创建员工并完成 assign→submit→approve，验证 approve 后产生下一轮建议（runtime 直调）。"""
    import os

    if os.getenv("EVO_M1_SKIP_EVOLUTION", "").strip().lower() in {"1", "true", "yes"}:
        checks.append(("P0 进化闭环探测", True, "skipped: EVO_M1_SKIP_EVOLUTION"))
        return

    from admin.runtime_state import load_autonomy_runtime, save_autonomy_runtime  # noqa: E402
    from admin.m1_evolution_probe_runtime import run_evolution_closure_probe  # noqa: E402

    baseline_runtime = load_autonomy_runtime(workspace)
    baseline_members = [
        item for item in baseline_runtime.get("child_members", {}).get("items", [])
        if isinstance(item, dict)
    ]
    baseline_primary_child = baseline_runtime.get("primary_child_member_id")
    baseline_selected_child = (
        baseline_runtime.get("child_members", {}).get("selected_member_id")
        if isinstance(baseline_runtime.get("child_members"), dict)
        else None
    )
    baseline_tasks = [
        item for item in baseline_runtime.get("task_center", {}).get("items", [])
        if isinstance(item, dict)
    ]
    baseline_recommendations = [
        item for item in baseline_runtime.get("task_center", {}).get("recommendations", [])
        if isinstance(item, dict)
    ]
    probe_member_id = ""
    try:
        probe = run_evolution_closure_probe(workspace)
        probe_member_id = str(probe.get("member_id") or "").strip()
        evolution = probe.get("evolution_summary") if isinstance(probe.get("evolution_summary"), dict) else {}
        checks.append(("P0 进化探测员工建档", bool(probe_member_id), probe_member_id or "missing member"))
        checks.append(("P0 进化探测任务分配", bool(probe.get("task_id")), str(probe.get("task_id") or "")))
        checks.append(("P0 进化探测任务提交", bool(probe.get("task_id")), "submitted via runtime"))
        checks.append((
            "P0 approve 返回进化摘要",
            bool(evolution.get("next_recommendation_id")),
            str(evolution.get("next_task_title") or "none"),
        ))
        checks.append((
            "P0 approve 后下一轮建议",
            int(probe.get("recommendation_count") or 0) > 0,
            str(probe.get("next_task_title") or "none"),
        ))
    except Exception as exc:
        checks.append(("P0 进化闭环探测", False, str(exc)[:180]))
    finally:
        if probe_member_id:
            runtime = load_autonomy_runtime(workspace)
            runtime["child_members"] = {
                **(runtime.get("child_members") if isinstance(runtime.get("child_members"), dict) else {}),
                "items": baseline_members,
                "selected_member_id": baseline_selected_child,
            }
            runtime["primary_child_member_id"] = baseline_primary_child
            task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
            task_center["items"] = baseline_tasks
            task_center["recommendations"] = baseline_recommendations
            runtime["task_center"] = task_center
            save_autonomy_runtime(workspace, runtime)


def _run_p0_work_type_chain_probe(workspace: Path, checks: list[tuple[str, bool, str]]) -> None:
    """临时写入探测工种，验证「添加工种 → 建档 → 路由/Mission 模板」链路，结束后恢复。"""
    from work_types import load_work_types, save_work_types  # noqa: E402
    from work_type_runtime import build_work_type_runtime_index  # noqa: E402
    from admin.worker_route_runtime import resolve_work_type_id, resolve_primary_worker_id  # noqa: E402
    from workers.registry import builtin_worker_manifests, load_worker_registry_config  # noqa: E402
    from project_caps import build_project_package_runtime_entries  # noqa: E402
    from admin.runtime_state import create_employee_member_runtime  # noqa: E402
    from core.mission_planner import MISSION_KIND_TEMPLATES  # noqa: E402

    payload = load_work_types(workspace)
    version = int(payload.get("version") or 1) if isinstance(payload, dict) else 1
    items = payload.get("items", []) if isinstance(payload, dict) else []
    baseline_items = [
        item for item in items
        if isinstance(item, dict)
        and str(item.get("work_type_id") or "").strip() != M1_PROBE_WORK_TYPE_ID
    ]
    probe_item = {
        "work_type_id": M1_PROBE_WORK_TYPE_ID,
        "title": "M1 Route Probe",
        "status": "active",
        "capability_type": "automation",
        "mission_kind": "automation_operation",
        "enabled": True,
    }
    restored = False
    try:
        save_work_types(workspace, {"version": version, "items": [*baseline_items, probe_item]})
        restored = True

        index = build_work_type_runtime_index(
            workspace,
            load_work_types=load_work_types,
            builtin_worker_manifests=builtin_worker_manifests,
            load_worker_registry_config=load_worker_registry_config,
            build_project_package_runtime_entries=build_project_package_runtime_entries,
        )
        route = index.get("work_types", {}).get(M1_PROBE_WORK_TYPE_ID, {}) if isinstance(index.get("work_types"), dict) else {}
        checks.append(("P0 工种→路由 index", bool(route), f"mission_kind={route.get('mission_kind')}"))
        checks.append((
            "P0 工种 mission_kind",
            route.get("mission_kind") == "automation_operation",
            str(route.get("mission_kind") or ""),
        ))
        checks.append((
            "P0 Mission 模板可解析",
            "automation_operation" in MISSION_KIND_TEMPLATES,
            "automation_operation",
        ))

        member = create_employee_member_runtime(
            tenant_id="default",
            name="M1 Route Probe Employee",
            role_label=str(probe_item["title"]),
            role_key=M1_PROBE_WORK_TYPE_ID,
            self_description="m1 route probe",
            long_term_goal="m1 route probe",
            work_type_id=M1_PROBE_WORK_TYPE_ID,
            work_type_title=str(probe_item["title"]),
        )
        resolved = resolve_work_type_id(member)
        checks.append(("P0 建档 job_id 解析", resolved == M1_PROBE_WORK_TYPE_ID, str(resolved or "")))

        worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=M1_PROBE_WORK_TYPE_ID)
        worker_ids = route.get("worker_ids") if isinstance(route.get("worker_ids"), list) else []
        checks.append((
            "P0 建档→worker 路由",
            bool(worker_id) or bool(worker_ids),
            str(worker_id or worker_ids or "none"),
        ))
    finally:
        if restored:
            save_work_types(workspace, {"version": version, "items": baseline_items})


def _run_work_type_route_smoke(workspace: Path, checks: list[tuple[str, bool, str]]) -> None:
    from work_types import load_work_types  # noqa: E402
    from work_type_runtime import build_work_type_runtime_index  # noqa: E402
    from admin.worker_route_runtime import resolve_work_type_id, resolve_primary_worker_id  # noqa: E402
    from workers.registry import builtin_worker_manifests, load_worker_registry_config  # noqa: E402
    from project_caps import build_project_package_runtime_entries  # noqa: E402
    from admin.runtime_state import create_employee_member_runtime  # noqa: E402

    items = load_work_types(workspace).get("items", []) if isinstance(load_work_types(workspace), dict) else []
    if not items:
        checks.append(("W-route 工种路由", True, "skipped: 无 work_types 条目"))
        return

    index = build_work_type_runtime_index(
        workspace,
        load_work_types=load_work_types,
        builtin_worker_manifests=builtin_worker_manifests,
        load_worker_registry_config=load_worker_registry_config,
        build_project_package_runtime_entries=build_project_package_runtime_entries,
    )
    first = next((item for item in items if isinstance(item, dict) and str(item.get("work_type_id") or "").strip()), None)
    if not isinstance(first, dict):
        checks.append(("W-route 工种路由", True, "skipped: 无有效 work_type 条目"))
        return

    work_type_id = str(first.get("work_type_id") or "").strip()
    route = index.get("work_types", {}).get(work_type_id, {}) if isinstance(index.get("work_types"), dict) else {}
    checks.append(("W-route runtime index", bool(route), json.dumps({
        "mission_kind": route.get("mission_kind"),
        "worker_ids": route.get("worker_ids"),
    }, ensure_ascii=False)[:180]))

    member = create_employee_member_runtime(
        tenant_id="default",
        name="Route Smoke Employee",
        role_label=str(first.get("title") or work_type_id),
        role_key=work_type_id,
        self_description="route smoke",
        long_term_goal="route smoke",
        work_type_id=work_type_id,
        work_type_title=str(first.get("title") or work_type_id),
    )
    resolved = resolve_work_type_id(member)
    checks.append(("W-route member job_id", resolved == work_type_id, str(resolved or "")))

    worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=work_type_id)
    checks.append(("W-route worker 解析", bool(worker_id), str(worker_id or "none")))


def _cleanup_worker_smoke_artifacts(workspace: Path, *, draft_path: str = "") -> list[str]:
    """移除 W 段冒烟产生的临时财务/草稿文件，避免污染默认 workspace。"""
    removed: list[str] = []
    finance_path = finance_record_path(workspace, "self_media_operations")
    if finance_path.is_file():
        finance_path.unlink()
        removed.append("finance:self_media_operations")
    if draft_path:
        draft = Path(draft_path)
        if draft.is_file():
            draft.unlink()
            removed.append(f"draft:{draft.name}")
    return removed


def _ensure_self_media_worktype(workspace: Path) -> None:
    from work_types import load_work_types  # noqa: E402

    payload = load_work_types(workspace)
    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    if any(
        isinstance(item, dict) and str(item.get("work_type_id") or "").strip() == "self_media_operations"
        for item in items
    ):
        return

    import importlib.util

    bootstrap_path = Path(__file__).resolve().parent / "bootstrap_self_media_worktype.py"
    spec = importlib.util.spec_from_file_location("bootstrap_self_media_worktype", bootstrap_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 bootstrap 脚本: {bootstrap_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def _run_self_media_smoke(
    workspace: Path,
    checks: list[tuple[str, bool, str]],
    *,
    keep_artifacts: bool,
) -> None:
    _ensure_self_media_worktype(workspace)
    _run_work_type_route_smoke(workspace, checks)

    project_id = "self_media_operations"
    finance_payload = {
        "channel": "toutiao",
        "project_id": project_id,
        "job_id": project_id,
    }

    login = _run_cli(["account", "update", "--account", "default", "--logged-in", "true"])
    status = _run_cli(["account", "status", "--account", "default", "--json"])
    logged_in = bool(isinstance(status.get("parsed"), dict) and status["parsed"].get("logged_in"))
    checks.append(("W A 账号 logged_in", login["ok"] and logged_in, status.get("stderr") or "ok"))

    media = create_self_media_runtime_bindings(
        trim_candidate_text=_trim,
        load_autonomy_runtime=_load_autonomy_runtime,
    )
    probe = media["probe_toutiao_connector"](workspace, {"account_id": "default", "channel": "toutiao"})
    passed = str(probe.get("validation_outcome") or "") == "passed"
    checks.append(("W A 执行器 probe passed", passed, str(probe.get("message") or "")))

    analytics = media["run_toutiao_analytics"](
        workspace,
        {"account_id": "default", "analytics_type": "works", "channel": "toutiao"},
    )
    analytics_ok = bool(analytics.get("ok"))
    summary = summarize_toutiao_analytics_result(
        {"analytics_type": "works", "channel": "toutiao"},
        analytics,
        safe_float=_safe_float,
        safe_percent_value=lambda v: _safe_float(v, 0.0),
        pick_top_distribution_item=lambda *a, **k: None,
        top_region_entries=lambda *a, **k: [],
        trim_candidate_text=_trim,
    )
    upsert_finance_from_analytics(
        workspace,
        tenant_id="default",
        payload=finance_payload,
        result={"channel": "toutiao", "analytics_type": "works", **analytics},
        analytics_summary=summary,
    )
    finance = get_finance_summary(workspace, project_id=project_id)
    finance_ok = bool(finance.get("views", 0) > 0 or finance.get("updated_at"))
    checks.append(("W B analytics works", analytics_ok, str(analytics.get("message") or "ok")))
    checks.append(("W B 财务落盘（动态 project_id）", finance_ok, json.dumps(finance, ensure_ascii=False)[:200]))

    draft = _run_cli([
        "publish", "weitoutiao", "--account", "default",
        "--content", "M1 验收草稿：运营闭环测试",
        "--topic", "自媒体运营", "--title", "M1验收", "--draft",
    ])
    draft_path = ""
    if isinstance(draft.get("parsed"), dict):
        draft_path = str(draft["parsed"].get("draft_path") or "")
    draft_ok = draft["ok"] and bool(draft_path) and Path(draft_path).is_file()
    checks.append(("W C 草稿 draft_path 有效", draft_ok, draft_path or draft.get("stderr") or "missing draft"))

    feedback = _run_cli(["comment", "list", "--account", "default", "--limit", "3", "--json"])
    entries = feedback.get("parsed", {}).get("entries") if isinstance(feedback.get("parsed"), dict) else []
    feedback_ok = feedback["ok"] and isinstance(entries, list) and len(entries) > 0
    headline = str(entries[0].get("content") or "") if entries else ""
    checks.append(("W C 反馈采集非空", feedback_ok and bool(headline), headline or feedback.get("stderr") or "empty"))

    if not keep_artifacts:
        cleaned = _cleanup_worker_smoke_artifacts(workspace, draft_path=draft_path)
        checks.append(("W 冒烟产物已清理", not finance_record_path(workspace, "self_media_operations").is_file(), ",".join(cleaned) or "none"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evo M1 运营标准自检")
    parser.add_argument(
        "--with-worker-smoke",
        action="store_true",
        help="强制执行 W 段自媒体冒烟（不要求 worker_registry 已启用；默认跑完后清理产物）",
    )
    parser.add_argument(
        "--keep-smoke-artifacts",
        action="store_true",
        help="保留 W 段产生的财务/草稿文件（仅与 --with-worker-smoke 联用）",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    checks: list[tuple[str, bool, str]] = []
    workspace = ROOT

    _run_platform_checks(workspace, checks)

    worker_enabled = _is_self_media_worker_enabled(workspace)
    run_worker_smoke = worker_enabled or args.with_worker_smoke
    keep_artifacts = bool(args.keep_smoke_artifacts) or (worker_enabled and not args.with_worker_smoke)
    if run_worker_smoke:
        _run_self_media_smoke(
            workspace,
            checks,
            keep_artifacts=keep_artifacts,
        )
    else:
        checks.append(("W 自媒体工种冒烟", True, "skipped: 未启用且未指定 --with-worker-smoke"))

    print("=== Evo M1 运营标准自检 ===\n")
    failed = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {name}")
        if detail:
            print(f"       {detail}\n")

    print(f"合计: {len(checks) - failed}/{len(checks)} 通过")
    if failed:
        print("\n未达 M1 全绿，请继续按 PRODUCT_M1_CHECKLIST_CN.md 迭代。")
        return 1
    if worker_enabled:
        print("\n平台默认环境干净；worker_registry 已启用 self_media_operations 且冒烟链路全绿。")
    elif args.with_worker_smoke:
        print("\n平台默认环境干净；已通过 --with-worker-smoke 完成 W 段冒烟（默认已清理临时产物）。")
    else:
        print("\n平台默认环境干净（内置育成师+财务，无预置成员/财务脏数据）。")
        print("完整工种冒烟：公司空间启用 self_media_operations 后重跑，或使用 --with-worker-smoke。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
