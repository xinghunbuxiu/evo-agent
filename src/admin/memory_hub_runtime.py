"""
成员级记忆检索与决策中枢。

V1 目标：
- 统一成员的身份、经验、技能、关系、企业仓、历史档案检索
- 给出当前主方案、备选方案、升级原因与写回目标
- 保留最近决策快照，方便复盘与 UI 展示
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from core import ExperienceStore
from admin.worker_route_runtime import member_uses_operation_automation, resolve_experience_domain


def create_memory_hub_runtime_bindings(
    *,
    build_historical_learning_tasks: Callable[[Path, str, object], list[dict]],
    list_platform_strategy_promotions: Callable[[Path, int], list[dict]],
):
    def _trim(value: object | None, limit: int = 160, fallback: str = "") -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        compact = " ".join(text.split())
        return compact[:limit]

    def _normalize_list(value: object | None) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _member_domain(primary_role: str, work_type_id: str | None = None) -> str:
        return resolve_experience_domain(None, primary_role=primary_role, work_type_id=work_type_id or primary_role)

    def _source_priority(tenant_manager, tenant_id: str) -> list[str]:
        policy = tenant_manager.get_external_learning_policy(tenant_id)
        values = policy.get("source_priority", []) if isinstance(policy, dict) else []
        normalized = [str(item).strip() for item in values if str(item).strip()]
        return normalized or ["local_memory", "platform_shared", "enterprise_repo", "official_docs", "web_search", "ai_assist"]

    def _allow_ai_assist(tenant_manager, tenant_id: str) -> bool:
        policy = tenant_manager.get_external_learning_policy(tenant_id)
        return bool(policy.get("allow_ai_assist", True)) if isinstance(policy, dict) else True

    def _string_match_score(query_terms: list[str], candidate_text: str) -> tuple[float, list[str]]:
        normalized_candidate = candidate_text.lower()
        matches: list[str] = []
        score = 0.0
        for term in query_terms:
            normalized_term = str(term or "").strip().lower()
            if len(normalized_term) < 2:
                continue
            if normalized_term in normalized_candidate or normalized_candidate in normalized_term:
                matches.append(term)
                score += 1.0 if len(normalized_term) >= 4 else 0.5
        return min(score / max(len(query_terms), 1), 1.0), matches

    def _enterprise_repo_entries(workspace: Path, tenant_id: str) -> list[dict]:
        path = workspace / ".tenants" / tenant_id / "data" / "enterprise_repo_index.json"
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        repos = payload.get("repos", {}) if isinstance(payload, dict) else {}
        entries: list[dict] = []
        for repo_key, repo_data in (repos.items() if isinstance(repos, dict) else []):
            if not isinstance(repo_data, dict):
                continue
            for item in (repo_data.get("entries") if isinstance(repo_data.get("entries"), list) else []):
                if not isinstance(item, dict):
                    continue
                entries.append({
                    "repo_key": repo_key,
                    "title": _trim(item.get("title") or item.get("name"), 120),
                    "summary": _trim(item.get("summary") or item.get("description"), 180),
                    "keywords": _normalize_list(item.get("keywords")),
                    "path": _trim(item.get("path"), 200),
                    "type": _trim(item.get("type"), 60),
                })
        return entries

    def _load_local_skill_entries(workspace: Path, tenant_id: str) -> list[dict]:
        roots = [
            workspace / ".tenants" / tenant_id / "skills" / "verified",
            workspace / ".tenants" / tenant_id / "skills" / "draft",
            workspace / ".tenants" / tenant_id / ".skill_cache" / "verified",
            workspace / ".tenants" / tenant_id / ".skill_cache" / "drafts",
        ]
        items: list[dict] = []
        seen_ids: set[str] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for file_path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
                try:
                    payload = json.loads(file_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                skill_id = str(payload.get("id") or file_path.stem).strip()
                if not skill_id or skill_id in seen_ids:
                    continue
                seen_ids.add(skill_id)
                items.append({
                    "skill_id": skill_id,
                    "name": _trim(payload.get("name"), 120, skill_id),
                    "description": _trim(payload.get("description"), 200),
                    "domain": _trim(payload.get("domain"), 60),
                    "trust_level": _trim(payload.get("trust_level"), 40, "draft"),
                    "success_rate": float(payload.get("success_rate") or 0.0),
                    "usage_count": int(payload.get("usage_count") or 0),
                })
        return items

    def _current_task(runtime: dict, member_id: str) -> dict | None:
        task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        scoped = [
            item for item in items
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
        ]
        scoped.sort(key=lambda item: str(item.get("assigned_at") or ""), reverse=True)
        for item in scoped:
            if str(item.get("status") or "").strip() != "approved":
                return item
        return scoped[0] if scoped else None

    def _current_recommendation(runtime: dict, member_id: str) -> dict | None:
        task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("recommendations") if isinstance(task_center.get("recommendations"), list) else []
        scoped = [
            item for item in items
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
        ]
        scoped.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        for item in scoped:
            if str(item.get("status") or "").strip() == "suggested":
                return item
        return scoped[0] if scoped else None

    def build_member_memory_hub(
        *,
        workspace: Path,
        tenant_manager,
        task_queue,
        tenant_id: str,
        runtime: dict,
        member: dict,
        trigger: str = "status_refresh",
    ) -> dict:
        member_id = str(member.get("member_id") or "").strip()
        primary_role = str(member.get("primary_role") or "").strip() or "autonomous_child_agent"
        task = _current_task(runtime, member_id) or {}
        recommendation = _current_recommendation(runtime, member_id) or {}
        active_job = (member.get("current_jobs") or [None])[0] if isinstance(member.get("current_jobs"), list) and member.get("current_jobs") else {}
        active_job = active_job if isinstance(active_job, dict) else {}
        existing_hub = member.get("memory_hub", {}) if isinstance(member.get("memory_hub"), dict) else {}
        case_suffix = str(task.get("task_id") or recommendation.get("recommendation_id") or active_job.get("job_id") or primary_role or member_id).strip() or member_id
        active_case_id = f"memory-hub:{tenant_id}:{member_id}:{case_suffix}"

        current_focus = _trim(
            member.get("growth_state", {}).get("current_focus")
            if isinstance(member.get("growth_state"), dict)
            else None,
            120,
        )
        next_action = _trim(
            member.get("training_plan", {}).get("next_action")
            if isinstance(member.get("training_plan"), dict)
            else None,
            160,
        )
        task_context = {
            "task_id": _trim(task.get("task_id"), 80) or None,
            "task_title": _trim(task.get("title"), 120) or None,
            "task_objective": _trim(task.get("objective"), 220) or None,
            "task_status": _trim(task.get("status"), 40) or None,
            "recommendation_id": _trim(recommendation.get("recommendation_id"), 80) or None,
            "recommendation_title": _trim(recommendation.get("title"), 120) or None,
            "job_id": _trim(active_job.get("job_id"), 80) or None,
            "job_title": _trim(active_job.get("title"), 120) or None,
            "account_id": _trim(active_job.get("account_id"), 80) or None,
            "current_focus": current_focus or None,
        }
        decision_intent = _trim(
            task.get("objective")
            or recommendation.get("objective")
            or active_job.get("target_outcome")
            or current_focus
            or next_action,
            240,
            f"围绕 {member.get('name') or member_id} 当前岗位目标做一轮检索与决策",
        )
        query_terms = [
            _trim(task.get("title"), 80),
            _trim(task.get("objective"), 120),
            _trim(recommendation.get("title"), 80),
            _trim(recommendation.get("objective"), 120),
            _trim(active_job.get("title"), 80),
            _trim(active_job.get("target_outcome"), 120),
            current_focus,
            _trim(member.get("persona", {}).get("role_label") if isinstance(member.get("persona"), dict) else None, 80),
            primary_role,
        ]
        query_terms = [item for item in query_terms if item]

        retrieval_hits: list[dict] = []
        retrieval_plan: list[dict] = []

        identity_text = " ".join([
            _trim(member.get("identity", {}).get("self_description") if isinstance(member.get("identity"), dict) else None, 200),
            _trim(member.get("role_memory", {}).get("long_term_goal") if isinstance(member.get("role_memory"), dict) else None, 160),
            " ".join(_normalize_list((member.get("role_memory") or {}).get("preferred_domains"))),
        ])
        identity_score, identity_matches = _string_match_score(query_terms, identity_text)
        retrieval_plan.append({
            "source": "identity_memory",
            "status": "completed" if identity_text else "no_match",
            "query": decision_intent,
            "confidence": round(identity_score, 3),
            "reason": "先确认这个员工是谁、长期目标是什么、当前岗位是什么。",
        })
        if identity_text:
            retrieval_hits.append({
                "source": "identity_memory",
                "status": "matched",
                "query": decision_intent,
                "hits": 1,
                "best_match_summary": _trim(identity_text, 180),
                "confidence": round(max(identity_score, 0.52), 3),
                "evidence": identity_matches or [primary_role],
                "recommended_action": "保持决策不要偏离当前岗位身份与长期目标。",
            })

        journal_cards = (member.get("experience_journal", {}).get("cards") if isinstance(member.get("experience_journal"), dict) else []) or []
        best_journal = None
        best_journal_score = 0.0
        best_journal_matches: list[str] = []
        for card in journal_cards[:8]:
            if not isinstance(card, dict):
                continue
            card_text = " ".join([
                _trim(card.get("title"), 120),
                _trim(card.get("summary"), 200),
                _trim(card.get("current_pattern"), 160),
                _trim(card.get("next_experiment"), 120),
            ])
            score, matches = _string_match_score(query_terms, card_text)
            if score >= best_journal_score:
                best_journal = card
                best_journal_score = score
                best_journal_matches = matches
        retrieval_plan.append({
            "source": "experience_journal",
            "status": "completed" if journal_cards else "no_match",
            "query": decision_intent,
            "confidence": round(best_journal_score, 3),
            "reason": "优先复用这个员工自己已经沉淀过的岗位经验卡。",
        })
        if best_journal:
            retrieval_hits.append({
                "source": "experience_journal",
                "status": "matched",
                "query": decision_intent,
                "hits": len(journal_cards[:8]),
                "best_match_summary": _trim(best_journal.get("summary") or best_journal.get("title"), 180, "找到岗位经验卡"),
                "confidence": round(max(best_journal_score, 0.58), 3),
                "evidence": best_journal_matches or _normalize_list(best_journal.get("evidence"))[:3] or [str(best_journal.get("card_id") or "journal_card")],
                "recommended_action": _trim(best_journal.get("next_experiment"), 160, "先按最近有效经验推进一轮最小动作。"),
            })

        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        thread = next(
            (
                item for item in (relationship_center.get("conversation_threads") if isinstance(relationship_center.get("conversation_threads"), list) else [])
                if isinstance(item, dict) and str(item.get("thread_id") or "") == f"trainer:{member_id}"
            ),
            None,
        )
        latest_messages = (thread.get("messages") if isinstance(thread, dict) and isinstance(thread.get("messages"), list) else [])[-3:]
        relationship_text = " ".join(_trim(item.get("content"), 160) for item in latest_messages if isinstance(item, dict))
        relationship_score, relationship_matches = _string_match_score(query_terms, relationship_text)
        retrieval_plan.append({
            "source": "relationship_context",
            "status": "completed" if latest_messages else "no_match",
            "query": decision_intent,
            "confidence": round(relationship_score, 3),
            "reason": "查看最近带教与沟通，避免脱离当前上下文。",
        })
        if latest_messages:
            retrieval_hits.append({
                "source": "relationship_context",
                "status": "matched",
                "query": decision_intent,
                "hits": len(latest_messages),
                "best_match_summary": _trim(relationship_text, 180, "最近存在带教上下文"),
                "confidence": round(max(relationship_score, 0.42), 3),
                "evidence": relationship_matches or [_trim(latest_messages[-1].get("sender_role"), 40, "trainer_context")],
                "recommended_action": "确保这轮执行与最近沟通保持一致，不重复走偏。",
            })

        local_skill_entries = _load_local_skill_entries(workspace, tenant_id)
        matched_skills: list[dict] = []
        for item in local_skill_entries:
            candidate_text = " ".join([item["name"], item["description"], item["domain"], item["trust_level"]])
            score, matches = _string_match_score(query_terms + [primary_role], candidate_text)
            if score > 0:
                matched_skills.append({
                    **item,
                    "match_score": score,
                    "matches": matches,
                })
        matched_skills.sort(key=lambda item: (item["match_score"], item["success_rate"], item["usage_count"]), reverse=True)
        retrieval_plan.append({
            "source": "local_skills",
            "status": "completed" if local_skill_entries else "no_match",
            "query": decision_intent,
            "confidence": round(float(matched_skills[0]["match_score"]) if matched_skills else 0.0, 3),
            "reason": "检查本地已验证技能，优先复用稳定方法。",
        })
        if matched_skills:
            best_skill = matched_skills[0]
            retrieval_hits.append({
                "source": "local_skills",
                "status": "matched",
                "query": decision_intent,
                "hits": len(matched_skills[:5]),
                "best_match_summary": _trim(f"{best_skill['name']} / {best_skill['description']}", 180),
                "confidence": round(max(float(best_skill["match_score"]), 0.62), 3),
                "evidence": best_skill.get("matches") or [best_skill["trust_level"], f"success_rate={best_skill['success_rate']:.2f}"],
                "recommended_action": "优先按本地已沉淀技能执行，减少重新试错。",
            })

        enterprise_entries = _enterprise_repo_entries(workspace, tenant_id)
        matched_repo_entries: list[dict] = []
        for item in enterprise_entries:
            candidate_text = " ".join([item["title"], item["summary"], " ".join(item["keywords"]), item["type"]])
            score, matches = _string_match_score(query_terms + [primary_role], candidate_text)
            if score > 0:
                matched_repo_entries.append({
                    **item,
                    "match_score": score,
                    "matches": matches,
                })
        matched_repo_entries.sort(key=lambda item: item["match_score"], reverse=True)
        retrieval_plan.append({
            "source": "enterprise_repo",
            "status": "completed" if enterprise_entries else "no_match",
            "query": decision_intent,
            "confidence": round(float(matched_repo_entries[0]["match_score"]) if matched_repo_entries else 0.0, 3),
            "reason": "检查企业/Gitee 经验仓，看有没有现成案例或索引。",
        })
        if matched_repo_entries:
            best_repo = matched_repo_entries[0]
            retrieval_hits.append({
                "source": "enterprise_repo",
                "status": "matched",
                "query": decision_intent,
                "hits": len(matched_repo_entries[:5]),
                "best_match_summary": _trim(f"{best_repo['title']} / {best_repo['summary']}", 180),
                "confidence": round(max(float(best_repo["match_score"]), 0.55), 3),
                "evidence": best_repo.get("matches") or [best_repo["repo_key"], best_repo["path"]],
                "recommended_action": "先复用企业仓已有案例或结构，再做最小改造。",
            })

        historical_items = build_historical_learning_tasks(workspace, tenant_id, task_queue) or []
        matched_historical: list[dict] = []
        for item in historical_items:
            if not isinstance(item, dict):
                continue
            candidate_text = " ".join([
                _trim(item.get("title"), 120),
                _trim(item.get("goal"), 160),
                " ".join(_trim(candidate.get("summary"), 140) for candidate in (item.get("candidate_approaches") if isinstance(item.get("candidate_approaches"), list) else [])[:2] if isinstance(candidate, dict)),
            ])
            score, matches = _string_match_score(query_terms + [primary_role], candidate_text)
            if score > 0:
                matched_historical.append({
                    "task_id": item.get("task_id"),
                    "title": _trim(item.get("title"), 120),
                    "summary": _trim(item.get("goal"), 180),
                    "match_score": score,
                    "matches": matches,
                    "next_validation_action": _trim(item.get("next_validation_action"), 160),
                })
        matched_historical.sort(key=lambda item: item["match_score"], reverse=True)
        retrieval_plan.append({
            "source": "historical_archive",
            "status": "completed" if historical_items else "no_match",
            "query": decision_intent,
            "confidence": round(float(matched_historical[0]["match_score"]) if matched_historical else 0.0, 3),
            "reason": "查看历史观察/验证档案，避免重复踩坑。",
        })
        if matched_historical:
            best_historical = matched_historical[0]
            retrieval_hits.append({
                "source": "historical_archive",
                "status": "matched",
                "query": decision_intent,
                "hits": len(matched_historical[:5]),
                "best_match_summary": _trim(f"{best_historical['title']} / {best_historical['summary']}", 180),
                "confidence": round(max(float(best_historical["match_score"]), 0.48), 3),
                "evidence": best_historical.get("matches") or [best_historical["task_id"]],
                "recommended_action": best_historical.get("next_validation_action") or "优先参考历史验证步骤，而不是从零开始。",
            })

        promotions = list_platform_strategy_promotions(workspace, limit=12)
        matched_promotions: list[dict] = []
        for item in promotions:
            if not isinstance(item, dict):
                continue
            candidate_text = " ".join([
                _trim(item.get("title"), 120),
                _trim(item.get("summary"), 180),
                _trim(item.get("strategy_id"), 120),
            ])
            score, matches = _string_match_score(query_terms + [primary_role], candidate_text)
            if score > 0:
                matched_promotions.append({
                    "id": item.get("id"),
                    "title": _trim(item.get("title"), 120),
                    "summary": _trim(item.get("summary"), 180),
                    "match_score": score,
                    "matches": matches,
                    "decision": _trim(item.get("decision"), 40),
                })
        matched_promotions.sort(key=lambda item: item["match_score"], reverse=True)
        retrieval_plan.append({
            "source": "platform_shared",
            "status": "completed" if promotions else "no_match",
            "query": decision_intent,
            "confidence": round(float(matched_promotions[0]["match_score"]) if matched_promotions else 0.0, 3),
            "reason": "查看平台共享层，看看其他租户是否已有已验证做法。",
        })
        if matched_promotions:
            best_promotion = matched_promotions[0]
            retrieval_hits.append({
                "source": "platform_shared",
                "status": "matched",
                "query": decision_intent,
                "hits": len(matched_promotions[:5]),
                "best_match_summary": _trim(f"{best_promotion['title']} / {best_promotion['summary']}", 180),
                "confidence": round(max(float(best_promotion["match_score"]), 0.44), 3),
                "evidence": best_promotion.get("matches") or [best_promotion.get("decision") or "platform_shared"],
                "recommended_action": "如果本地经验不足，可参考共享层已验证做法作为对照方案。",
            })

        priority_sources = _source_priority(tenant_manager, tenant_id)
        for source in ["official_docs", "web_search", "ai_assist"]:
            if source not in priority_sources:
                priority_sources.append(source)
        local_strength = max(
            [item.get("confidence", 0.0) for item in retrieval_hits if item.get("source") in {"experience_journal", "local_skills", "enterprise_repo", "historical_archive"}],
            default=0.0,
        )
        blocked_reason = _trim(
            member.get("derived_state", {}).get("blocked_reason")
            if isinstance(member.get("derived_state"), dict)
            else None,
            180,
        )
        needs_external = local_strength < 0.66 or bool(blocked_reason)
        escalation_reason = None
        if blocked_reason:
            escalation_reason = f"当前存在卡点：{blocked_reason}"
        elif needs_external:
            escalation_reason = "本地经验与技能命中不足，需要准备升级到外部学习层。"

        for source in ["official_docs", "web_search", "ai_assist"]:
            if source == "ai_assist" and not _allow_ai_assist(tenant_manager, tenant_id):
                retrieval_plan.append({
                    "source": source,
                    "status": "disabled",
                    "query": decision_intent,
                    "confidence": 0.0,
                    "reason": "当前公司策略禁止 AI 辅助。",
                })
                continue
            retrieval_plan.append({
                "source": source,
                "status": "queued" if needs_external and source in priority_sources else "standby",
                "query": decision_intent,
                "confidence": 0.0,
                "reason": "只有本地不足或发生冲突时，才升级到外部学习来源。",
            })

        primary_hit = max(retrieval_hits, key=lambda item: float(item.get("confidence", 0.0)), default=None)
        used_sources = [item["source"] for item in retrieval_hits if float(item.get("confidence", 0.0)) >= 0.45]
        if not used_sources and primary_hit:
            used_sources = [primary_hit["source"]]
        primary_plan = _trim(
            primary_hit.get("recommended_action") if isinstance(primary_hit, dict) else None,
            180,
            "先围绕当前任务做一轮最小可验证动作，并保留复盘证据。",
        )
        fallback_plan = _trim(
            best_journal.get("next_experiment") if isinstance(best_journal, dict) else None,
            160,
            "如果当前方案不稳，就退回最近一条可验证经验，再补样本。",
        )
        if needs_external:
            fallback_plan = "如果本地经验不足或再次受阻，就按来源优先级升级到企业仓、官方资料、联网搜索和 AI 辅助。"
        verification_goal = _trim(
            task.get("objective")
            or active_job.get("target_outcome")
            or recommendation.get("objective"),
            180,
            "验证当前方案是否能形成稳定、可复用的岗位动作。",
        )
        expected_output = _trim(
            "；".join(_normalize_list(task.get("deliverables"))) or task.get("result_summary"),
            180,
            "形成一份可提交的结果摘要、复盘和下一轮建议。",
        )
        decision_confidence = round(min(max(local_strength or (primary_hit.get("confidence", 0.0) if isinstance(primary_hit, dict) else 0.42), 0.36), 0.94), 3)
        decision_summary = {
            "summary": _trim(
                primary_hit.get("best_match_summary") if isinstance(primary_hit, dict) else None,
                180,
                "当前还没有稳定命中的现成经验，先以最小实验推进。",
            ),
            "used_sources": used_sources,
            "primary_plan": primary_plan,
            "fallback_plan": fallback_plan,
            "stop_reason": blocked_reason or None,
            "escalation_reason": escalation_reason,
            "verification_goal": verification_goal,
            "expected_output": expected_output,
            "external_learning_required": needs_external,
        }
        writeback_targets = [
            "experience_journal",
            "relationship_center",
            "decision_history",
        ]
        if bool((member.get("operating_contract") or {}).get("must_record_experience", True)):
            writeback_targets.append("skills/draft")
        if member_uses_operation_automation(workspace, {"primary_role": primary_role, "current_jobs": [{"job_id": primary_role}]}):
            writeback_targets.append("enterprise_repo")

        decision_state = {
            "status": "blocked" if blocked_reason else ("needs_external_learning" if needs_external else "ready_to_execute"),
            "primary_plan": primary_plan,
            "fallback_plan": fallback_plan,
            "stop_reason": blocked_reason or None,
            "escalation_reason": escalation_reason,
            "verification_goal": verification_goal,
            "expected_output": expected_output,
        }
        retrieval_state = {
            "preferred_sources": priority_sources,
            "local_strength": decision_confidence,
            "needs_external_learning": needs_external,
            "retrieval_plan": retrieval_plan,
            "retrieval_hits": retrieval_hits,
        }
        snapshot = {
            "case_id": active_case_id,
            "member_id": member_id,
            "trigger": trigger,
            "decision_intent": decision_intent,
            "decision_state": copy.deepcopy(decision_state),
            "retrieval_state": copy.deepcopy(retrieval_state),
            "decision_summary": copy.deepcopy(decision_summary),
            "decision_confidence": decision_confidence,
            "created_at": datetime.now().isoformat(),
        }
        return {
            "active_case_id": active_case_id,
            "decision_intent": decision_intent,
            "task_context": task_context,
            "retrieval_plan": retrieval_plan,
            "retrieval_hits": retrieval_hits,
            "decision_summary": decision_summary,
            "decision_confidence": decision_confidence,
            "fallback_strategy": fallback_plan,
            "next_action": primary_plan,
            "writeback_targets": writeback_targets,
            "last_run_at": datetime.now().isoformat(),
            "last_trigger": trigger,
            "preferred_sources": priority_sources,
            "decision_state": decision_state,
            "retrieval_state": retrieval_state,
            "last_decision_snapshot": snapshot,
            "decision_history": existing_hub.get("decision_history", []) if isinstance(existing_hub.get("decision_history"), list) else [],
        }

    def sync_runtime_memory_hub(
        *,
        workspace: Path,
        tenant_manager,
        task_queue,
        tenant_id: str,
        runtime: dict,
        target_member_id: str | None = None,
        trigger: str = "manual_run",
        append_history: bool = False,
    ) -> dict:
        child_members = runtime.get("child_members", {}) if isinstance(runtime.get("child_members"), dict) else {}
        items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
        next_items: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            member_id = str(item.get("member_id") or "").strip()
            if target_member_id and member_id != target_member_id:
                next_items.append(item)
                continue
            hub = build_member_memory_hub(
                workspace=workspace,
                tenant_manager=tenant_manager,
                task_queue=task_queue,
                tenant_id=tenant_id,
                runtime=runtime,
                member=item,
                trigger=trigger,
            )
            history = hub.get("decision_history", []) if isinstance(hub.get("decision_history"), list) else []
            snapshot = hub.get("last_decision_snapshot") if isinstance(hub.get("last_decision_snapshot"), dict) else None
            if append_history and isinstance(snapshot, dict):
                next_history = [
                    snapshot,
                    *[
                        entry for entry in history
                        if isinstance(entry, dict) and str(entry.get("case_id") or "") != str(snapshot.get("case_id") or "")
                    ],
                ][:20]
            else:
                next_history = history[:20]
            next_items.append({
                **item,
                "memory_hub": {
                    **hub,
                    "decision_history": next_history,
                },
                "decision_state": hub.get("decision_state", {}),
                "retrieval_state": hub.get("retrieval_state", {}),
                "active_case_id": hub.get("active_case_id"),
                "last_decision_snapshot": hub.get("last_decision_snapshot"),
                "decision_history": next_history,
            })
        runtime["child_members"] = {
            "selected_member_id": child_members.get("selected_member_id"),
            "items": next_items,
        }
        return runtime

    return {
        "build_member_memory_hub": build_member_memory_hub,
        "sync_runtime_memory_hub": sync_runtime_memory_hub,
    }
