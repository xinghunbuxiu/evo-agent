"""
Git knowledge / 企业知识仓运行时：
负责仓配置、索引扫描、模板生成与容器解析。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from core import (
    KnowledgeContainerResolver,
    get_distributed_config,
    get_git_provider,
)
from core.tenant import TenantManager


def create_git_knowledge_runtime_bindings(
    *,
    load_learning_tasks: Callable[[Path], dict],
    trim_candidate_text: Callable[[str | None, int], str],
    build_evolution_overview: Callable[..., dict],
):
    def sanitize_repo_name(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe.strip("-") or "tenant"

    def resolve_git_runtime_config(config, git_knowledge: dict | None = None) -> tuple[str, str, str]:
        git_knowledge = git_knowledge if isinstance(git_knowledge, dict) else {}
        provider = str(git_knowledge.get("provider") or "").strip() or str(config.platform or "gitee")
        api_base = str(git_knowledge.get("api_base") or "").strip() or str(config.api_base or "")
        base_url = str(git_knowledge.get("base_url") or "").strip() or str(config.knowledge.base_url or "https://gitee.com")
        return provider, api_base, base_url

    def get_git_provider_instance(config, git_knowledge: dict | None = None):
        provider, api_base, base_url = resolve_git_runtime_config(config, git_knowledge)
        return get_git_provider(provider, api_base, base_url)

    def get_tenant_git_repo(
        tenant_manager: TenantManager,
        tenant_id: str,
        repo_key: str,
        fallback_full_name: str,
        fallback_url: str,
    ) -> tuple[str, str]:
        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        resolver = KnowledgeContainerResolver(Path.cwd(), get_distributed_config())
        repo_full_name, repo_url = resolver.resolve_repo(repo_key, git_knowledge)
        return repo_full_name or fallback_full_name, repo_url or fallback_url

    def build_tenant_knowledge_containers(
        workspace: Path,
        tenant_manager: TenantManager,
        tenant_id: str,
        config,
    ) -> list[dict]:
        resolver = KnowledgeContainerResolver(workspace, config)
        return resolver.build_tenant_containers(
            tenant_id,
            git_knowledge=tenant_manager.get_git_knowledge_config(tenant_id),
            knowledge_policy=tenant_manager.get_knowledge_policy(tenant_id),
        )

    def normalize_git_knowledge_payload(payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("git_knowledge 必须是对象")

        repos_payload = payload.get("repos", {})
        repos_payload = repos_payload if isinstance(repos_payload, dict) else {}
        normalized_repos: dict[str, dict] = {}
        for repo_key, repo in repos_payload.items():
            if not isinstance(repo_key, str) or not isinstance(repo, dict):
                continue
            full_name = str(repo.get("full_name") or "").strip()
            url = str(repo.get("url") or "").strip()
            if not full_name and not url:
                continue
            normalized_repos[repo_key] = {
                "name": str(repo.get("name") or repo_key).strip() or repo_key,
                "full_name": full_name or str(repo.get("name") or repo_key).strip(),
                "url": url,
                "branch": str(repo.get("branch") or "main").strip() or "main",
                "private": bool(repo.get("private", True)),
            }

        provider = str(payload.get("provider") or "").strip() or "gitee"
        return {
            "provider": provider,
            "api_base": str(payload.get("api_base") or "").strip() or None,
            "base_url": str(payload.get("base_url") or "").strip() or None,
            "namespace": str(payload.get("namespace") or "").strip() or None,
            "base_name": str(payload.get("base_name") or "").strip() or None,
            "repos": normalized_repos,
            "bootstrapped_at": payload.get("bootstrapped_at") or datetime.now().isoformat(),
        }

    def enterprise_repo_index_file(workspace: Path, tenant_id: str) -> Path:
        data_dir = workspace / ".tenants" / tenant_id / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "enterprise_repo_index.json"

    def load_enterprise_repo_index(workspace: Path, tenant_id: str) -> dict:
        path = enterprise_repo_index_file(workspace, tenant_id)
        if not path.is_file():
            return {"tenant_id": tenant_id, "updated_at": None, "repos": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        return {
            "tenant_id": tenant_id,
            "updated_at": data.get("updated_at"),
            "repos": data.get("repos", {}) if isinstance(data.get("repos"), dict) else {},
        }

    def save_enterprise_repo_index(workspace: Path, tenant_id: str, payload: dict) -> None:
        normalized = {
            "tenant_id": tenant_id,
            "updated_at": datetime.now().isoformat(),
            "repos": payload.get("repos", {}) if isinstance(payload, dict) else {},
        }
        enterprise_repo_index_file(workspace, tenant_id).write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def summarize_enterprise_repo_index(index_payload: dict) -> dict:
        repos = index_payload.get("repos", {}) if isinstance(index_payload, dict) else {}
        repos = repos if isinstance(repos, dict) else {}
        indexed_repo_count = 0
        total_entries = 0
        repo_summaries: list[dict] = []
        for repo_key, repo_data in repos.items():
            if not isinstance(repo_data, dict):
                continue
            entry_count = int(repo_data.get("entry_count") or 0)
            if entry_count > 0:
                indexed_repo_count += 1
            total_entries += max(entry_count, 0)
            repo_summaries.append({
                "repo_key": repo_key,
                "index_path": repo_data.get("index_path"),
                "entry_count": entry_count,
                "scanned_at": repo_data.get("scanned_at"),
            })
        repo_summaries.sort(key=lambda item: (item.get("entry_count") or 0), reverse=True)
        return {
            "updated_at": index_payload.get("updated_at") if isinstance(index_payload, dict) else None,
            "repo_count": len(repo_summaries),
            "indexed_repo_count": indexed_repo_count,
            "total_entries": total_entries,
            "repos": repo_summaries,
        }

    def extract_enterprise_repo_index_entries(repo_key: str, content: str | None) -> list[dict]:
        if not content:
            return []
        try:
            payload = json.loads(content)
        except Exception:
            return []

        if isinstance(payload, dict):
            entries = payload.get("entries", payload.get("items", []))
        else:
            entries = payload
        if not isinstance(entries, list):
            return []

        normalized: list[dict] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "title": str(item.get("title") or item.get("name") or item.get("id") or repo_key),
                "summary": trim_candidate_text(item.get("summary") or item.get("description") or ""),
                "keywords": item.get("keywords", []) if isinstance(item.get("keywords"), list) else [],
                "path": str(item.get("path") or item.get("file") or ""),
                "type": str(item.get("type") or repo_key),
            })
        return normalized[:20]

    async def scan_enterprise_repo_contents(
        workspace: Path,
        tenant_id: str,
        repo_key: str,
        repo: dict,
        provider,
        token: str,
    ) -> dict:
        repo_full_name = str(repo.get("full_name") or "")
        branch = str(repo.get("branch") or "main")
        common_index_paths = [
            "evo/index.json",
            "catalog/index.json",
            "catalog/skills.json",
            "catalog/experiences.json",
            "indexes/knowledge.json",
            ".evo/index.json",
        ]
        root_entries = await provider.list_directory(
            token=token,
            repo_full_name=repo_full_name,
            path="",
            branch=branch,
        )
        root_paths = [str(item.get("path") or item.get("name") or "") for item in root_entries if isinstance(item, dict)]
        selected_index_path = None
        extracted_entries: list[dict] = []

        for candidate_path in common_index_paths:
            text = await provider.read_text_file(
                token=token,
                repo_full_name=repo_full_name,
                file_path=candidate_path,
                branch=branch,
            )
            extracted_entries = extract_enterprise_repo_index_entries(repo_key, text)
            if extracted_entries:
                selected_index_path = candidate_path
                break

        return {
            "repo_key": repo_key,
            "full_name": repo_full_name,
            "branch": branch,
            "url": repo.get("url"),
            "scanned_at": datetime.now().isoformat(),
            "index_path": selected_index_path,
            "root_paths": root_paths[:30],
            "entries": extracted_entries,
            "entry_count": len(extracted_entries),
        }

    def collect_local_skill_template_entries(workspace: Path, tenant_id: str, limit: int = 6) -> list[dict]:
        skills_dir = workspace / ".tenants" / tenant_id / "skills"
        entries: list[dict] = []
        if not skills_dir.is_dir():
            return entries

        skill_files = sorted(skills_dir.rglob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for file_path in skill_files[:limit]:
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name") or file_path.stem)
            domain = str(payload.get("domain") or "general")
            summary = trim_candidate_text(
                payload.get("description")
                or payload.get("summary")
                or payload.get("problem_pattern")
                or ""
            )
            keywords = [
                keyword
                for keyword in [
                    domain,
                    payload.get("trust_level"),
                    payload.get("framework"),
                    payload.get("skill_type"),
                ]
                if isinstance(keyword, str) and keyword.strip()
            ]
            entries.append({
                "id": f"skill:{name}",
                "type": "skill",
                "title": name,
                "summary": summary or f"{domain} 方向本地技能",
                "keywords": keywords[:8],
                "path": str(file_path.relative_to(workspace)),
                "source": "tenant_local_skill",
            })
        return entries

    def build_enterprise_repo_index_template(
        workspace: Path,
        tenant_id: str,
        task_queue,
        plugin_summary,
        tenant_manager: TenantManager,
    ) -> dict:
        overview = build_evolution_overview(
            workspace=workspace,
            tenant_id=tenant_id,
            task_queue=task_queue,
            plugin_summary=plugin_summary,
            tenant_manager=tenant_manager,
        )
        growth_timeline = overview.get("growth_timeline", []) if isinstance(overview, dict) else []
        review_queue = overview.get("strategy_review_queue", []) if isinstance(overview, dict) else []
        learning_tasks = load_learning_tasks(workspace).get("tasks", {})
        learning_items = learning_tasks.values() if isinstance(learning_tasks, dict) else []

        experience_entries: list[dict] = []
        for item in growth_timeline[:4]:
            if not isinstance(item, dict):
                continue
            experience_entries.append({
                "id": str(item.get("id") or item.get("strategy_id") or item.get("event_type") or "experience"),
                "type": "experience",
                "title": str(item.get("title") or item.get("event_type") or "growth event"),
                "summary": trim_candidate_text(item.get("detail") or ""),
                "keywords": [
                    keyword for keyword in [
                        item.get("event_type"),
                        item.get("strategy_id"),
                        "growth",
                        "observation",
                    ]
                    if isinstance(keyword, str) and keyword.strip()
                ][:8],
                "path": f"experiences/{tenant_id}/growth_timeline.json",
                "source": "tenant_growth_timeline",
            })

        strategy_entries: list[dict] = []
        for item in review_queue[:4]:
            if not isinstance(item, dict):
                continue
            strategy_entries.append({
                "id": str(item.get("strategy_id") or item.get("id") or "strategy"),
                "type": "strategy",
                "title": str(item.get("strategy_id") or item.get("id") or "strategy"),
                "summary": trim_candidate_text(item.get("notes") or item.get("draft", {}).get("summary") or ""),
                "keywords": [
                    keyword for keyword in [
                        item.get("alert_reason"),
                        item.get("status"),
                        "review_queue",
                    ]
                    if isinstance(keyword, str) and keyword.strip()
                ][:8],
                "path": f"strategies/{tenant_id}/review_queue.json",
                "source": "tenant_strategy_review",
            })

        report_entries: list[dict] = []
        for item in list(learning_items)[:4]:
            if not isinstance(item, dict):
                continue
            report_entries.append({
                "id": str(item.get("task_id") or item.get("source_dir") or "report"),
                "type": "report",
                "title": str(item.get("issue_category") or "learning-task"),
                "summary": trim_candidate_text(item.get("next_validation_action") or item.get("source_dir") or ""),
                "keywords": [
                    keyword for keyword in [
                        item.get("issue_category"),
                        item.get("status"),
                        "learning_task",
                    ]
                    if isinstance(keyword, str) and keyword.strip()
                ][:8],
                "path": f"reports/{tenant_id}/learning_tasks.json",
                "source": "tenant_learning_tasks",
            })

        skill_entries = collect_local_skill_template_entries(workspace, tenant_id)
        template_entries = [*skill_entries, *experience_entries, *strategy_entries, *report_entries][:16]

        return {
            "schema_version": "1.0",
            "tenant_id": tenant_id,
            "generated_at": datetime.now().isoformat(),
            "description": "Starter enterprise knowledge index for Evo autonomous learning.",
            "entries": template_entries,
        }

    return {
        "sanitize_repo_name": sanitize_repo_name,
        "resolve_git_runtime_config": resolve_git_runtime_config,
        "get_git_provider_instance": get_git_provider_instance,
        "get_tenant_git_repo": get_tenant_git_repo,
        "build_tenant_knowledge_containers": build_tenant_knowledge_containers,
        "normalize_git_knowledge_payload": normalize_git_knowledge_payload,
        "load_enterprise_repo_index": load_enterprise_repo_index,
        "save_enterprise_repo_index": save_enterprise_repo_index,
        "summarize_enterprise_repo_index": summarize_enterprise_repo_index,
        "scan_enterprise_repo_contents": scan_enterprise_repo_contents,
        "collect_local_skill_template_entries": collect_local_skill_template_entries,
        "build_enterprise_repo_index_template": build_enterprise_repo_index_template,
    }
