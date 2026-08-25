"""
外部学习运行时：
负责研究源选择、候选方案检索、本地 Codex 辅助与学习任务执行。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from core import ExperienceStore
from core.tenant import TenantManager


def create_external_learning_runtime_bindings(
    *,
    list_platform_strategy_promotions: Callable,
    load_review_queue: Callable,
    load_enterprise_repo_index: Callable,
    trim_candidate_text: Callable[[str | None, int], str],
    make_learning_task_id: Callable[[str, dict], str],
    build_diagnosis_signature: Callable[[dict], dict],
    build_review_item_signature: Callable[[dict], dict],
    score_signature_similarity: Callable[[dict, dict], tuple[float, list[str]]],
):
    def build_external_learning_plan(
        tenant_manager: TenantManager,
        tenant_id: str,
        diagnosis: dict,
    ) -> dict:
        policy = tenant_manager.get_external_learning_policy(tenant_id)
        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        reconstruct = diagnosis.get("reconstruct", {}) if isinstance(diagnosis, dict) else {}
        category = reconstruct.get("issue_category") or diagnosis.get("analyze", {}).get("issue_category")
        research_state = diagnosis.get("research_state")
        stable = bool(diagnosis.get("stable"))
        enterprise_repo_ready = bool(
            isinstance(git_knowledge, dict)
            and isinstance(git_knowledge.get("repos"), dict)
            and bool(git_knowledge.get("repos"))
        )

        needs_external_learning = not stable and category in {"capability_gap", "execution_error", "plugin_policy_gap"}
        if research_state in {"blocked", "discovering"}:
            needs_external_learning = True

        preferred_sources: list[str] = []
        for source in policy.get("source_priority", []):
            if source == "enterprise_repo" and not policy.get("allow_enterprise_sources", True):
                continue
            if source == "web_search" and not policy.get("allow_web_research", True):
                continue
            if source == "ai_assist" and not policy.get("allow_ai_assist", True):
                continue
            preferred_sources.append(source)

        if enterprise_repo_ready and policy.get("allow_enterprise_sources", True):
            preferred_sources = [source for source in preferred_sources if source != "enterprise_repo"]
            insert_at = 1 if preferred_sources and preferred_sources[0] == "local_memory" else 0
            preferred_sources.insert(insert_at, "enterprise_repo")

        queries: list[str] = []
        strategy_id = reconstruct.get("strategy_id")
        capability_id = reconstruct.get("capability_id")
        if category == "capability_gap":
            queries.append(f"Find missing capability approach for {diagnosis.get('bundle_path')} in javascript reverse workflow")
            if capability_id:
                queries.append(f"How to extend capability provider around {capability_id}")
        elif category == "execution_error":
            queries.append(f"Diagnose execution failure path for {strategy_id or capability_id or 'javascript reconstruct'}")
        elif category == "plugin_policy_gap":
            queries.append(f"Check plugin policy constraints for {strategy_id or capability_id or 'javascript pipeline'}")

        if enterprise_repo_ready:
            queries.append("Search tenant private git knowledge before expanding to shared/web sources")

        if policy.get("allow_ai_assist", True) and "ai_assist" in preferred_sources and "ai_assist" not in preferred_sources[:6]:
            preferred_sources.append("ai_assist")

        return {
            "needs_external_learning": needs_external_learning,
            "policy": policy,
            "preferred_sources": preferred_sources[:6],
            "validation_gate": (
                "外部学习得到的候选方案必须经过真实样本重放验证后，才能晋升为策略/技能"
                if policy.get("validation_required", True)
                else "允许先进入观察态，再补验证"
            ),
            "queries": queries[:3],
            "enterprise_repo_ready": enterprise_repo_ready,
        }

    def detect_local_codex() -> dict:
        command = shutil.which("codex")
        if not command:
            return {
                "available": False,
                "command": None,
                "reason": "codex_not_found",
            }
        return {
            "available": True,
            "command": command,
            "reason": "local_cli_available",
        }

    def build_codex_learning_prompt(
        tenant_id: str,
        diagnosis: dict,
        queries: list[str],
    ) -> str:
        reconstruct = diagnosis.get("reconstruct", {}) if isinstance(diagnosis, dict) else {}
        analyze = diagnosis.get("analyze", {}) if isinstance(diagnosis, dict) else {}
        lines = [
            "You are assisting Evo's autonomous learning loop.",
            "Return a short, practical research note for a JavaScript reverse-engineering problem.",
            f"tenant_id: {tenant_id}",
            f"bundle_path: {diagnosis.get('bundle_path') or '--'}",
            f"research_state: {diagnosis.get('research_state') or '--'}",
            f"analyze_issue: {analyze.get('issue_category') or '--'}",
            f"reconstruct_issue: {reconstruct.get('issue_category') or '--'}",
            "queries:",
        ]
        for query in queries[:3]:
            lines.append(f"- {query}")
        lines.extend([
            "Output sections:",
            "1. likely_root_cause",
            "2. candidate_fix",
            "3. validation_steps",
            "4. risk_notes",
            "Keep it concise and action-oriented.",
        ])
        return "\n".join(lines)

    def run_local_codex_learning(
        workspace: Path,
        tenant_id: str,
        diagnosis: dict,
        queries: list[str],
    ) -> dict:
        codex_info = detect_local_codex()
        if not codex_info.get("available"):
            return {
                "source": "ai_assist",
                "status": "unavailable",
                "candidate": None,
                "detail": codex_info.get("reason"),
            }

        prompt = build_codex_learning_prompt(tenant_id, diagnosis, queries)
        with tempfile.NamedTemporaryFile(prefix="evo_codex_", suffix=".txt", delete=False) as tmp:
            output_file = Path(tmp.name)

        try:
            completed = subprocess.run(
                [
                    str(codex_info["command"]),
                    "exec",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "read-only",
                    "--cd",
                    str(workspace),
                    "--output-last-message",
                    str(output_file),
                    prompt,
                ],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=45,
            )
            response_text = ""
            if output_file.is_file():
                response_text = output_file.read_text(encoding="utf-8", errors="ignore")
            if completed.returncode != 0:
                error_text = trim_candidate_text(completed.stderr or completed.stdout or "codex exec failed")
                return {
                    "source": "ai_assist",
                    "status": "error",
                    "candidate": None,
                    "detail": error_text,
                }

            summary = trim_candidate_text(response_text or completed.stdout or "codex returned empty response", 280)
            return {
                "source": "ai_assist",
                "status": "completed",
                "candidate": {
                    "source": "ai_assist",
                    "title": "Local Codex research note",
                    "summary": summary,
                    "confidence": 0.58,
                    "evidence": [
                        f"executor={codex_info.get('command')}",
                        "mode=local_codex_exec",
                    ],
                    "next_steps": [
                        "把 Codex 给出的候选修复点转成一次可回放实验",
                        "只在真实样本验证通过后再晋升为策略或经验",
                    ],
                    "metadata": {
                        "executor": codex_info.get("command"),
                    },
                },
                "detail": None,
            }
        except subprocess.TimeoutExpired:
            return {
                "source": "ai_assist",
                "status": "timeout",
                "candidate": None,
                "detail": "local codex exec timeout",
            }
        finally:
            output_file.unlink(missing_ok=True)

    def score_query_match(queries: list[str], haystacks: list[str]) -> float:
        query_terms: set[str] = set()
        for query in queries:
            for term in str(query).lower().replace("/", " ").replace("-", " ").split():
                if len(term) >= 3:
                    query_terms.add(term)
        if not query_terms:
            return 0.0

        haystack_terms: set[str] = set()
        for item in haystacks:
            for term in str(item).lower().replace("/", " ").replace("-", " ").split():
                if len(term) >= 3:
                    haystack_terms.add(term)
        if not haystack_terms:
            return 0.0
        matches = query_terms & haystack_terms
        return round(len(matches) / max(len(query_terms), 1), 3)

    def build_local_memory_candidates(
        workspace: Path,
        tenant_id: str,
        diagnosis: dict,
        queries: list[str],
        limit: int = 3,
    ) -> list[dict]:
        store = ExperienceStore(workspace, tenant_id)
        candidates: list[dict] = []
        experiences = [
            *store.load_by_domain("javascript", limit=20),
            *store.load_by_task("evolution", "growth_event", limit=12),
            *store.load_by_task("evolution", "replay_validation", limit=12),
        ]
        seen_ids: set[str] = set()

        for exp in experiences:
            if exp.id in seen_ids:
                continue
            seen_ids.add(exp.id)
            haystacks = [
                exp.domain,
                exp.task_type,
                exp.input_summary,
                exp.output_summary,
                json.dumps(exp.metadata, ensure_ascii=False),
            ]
            query_score = score_query_match(queries, haystacks)
            quality_score = round(min(max(float(exp.quality_score or 0.0), 0.0), 1.0), 3)
            total_score = round(min(1.0, 0.55 * quality_score + 0.45 * query_score), 3)
            if total_score <= 0:
                continue

            candidates.append({
                "source": "local_memory",
                "title": exp.id,
                "summary": trim_candidate_text(exp.output_summary or exp.input_summary),
                "confidence": total_score,
                "evidence": [
                    f"domain={exp.domain}",
                    f"task_type={exp.task_type}",
                    f"quality={quality_score:.2f}",
                ],
                "next_steps": [
                    "对照当前失败样本复核这条经验是否可迁移",
                    "若适配，则将关键规则转成新的策略实验输入",
                ],
                "metadata": {
                    "experience_id": exp.id,
                    "created_at": exp.created_at,
                },
            })

        candidates.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        return candidates[:limit]

    def build_platform_shared_candidates(
        workspace: Path,
        diagnosis: dict,
        queries: list[str],
        limit: int = 3,
    ) -> list[dict]:
        promotions = list_platform_strategy_promotions(workspace, limit=40)
        issue_category = (
            diagnosis.get("reconstruct", {}).get("issue_category")
            or diagnosis.get("analyze", {}).get("issue_category")
        )
        candidates: list[dict] = []

        for item in promotions:
            strategy_id = str(item.get("strategy_id") or "")
            haystacks = [
                strategy_id,
                item.get("title") or "",
                item.get("summary") or "",
                issue_category or "",
            ]
            query_score = score_query_match(queries, haystacks)
            confidence = 0.3 + min(query_score, 0.5)
            if strategy_id.startswith("builtin.javascript"):
                confidence += 0.2
            if item.get("decision") in {"accept", "auto_accept"}:
                confidence += 0.1

            candidates.append({
                "source": "platform_shared",
                "title": item.get("title") or strategy_id,
                "summary": trim_candidate_text(item.get("summary") or "平台共享层中的已验证策略候选"),
                "confidence": round(min(confidence, 1.0), 3),
                "evidence": [
                    f"strategy={strategy_id or '--'}",
                    f"decision={item.get('decision') or '--'}",
                    f"share_mode={item.get('share_mode') or '--'}",
                ],
                "next_steps": [
                    "把这条共享策略作为候选对照当前样本重放",
                    "若验证通过，再决定是否注入当前租户的策略覆盖层",
                ],
                "metadata": {
                    "strategy_id": strategy_id,
                    "promoted_at": item.get("promoted_at"),
                    "tenant_id": item.get("tenant_id"),
                    "path": item.get("path"),
                },
            })

        candidates.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        return candidates[:limit]

    def build_enterprise_repo_candidates(
        workspace: Path,
        tenant_manager: TenantManager,
        tenant_id: str,
        queries: list[str],
        limit: int = 3,
    ) -> list[dict]:
        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        repo_index = load_enterprise_repo_index(workspace, tenant_id)
        indexed_repos = repo_index.get("repos", {}) if isinstance(repo_index.get("repos"), dict) else {}
        candidates: list[dict] = []
        provider = str(git_knowledge.get("provider") or "git") if isinstance(git_knowledge, dict) else "git"
        namespace = str(git_knowledge.get("namespace") or "").strip() if isinstance(git_knowledge, dict) else ""

        for repo_key, repo in repos.items():
            if not isinstance(repo, dict):
                continue
            repo_name = str(repo.get("full_name") or repo.get("name") or repo_key)
            repo_url = str(repo.get("url") or "")
            repo_branch = str(repo.get("branch") or "main")
            repo_index_item = indexed_repos.get(repo_key, {}) if isinstance(indexed_repos.get(repo_key), dict) else {}
            indexed_entries = repo_index_item.get("entries", []) if isinstance(repo_index_item.get("entries"), list) else []
            indexed_keywords: list[str] = []
            for entry in indexed_entries[:12]:
                if not isinstance(entry, dict):
                    continue
                indexed_keywords.extend([str(item) for item in entry.get("keywords", []) if isinstance(item, str)])
                indexed_keywords.append(str(entry.get("title") or ""))
                indexed_keywords.append(str(entry.get("summary") or ""))
            query_score = score_query_match(queries, [repo_key, repo_name, repo_url])
            entry_match_score = score_query_match(queries, indexed_keywords)
            purpose_bonus = 0.1 if repo_key in {"skills", "experiences", "strategies"} else 0.04
            confidence = round(min(0.38 + query_score + entry_match_score + purpose_bonus, 0.92), 3)
            summary = (
                f"租户私有知识仓 {repo_name} 已就绪，索引到 {len(indexed_entries)} 条企业知识条目"
                if indexed_entries
                else f"租户私有知识仓 {repo_name} 已就绪，可优先作为企业侧技能/经验检索与沉淀入口"
            )
            candidates.append({
                "source": "enterprise_repo",
                "title": f"{provider}:{repo_key}",
                "summary": trim_candidate_text(summary),
                "confidence": confidence,
                "evidence": [
                    f"provider={provider}",
                    f"repo={repo_name}",
                    f"branch={repo_branch}",
                    f"url={repo_url or '--'}",
                    f"namespace={namespace or '--'}",
                    f"indexed_entries={len(indexed_entries)}",
                ],
                "next_steps": [
                    "优先到该私有仓补充企业技能、策略说明和经验快照",
                    "保持 repo index 最新，这样自治学习会优先命中企业私有知识条目",
                ],
                "metadata": {
                    "repo_key": repo_key,
                    "full_name": repo_name,
                    "url": repo_url,
                    "provider": provider,
                    "branch": repo_branch,
                    "namespace": namespace or None,
                    "index_path": repo_index_item.get("index_path"),
                    "indexed_entries": indexed_entries[:5],
                },
            })
            for entry in indexed_entries[:8]:
                if not isinstance(entry, dict):
                    continue
                entry_texts = [
                    str(entry.get("title") or ""),
                    str(entry.get("summary") or ""),
                    *[str(keyword) for keyword in entry.get("keywords", []) if isinstance(keyword, str)],
                    str(entry.get("path") or ""),
                    repo_key,
                ]
                entry_query_score = score_query_match(queries, entry_texts)
                if entry_query_score <= 0:
                    continue
                entry_confidence = round(min(0.46 + entry_query_score + purpose_bonus, 0.95), 3)
                candidates.append({
                    "source": "enterprise_repo",
                    "title": f"{provider}:{repo_key}:{entry.get('title') or 'entry'}",
                    "summary": trim_candidate_text(
                        entry.get("summary")
                        or f"{repo_name} 中的 {entry.get('type') or repo_key} 条目"
                    ),
                    "confidence": entry_confidence,
                    "evidence": [
                        f"provider={provider}",
                        f"repo={repo_name}",
                        f"entry_type={entry.get('type') or repo_key}",
                        f"entry_path={entry.get('path') or '--'}",
                        f"keywords={','.join([str(keyword) for keyword in entry.get('keywords', [])[:4]]) or '--'}",
                    ],
                    "next_steps": [
                        "优先阅读该条目的实现说明、经验总结或策略约束",
                        "命中后把验证结果再沉淀回企业仓，形成闭环索引",
                    ],
                    "metadata": {
                        "repo_key": repo_key,
                        "full_name": repo_name,
                        "url": repo_url,
                        "provider": provider,
                        "branch": repo_branch,
                        "namespace": namespace or None,
                        "index_path": repo_index_item.get("index_path"),
                        "entry": entry,
                    },
                })

        candidates.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        return candidates[:limit]

    def build_historical_archive_candidates(
        workspace: Path,
        tenant_id: str,
        diagnosis: dict,
        queries: list[str],
        limit: int = 3,
    ) -> list[dict]:
        items = load_review_queue(workspace, tenant_id)
        current_signature = build_diagnosis_signature(diagnosis)
        issue_category = (
            diagnosis.get("reconstruct", {}).get("issue_category")
            or diagnosis.get("analyze", {}).get("issue_category")
            or diagnosis.get("research_state")
        )
        candidates: list[dict] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            review_id = str(item.get("id") or "")
            strategy_id = str(item.get("strategy_id") or "")
            if not review_id:
                continue
            latest_run = item.get("experiment_runs", [{}])[0] if isinstance(item.get("experiment_runs"), list) and item.get("experiment_runs") else {}
            latest_summary = latest_run.get("summary", {}) if isinstance(latest_run, dict) else {}
            upgrade_candidate = item.get("upgrade_candidate", {}) if isinstance(item.get("upgrade_candidate"), dict) else {}
            platform_promotion = item.get("platform_promotion", {}) if isinstance(item.get("platform_promotion"), dict) else {}
            historical_signature = build_review_item_signature(item)
            signature_score, signature_reasons = score_signature_similarity(current_signature, historical_signature)
            draft_summary = (item.get("draft", {}) if isinstance(item.get("draft"), dict) else {}).get("summary")
            haystacks = [
                review_id,
                strategy_id,
                item.get("alert_reason") or "",
                item.get("notes") or "",
                draft_summary if isinstance(draft_summary, str) else "",
                upgrade_candidate.get("summary") or "",
                issue_category or "",
            ]
            query_score = score_query_match(queries, haystacks)
            confidence = 0.2 + min(query_score, 0.22) + min(signature_score, 0.5)
            if item.get("alert_reason") == issue_category:
                confidence += 0.18
            if latest_summary.get("status") == "improved":
                confidence += 0.18
            if upgrade_candidate.get("decision") in {"accept", "auto_accept"}:
                confidence += 0.1
            if platform_promotion.get("status") == "promoted":
                confidence += 0.08

            candidates.append({
                "source": "historical_archive",
                "title": upgrade_candidate.get("title") or strategy_id or review_id,
                "summary": trim_candidate_text(
                    upgrade_candidate.get("summary")
                    or item.get("notes")
                    or "历史复盘档案中的已验证候选方案"
                ),
                "confidence": round(min(confidence, 0.95), 3),
                "evidence": [
                    f"review_id={review_id}",
                    f"alert_reason={item.get('alert_reason') or '--'}",
                    f"experiment_status={latest_summary.get('status') or item.get('status') or '--'}",
                    f"signature_score={signature_score:.2f}",
                    *signature_reasons[:3],
                ],
                "next_steps": [
                    "优先拿这条历史档案对当前相似问题做自动验证",
                    "若新样本仍表现正向，再把结果沉淀成新的经验或策略提升",
                ],
                "metadata": {
                    "review_id": review_id,
                    "strategy_id": strategy_id,
                    "historical_status": item.get("status"),
                    "platform_promotion": platform_promotion.get("status"),
                    "signature": historical_signature,
                    "signature_score": signature_score,
                },
            })

        candidates.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        return candidates[:limit]

    def execute_learning_task(
        workspace: Path,
        tenant_manager: TenantManager,
        tenant_id: str,
        sample: dict,
        diagnosis: dict,
        learning_plan: dict,
    ) -> dict:
        preferred_sources = learning_plan.get("preferred_sources", []) if isinstance(learning_plan, dict) else []
        queries = learning_plan.get("queries", []) if isinstance(learning_plan, dict) else []
        source_runs: list[dict] = []
        candidate_approaches: list[dict] = []

        historical_candidates = build_historical_archive_candidates(
            workspace=workspace,
            tenant_id=tenant_id,
            diagnosis=diagnosis,
            queries=queries,
            limit=3,
        )
        if historical_candidates:
            source_runs.append({
                "source": "historical_archive",
                "status": "completed",
                "candidate_count": len(historical_candidates),
            })
            candidate_approaches.extend(historical_candidates)

        for source in preferred_sources:
            if source == "local_memory":
                candidates = build_local_memory_candidates(workspace, tenant_id, diagnosis, queries)
                source_runs.append({
                    "source": source,
                    "status": "completed" if candidates else "no_match",
                    "candidate_count": len(candidates),
                })
                candidate_approaches.extend(candidates)
                continue
            if source == "platform_shared":
                candidates = build_platform_shared_candidates(workspace, diagnosis, queries)
                source_runs.append({
                    "source": source,
                    "status": "completed" if candidates else "no_match",
                    "candidate_count": len(candidates),
                })
                candidate_approaches.extend(candidates)
                continue
            if source == "enterprise_repo":
                candidates = build_enterprise_repo_candidates(workspace, tenant_manager, tenant_id, queries)
                source_runs.append({
                    "source": source,
                    "status": "completed" if candidates else "no_match",
                    "candidate_count": len(candidates),
                })
                candidate_approaches.extend(candidates)
                continue
            if source == "ai_assist":
                ai_result = None
                try:
                    from admin.model_provider_runtime import run_configured_ai_assist

                    goal = str(
                        (diagnosis or {}).get("reconstruct", {}).get("issue_category")
                        or (diagnosis or {}).get("analyze", {}).get("issue_category")
                        or "补齐当前能力缺口"
                    )
                    ai_result = run_configured_ai_assist(
                        tenant_manager=tenant_manager,
                        tenant_id=tenant_id,
                        goal=goal,
                        queries=queries,
                        role_hint="学习研究员",
                    )
                except Exception:
                    ai_result = None
                if not isinstance(ai_result, dict) or ai_result.get("status") != "completed":
                    ai_result = run_local_codex_learning(
                        workspace=workspace,
                        tenant_id=tenant_id,
                        diagnosis=diagnosis,
                        queries=queries,
                    )
                source_runs.append({
                    "source": source,
                    "status": ai_result.get("status", "unknown"),
                    "candidate_count": 1 if isinstance(ai_result.get("candidate"), dict) else 0,
                    "detail": ai_result.get("detail"),
                })
                if isinstance(ai_result.get("candidate"), dict):
                    candidate_approaches.append(ai_result["candidate"])
                continue

            source_runs.append({
                "source": source,
                "status": "awaiting_connector",
                "candidate_count": 0,
            })

        deduped: list[dict] = []
        seen_keys: set[str] = set()
        for item in sorted(candidate_approaches, key=lambda entry: entry.get("confidence", 0.0), reverse=True):
            key = f"{item.get('source')}::{item.get('title')}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)

        status = "researching"
        if deduped:
            status = "ready_for_validation" if learning_plan.get("policy", {}).get("validation_required", True) else "candidate_found"
        elif any(item.get("status") == "awaiting_connector" for item in source_runs):
            status = "awaiting_connector"
        else:
            status = "no_match"

        return {
            "task_id": make_learning_task_id(tenant_id, sample),
            "tenant_id": tenant_id,
            "source_dir": sample.get("source_dir"),
            "bundle_path": sample.get("bundle_path"),
            "sample_signature": sample.get("sample_signature"),
            "issue_category": (
                diagnosis.get("reconstruct", {}).get("issue_category")
                or diagnosis.get("analyze", {}).get("issue_category")
            ),
            "queries": queries[:],
            "preferred_sources": preferred_sources[:],
            "validation_gate": learning_plan.get("validation_gate"),
            "status": status,
            "source_runs": source_runs,
            "candidate_approaches": deduped[:6],
            "next_validation_action": (
                "选择置信度最高的候选方案，对当前样本重放 analyze/reconstruct，只有通过验证后才能晋升"
                if learning_plan.get("policy", {}).get("validation_required", True)
                else "先将候选方案放入观察态，再决定是否执行样本重放验证"
            ),
            "updated_at": datetime.now().isoformat(),
        }

    return {
        "build_external_learning_plan": build_external_learning_plan,
        "detect_local_codex": detect_local_codex,
        "run_local_codex_learning": run_local_codex_learning,
        "execute_learning_task": execute_learning_task,
        "build_local_memory_candidates": build_local_memory_candidates,
        "build_platform_shared_candidates": build_platform_shared_candidates,
        "build_enterprise_repo_candidates": build_enterprise_repo_candidates,
        "build_historical_archive_candidates": build_historical_archive_candidates,
    }
