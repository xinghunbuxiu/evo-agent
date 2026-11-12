"""
Mission 规划、执行与续跑接口。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import Request

from admin.mission_runtime import (
    exclusive_mission_claim_lock,
    load_mission_runs,
    load_mission_runs_strict,
    release_worker_claim_for_review,
    save_mission_runs,
)


def register_mission_routes(
    app,
    *,
    workspace: Path,
    task_queue,
    tenant_manager,
    prepare_mission_work_type_bundle: Callable[..., dict],
    mission_planner,
    upsert_plan_learning_tasks: Callable[..., list[str]],
    refresh_mission_runs: Callable[..., dict],
    start_mission: Callable[..., tuple[dict | None, object | None]],
    find_mission_run: Callable[[Path, str], dict | None],
    derive_follow_up_goal: Callable[[dict], str],
    derive_follow_up_context: Callable[[dict], dict],
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
    get_session_user: Callable[[Request], dict | None],
    authorize_tenant: Callable[[dict, str], bool],
    tenant_role: Callable[[dict, str], str | None],
    organization_registry,
    skill_replay_runtime=None,
) -> None:
    @app.post("/api/missions/plan")
    async def plan_mission(request: Request):
        data = await request.json()
        goal = str(data.get("goal") or "").strip()
        work_type_id = str(data.get("work_type_id") or "").strip() or None
        tenant_id = str(data.get("tenant_id") or "default").strip() or "default"
        mission_kind = str(data.get("mission_kind") or "").strip() or None
        context = data.get("context", {})
        if not isinstance(context, dict):
            context = {}
        prepared = prepare_mission_work_type_bundle(
            workspace=workspace,
            work_type_id=work_type_id,
            goal=goal,
            mission_kind=mission_kind,
            context=context,
        )
        goal = str(prepared.get("goal") or "").strip()
        mission_kind = prepared.get("mission_kind")
        context = prepared.get("context", {})
        validation = prepared.get("work_type_validation", {})
        if not goal:
            return error_response("goal 不能为空", 400)
        context.setdefault("work_type_validation", validation)
        plan = mission_planner.plan(
            tenant_id=tenant_id,
            goal=goal,
            mission_kind=mission_kind,
            context=context,
        )
        if prepared.get("work_type"):
            plan["work_type"] = prepared["work_type"]
            plan["work_type_summary"] = prepared.get("work_type_summary")
            plan["work_type_validation"] = validation
            plan["runtime_route"] = prepared.get("runtime_route")
        learning_task_ids = upsert_plan_learning_tasks(
            workspace=workspace,
            tenant_id=tenant_id,
            mission_kind=str(mission_kind or ""),
            goal=goal,
            context=context,
            plan=plan,
        )
        plan["learning_task_ids"] = learning_task_ids
        return success_response(plan, "Mission 规划已生成")

    @app.get("/api/missions/runs")
    async def list_mission_runs(tenant_id: str | None = None, limit: int = 20):
        state = refresh_mission_runs(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            mission_starter=start_mission,
        )
        items = state.get("items", []) if isinstance(state, dict) else []
        filtered = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if tenant_id and item.get("tenant_id") != tenant_id:
                continue
            filtered.append(item)
            if len(filtered) >= max(1, min(limit, 100)):
                break
        return success_response({
            "updated_at": state.get("updated_at"),
            "items": filtered,
        })

    @app.post("/api/missions/{mission_run_id}/skills/{skill_id}/replay")
    async def replay_mission_skill(request: Request, mission_run_id: str, skill_id: str):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        if skill_replay_runtime is None:
            return error_response("Skill Replay Broker 尚未配置；普通 Mission 执行不受影响", 503)
        try:
            data = await request.json()
        except Exception:
            return error_response("请求 JSON 无效", 400)
        if not isinstance(data, dict) or set(data) != {"node_id"}:
            return error_response("请求内容必须只包含 node_id", 400)
        node_id = str(data.get("node_id") or "").strip()
        if not node_id:
            return error_response("必须指定 node_id", 400)
        idempotency_key = str(request.headers.get("idempotency-key") or "").strip().lower()
        try:
            parsed_idempotency_key = uuid.UUID(idempotency_key)
        except (ValueError, AttributeError):
            return error_response("必须通过 Idempotency-Key 请求头提供 UUID 幂等键", 400)
        if str(parsed_idempotency_key) != idempotency_key:
            return error_response("Idempotency-Key 必须是规范 UUID 格式", 400)

        task_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "evo-agent:mission-skill-replay:"
            + ":".join((mission_run_id, skill_id, node_id, idempotency_key)),
        ).hex
        action = {
            "action_type": "skill_replay",
            "status": "running",
            "task_id": task_id,
            "node_id": node_id,
            "title": f"Skill Replay: {skill_id}",
            "skill_id": skill_id,
            "idempotency_key": idempotency_key,
            "created_at": datetime.now().astimezone().isoformat(),
            "detail": "已通过 Mission API 授权，正在向 Broker 提交不可变 Skill 候选",
        }

        # Serialize the durable Mission action creation with other Mission writes.
        with exclusive_mission_claim_lock(workspace):
            try:
                state = load_mission_runs_strict(workspace)
            except (OSError, UnicodeError, ValueError):
                return error_response("Mission 运行记录不可读取，拒绝执行 Skill Replay", 500)
            mission_run = next((
                item for item in state["items"]
                if isinstance(item, dict)
                and str(item.get("mission_run_id") or "") == mission_run_id
            ), None)
            if not isinstance(mission_run, dict):
                return error_response("未找到对应的 mission run", 404)
            tenant_id = str(mission_run.get("tenant_id") or "default")
            if not authorize_tenant(user, tenant_id):
                return error_response("无权访问该租户", 403)
            if tenant_role(user, tenant_id) not in {"tenant_admin", "member"}:
                return error_response("只有租户管理员或成员可以发起 Skill Replay", 403)
            plan = mission_run.get("plan") if isinstance(mission_run.get("plan"), dict) else {}
            nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
            if not any(
                isinstance(node, dict) and str(node.get("id") or "") == node_id
                for node in nodes
            ):
                return error_response("node_id 不属于该 Mission", 400)
            actions = mission_run.get("actions") if isinstance(mission_run.get("actions"), list) else []
            prior_request = next((
                item for item in actions
                if isinstance(item, dict)
                and item.get("action_type") == "skill_replay"
                and item.get("idempotency_key") == idempotency_key
            ), None)
            if isinstance(prior_request, dict):
                if (
                    prior_request.get("skill_id") != skill_id
                    or prior_request.get("node_id") != node_id
                    or prior_request.get("task_id") != task_id
                ):
                    return error_response("该 Idempotency-Key 已用于不同的 Skill Replay 请求", 409)
                if prior_request.get("status") == "completed":
                    cached_operation = prior_request.get("operation_result")
                    if not isinstance(cached_operation, dict):
                        return error_response("该 Replay 已完成但响应快照缺失；拒绝再次执行", 409)
                    return success_response(
                        cached_operation,
                        str(prior_request.get("completion_message") or "已返回同一幂等请求的 Replay 结果"),
                    )
                if prior_request.get("status") == "failed":
                    return error_response(
                        str(prior_request.get("error_message") or "该幂等请求此前已失败；请使用新的 Idempotency-Key 发起新尝试"),
                        int(prior_request.get("error_status") or 409),
                    )
                return error_response("该幂等请求仍在执行或等待人工复核；拒绝重复执行", 409)
            if any(
                isinstance(item, dict)
                and item.get("action_type") == "skill_replay"
                and (
                    item.get("status") == "running"
                    or (
                        item.get("status") == "interrupted"
                        and item.get("recovery_status") == "needs_review"
                    )
                )
                and item.get("skill_id") == skill_id
                and item.get("node_id") == node_id
                for item in actions
            ):
                return error_response(
                    "该 Skill 在此 Mission 节点已有未完成或中断的 Replay；请先核验 Broker 与 Evidence Store，不得直接重跑",
                    409,
                )
            actions.append(action)
            mission_run["actions"] = actions
            mission_run["updated_at"] = datetime.now().astimezone().isoformat()
            save_mission_runs(workspace, state)

        partial_evidence_ref = None
        outcome_indeterminate = False

        def persist_candidate_binding(candidate_binding: dict) -> None:
            if not isinstance(candidate_binding, dict):
                raise ValueError("Replay candidate binding must be an object")
            binding = candidate_binding.get("skill_binding")
            if not isinstance(binding, dict):
                raise ValueError("Replay candidate binding is missing its immutable Skill identity")
            with exclusive_mission_claim_lock(workspace):
                current_state = load_mission_runs_strict(workspace)
                current_run = next((
                    item for item in current_state["items"]
                    if isinstance(item, dict)
                    and str(item.get("mission_run_id") or "") == mission_run_id
                    and item.get("tenant_id") == tenant_id
                ), None)
                if not isinstance(current_run, dict):
                    raise RuntimeError("Mission disappeared before candidate identity could be pinned")
                current_actions = current_run.get("actions") if isinstance(current_run.get("actions"), list) else []
                current_action = next((
                    item for item in current_actions
                    if isinstance(item, dict) and item.get("task_id") == task_id
                ), None)
                if not isinstance(current_action, dict) or current_action.get("status") != "running":
                    raise RuntimeError("Replay action is no longer running; refusing Broker dispatch")
                current_action.update({
                    "skill_binding": binding,
                    "candidate_skill_version": binding.get("skill_version"),
                    "candidate_content_sha256": binding.get("content_sha256"),
                    "stage_request_id": candidate_binding.get("stage_request_id"),
                    "execution_request_id": candidate_binding.get("execution_request_id"),
                    "candidate_pinned_at": datetime.now().astimezone().isoformat(),
                })
                current_run["actions"] = current_actions
                current_run["updated_at"] = datetime.now().astimezone().isoformat()
                save_mission_runs(workspace, current_state)

        try:
            operation = await asyncio.to_thread(
                skill_replay_runtime.replay_candidate,
                tenant_id=tenant_id,
                mission_run=mission_run,
                node_id=node_id,
                task_id=task_id,
                skill_id=skill_id,
                on_candidate_bound=persist_candidate_binding,
            )
        except FileNotFoundError:
            error_status, error_message = 404, "未找到该租户的 Skill 候选"
        except PermissionError:
            error_status, error_message = 403, "Skill 候选的租户或 Mission 来源不匹配"
        except ValueError as exc:
            error_status, error_message = 409, f"Skill 候选不符合 Replay 契约: {str(exc)[:180]}"
        except Exception as exc:
            outcome_indeterminate = True
            candidate_evidence_ref = getattr(exc, "evidence_ref", None)
            if isinstance(candidate_evidence_ref, dict):
                partial_evidence_ref = dict(candidate_evidence_ref)
            error_status, error_message = 502, f"Broker Skill Replay 未完成: {type(exc).__name__}"
        else:
            replay = operation.get("replay", {}) if isinstance(operation, dict) else {}
            result = replay.get("result", {}) if isinstance(replay, dict) else {}
            evidence = replay.get("evidence", {}) if isinstance(replay, dict) else {}
            experience = replay.get("experience", {}) if isinstance(replay, dict) else {}
            validation = operation.get("validation", {}) if isinstance(operation, dict) else {}
            promotion = operation.get("promotion", {}) if isinstance(operation, dict) else {}
            if promotion.get("status") == "published":
                completion_detail = "Broker 执行证明有效；独立 Validator 验收通过；Artifact Store 已发布不可变 Skill"
                completion_message = "Skill Replay、独立验收与 Artifact Store 发布均已完成"
            elif validation.get("status") == "rejected":
                completion_detail = "Broker Replay 已记录；独立 Validator 未通过或不可用，Skill 未晋升"
                completion_message = "Replay 已记录，但独立验收未通过，未发布 Skill Artifact"
            elif validation.get("status") == "passed":
                completion_detail = "Broker Replay 与独立 Validator 验收已通过；Artifact Store 发布未完成"
                completion_message = "独立验收已通过，但 Artifact Store 发布未完成"
            elif validation.get("status") == "not_configured":
                completion_detail = "Broker Replay 已记录；Validator 尚未配置，Skill 保持 Draft，未发布 Artifact"
                completion_message = "Replay 已记录；Validator 未配置，Skill 保持 Draft"
            else:
                completion_detail = "Broker Replay 已记录；执行失败，未进行独立验收或 Skill 晋升"
                completion_message = "Replay 已记录，但执行未成功，未进行 Skill 晋升"
            with exclusive_mission_claim_lock(workspace):
                state = load_mission_runs_strict(workspace)
                latest = next((
                    item for item in state["items"]
                    if isinstance(item, dict)
                    and str(item.get("mission_run_id") or "") == mission_run_id
                ), None)
                if not isinstance(latest, dict):
                    return error_response("Replay 已执行并保存证据，但 Mission 记录暂时不可更新", 503)
                latest_actions = latest.get("actions") if isinstance(latest.get("actions"), list) else []
                recorded = next((
                    item for item in latest_actions
                    if isinstance(item, dict) and item.get("task_id") == task_id
                ), None)
                if not isinstance(recorded, dict):
                    return error_response("Replay 已执行并保存证据，但操作记录未找到", 503)
                recorded.update({
                    "status": "completed",
                    "detail": completion_detail,
                    "execution_succeeded": result.get("execution_succeeded") is True,
                    "validation_status": validation.get("status"),
                    "validation_id": validation.get("validation_id"),
                    "validator_id": validation.get("validator_id"),
                    "validation_policy_id": validation.get("policy_id"),
                    "validation_error_type": validation.get("error_type"),
                    "promotion_status": promotion.get("status"),
                    "promotion_error_type": promotion.get("error_type"),
                    "published_artifact": promotion.get("artifact") if promotion.get("status") == "published" else None,
                    "evidence_id": evidence.get("evidence_id"),
                    "experience_id": experience.get("id"),
                    "replay_result": result,
                    "skill_replay_output": replay.get("skill_replay_output"),
                    "stage_receipt": operation.get("stage_receipt"),
                    "operation_result": operation,
                    "completion_message": completion_message,
                    "completed_at": datetime.now().astimezone().isoformat(),
                })
                latest["actions"] = latest_actions
                latest["updated_at"] = datetime.now().astimezone().isoformat()
                save_mission_runs(workspace, state)
            return success_response(operation, completion_message)

        # Once the runtime has been entered, an unclassified exception may
        # follow a Broker side effect whose response was lost. Keep the node
        # blocked for review; a new HTTP idempotency key must not create a new
        # Broker task and accidentally execute the Skill twice.
        try:
            with exclusive_mission_claim_lock(workspace):
                state = load_mission_runs_strict(workspace)
                latest = next((
                    item for item in state["items"]
                    if isinstance(item, dict)
                    and str(item.get("mission_run_id") or "") == mission_run_id
                ), None)
                if isinstance(latest, dict):
                    latest_actions = latest.get("actions") if isinstance(latest.get("actions"), list) else []
                    recorded = next((
                        item for item in latest_actions
                        if isinstance(item, dict) and item.get("task_id") == task_id
                    ), None)
                    if isinstance(recorded, dict):
                        recorded.update({
                            "status": "interrupted" if outcome_indeterminate else "failed",
                            "detail": error_message,
                            "error_type": (
                                "skill_replay_outcome_indeterminate"
                                if outcome_indeterminate
                                else "skill_replay_rejected_or_unavailable"
                            ),
                            "error_status": error_status,
                            "error_message": error_message,
                        })
                        if outcome_indeterminate:
                            recorded.update({
                                "recovery_status": "needs_review",
                                "recovery_reason": "skill_replay_outcome_indeterminate",
                                "interrupted_at": datetime.now().astimezone().isoformat(),
                            })
                        else:
                            recorded["completed_at"] = datetime.now().astimezone().isoformat()
                        if isinstance(partial_evidence_ref, dict):
                            recorded["evidence_ref"] = partial_evidence_ref
                            recorded["evidence_id"] = partial_evidence_ref.get("evidence_id")
                        latest["actions"] = latest_actions
                        latest["updated_at"] = datetime.now().astimezone().isoformat()
                        save_mission_runs(workspace, state)
        except Exception:
            pass
        return error_response(error_message, error_status)

    @app.get("/api/missions/skill-replays/recovery-review")
    async def list_skill_replay_recovery_review(request: Request, tenant_id: str | None = None, limit: int = 100):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        if not tenant_id or not str(tenant_id).strip():
            return error_response("必须指定 tenant_id", 400)
        if not authorize_tenant(user, tenant_id):
            return error_response("无权访问该租户", 403)
        if tenant_role(user, tenant_id) != "tenant_admin":
            return error_response("仅租户管理员可以查看 Skill Replay 复核队列", 403)

        try:
            state = load_mission_runs_strict(workspace)
        except (OSError, UnicodeError, ValueError) as exc:
            return error_response(f"Skill Replay 复核数据读取失败: {type(exc).__name__}", 500)

        reviews = []
        for mission_run in state["items"]:
            if not isinstance(mission_run, dict) or mission_run.get("tenant_id") != tenant_id:
                continue
            actions = mission_run.get("actions") if isinstance(mission_run.get("actions"), list) else []
            for action in actions:
                if (
                    not isinstance(action, dict)
                    or action.get("action_type") != "skill_replay"
                    or action.get("status") != "interrupted"
                    or action.get("recovery_status") != "needs_review"
                ):
                    continue
                mission_run_id = str(mission_run.get("mission_run_id") or "")
                node_id = str(action.get("node_id") or "")
                task_id = str(action.get("task_id") or "")
                binding = action.get("skill_binding")
                binding_status = "missing"
                safe_binding = None
                stage_request_id = None
                execution_request_id = None
                if isinstance(binding, dict):
                    context = binding.get("mission_context")
                    digest = binding.get("content_sha256")
                    if (
                        binding.get("schema_version") == "mission.skill-replay-binding.v1"
                        and binding.get("skill_id") == action.get("skill_id")
                        and isinstance(binding.get("skill_version"), str)
                        and binding.get("trust_level") == "draft"
                        and isinstance(digest, str)
                        and re.fullmatch(r"[0-9a-f]{64}", digest)
                        and context == {
                            "tenant_id": tenant_id,
                            "mission_run_id": mission_run_id,
                            "node_id": node_id,
                            "task_id": task_id,
                        }
                        and isinstance(action.get("stage_request_id"), str)
                        and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", action["stage_request_id"])
                        and isinstance(action.get("execution_request_id"), str)
                        and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", action["execution_request_id"])
                    ):
                        binding_status = "pinned"
                        safe_binding = {
                            "skill_id": binding["skill_id"],
                            "skill_version": binding["skill_version"],
                            "content_sha256": digest,
                            "trust_level": binding["trust_level"],
                        }
                        stage_request_id = action["stage_request_id"]
                        execution_request_id = action["execution_request_id"]
                    else:
                        binding_status = "invalid"

                evidence_ref = action.get("evidence_ref")
                safe_evidence_ref = None
                if isinstance(evidence_ref, dict):
                    safe_evidence_ref = {
                        key: evidence_ref.get(key)
                        for key in ("evidence_id", "sha256", "relative_path")
                        if isinstance(evidence_ref.get(key), str)
                    }
                reviews.append({
                    "mission_run_id": mission_run_id,
                    "tenant_id": tenant_id,
                    "goal": mission_run.get("goal"),
                    "node_id": node_id,
                    "task_id": task_id,
                    "skill_id": action.get("skill_id"),
                    "title": action.get("title"),
                    "idempotency_key": action.get("idempotency_key"),
                    "recovery_status": action.get("recovery_status"),
                    "recovery_reason": action.get("recovery_reason"),
                    "interrupted_at": action.get("interrupted_at"),
                    "candidate_binding_status": binding_status,
                    "skill_binding": safe_binding,
                    "stage_request_id": stage_request_id,
                    "execution_request_id": execution_request_id,
                    "evidence_ref": safe_evidence_ref,
                })
                if len(reviews) >= max(1, min(limit, 500)):
                    return success_response({
                        "count": len(reviews),
                        "items": reviews,
                    }, "待人工复核的 Skill Replay")
        return success_response({
            "count": len(reviews),
            "items": reviews,
        }, "待人工复核的 Skill Replay")


    @app.get("/api/missions/worker-claims/recovery-review")
    async def list_worker_claims_for_recovery_review(request: Request, tenant_id: str | None = None, limit: int = 100):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        if not tenant_id or not str(tenant_id).strip():
            return error_response("必须指定 tenant_id", 400)
        if not authorize_tenant(user, tenant_id):
            return error_response("无权访问该租户", 403)

        # Read persisted evidence directly: do not refresh missions or trigger dispatch here.
        # Corrupt/incomplete storage must not masquerade as an empty review queue.
        try:
            state = load_mission_runs_strict(workspace)
        except (OSError, UnicodeError, ValueError) as exc:
            return error_response(f"Mission 复核数据读取失败: {type(exc).__name__}", 500)
        items = state["items"]
        reviews = []
        for mission_run in items:
            if not isinstance(mission_run, dict):
                continue
            if tenant_id and mission_run.get("tenant_id") != tenant_id:
                continue
            actions = mission_run.get("actions", [])
            if not isinstance(actions, list):
                continue
            for action in actions:
                if not isinstance(action, dict):
                    continue
                claim = action.get("worker_claim")
                if not isinstance(claim, dict):
                    continue
                if claim.get("state") != "claimed" or claim.get("recovery_status") != "needs_review":
                    continue
                reviews.append({
                    "mission_run_id": mission_run.get("mission_run_id"),
                    "tenant_id": mission_run.get("tenant_id") or "default",
                    "goal": mission_run.get("goal"),
                    "node_id": action.get("node_id"),
                    "action_title": action.get("title"),
                    "task_id": action.get("task_id"),
                    "worker_claim": {
                        "claim_id": claim.get("claim_id"),
                        "worker_id": claim.get("worker_id"),
                        "state": claim.get("state"),
                        "recovery_status": claim.get("recovery_status"),
                        "recovery_reason": claim.get("recovery_reason"),
                        "recovery_checked_at": claim.get("recovery_checked_at"),
                        "release_error_type": claim.get("release_error_type"),
                    },
                })
                if len(reviews) >= max(1, min(limit, 500)):
                    return success_response({
                        "count": len(reviews),
                        "items": reviews,
                    }, "待人工复核的 Worker Claim")
        return success_response({
            "count": len(reviews),
            "items": reviews,
        }, "待人工复核的 Worker Claim")


    @app.post("/api/missions/worker-claims/{claim_id}/release")
    async def release_worker_claim(request: Request, claim_id: str):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        try:
            data = await request.json()
        except Exception:
            return error_response("请求 JSON 无效", 400)
        if not isinstance(data, dict):
            return error_response("请求内容必须是 JSON 对象", 400)
        tenant_id = str(data.get("tenant_id") or "").strip()
        mission_run_id = str(data.get("mission_run_id") or "").strip()
        reason = str(data.get("reason") or "").strip()
        if not tenant_id or not mission_run_id:
            return error_response("必须提供 tenant_id 和 mission_run_id", 400)
        if len(reason) < 10 or len(reason) > 500:
            return error_response("人工释放原因长度必须为 10 到 500 个字符", 400)
        if tenant_role(user, tenant_id) != "tenant_admin":
            return error_response("仅租户管理员可以释放 Worker Claim", 403)
        try:
            result = release_worker_claim_for_review(
                workspace=workspace,
                mission_run_id=mission_run_id,
                tenant_id=tenant_id,
                claim_id=claim_id,
                actor=user,
                reason=reason,
                task_queue=task_queue,
                organization_registry=organization_registry,
            )
        except PermissionError:
            return error_response("无权操作该租户的 Worker Claim", 403)
        except KeyError:
            return error_response("未找到对应的 Mission 或 Worker Claim", 404)
        except ValueError as exc:
            return error_response(f"Worker Claim 当前不满足释放条件: {str(exc)}", 409)
        except (OSError, RuntimeError):
            return error_response("Worker Claim 释放过程未能完成；请检查复核记录和审计日志", 503)
        except Exception:
            return error_response("Worker Claim 释放失败；占用状态已保留待复核", 503)
        return success_response(result, "Worker Claim 已人工释放")

    @app.get("/api/missions/{mission_run_id}")
    async def get_mission_run(mission_run_id: str):
        state = refresh_mission_runs(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            mission_starter=start_mission,
        )
        items = state.get("items", []) if isinstance(state, dict) else []
        current = next((
            item for item in items
            if isinstance(item, dict) and str(item.get("mission_run_id") or "") == str(mission_run_id or "")
        ), None)
        if not isinstance(current, dict):
            current = find_mission_run(workspace, mission_run_id)
        if not isinstance(current, dict):
            return error_response("未找到对应的 mission run", 404)
        return success_response(current)

    @app.post("/api/missions/execute")
    async def execute_mission(request: Request):
        data = await request.json()
        latest, error = start_mission(data if isinstance(data, dict) else {})
        if error:
            return error
        return success_response(latest, "Mission 已开始推进")

    @app.post("/api/missions/{mission_run_id}/continue")
    async def continue_mission(mission_run_id: str):
        state = refresh_mission_runs(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            mission_starter=start_mission,
        )
        items = state.get("items", []) if isinstance(state, dict) else []
        current = next((
            item for item in items
            if isinstance(item, dict) and str(item.get("mission_run_id") or "") == str(mission_run_id or "")
        ), None)
        if not isinstance(current, dict):
            current = find_mission_run(workspace, mission_run_id)
        if not isinstance(current, dict):
            return error_response("未找到对应的 mission run", 404)

        next_cycle_plan = (
            current.get("summary", {}).get("next_cycle_plan", {})
            if isinstance(current.get("summary"), dict)
            else {}
        )
        if str(next_cycle_plan.get("status") or "") != "ready":
            return error_response("当前 mission 尚未生成可继续推进的下一轮计划", 400)

        payload = {
            "tenant_id": current.get("tenant_id") or "default",
            "work_type_id": (
                current.get("work_type", {}).get("work_type_id")
                if isinstance(current.get("work_type"), dict)
                else None
            ),
            "mission_kind": current.get("mission_kind"),
            "goal": derive_follow_up_goal(current),
            "context": derive_follow_up_context(current),
        }
        latest, error = start_mission(payload)
        if error:
            return error
        return success_response({
            "source_mission_run_id": mission_run_id,
            "continued_mission_run": latest,
        }, "已基于上一轮结果启动下一轮 Mission")
