"""
Git knowledge / 企业知识仓相关接口。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import Request

from core import ExperienceStore, GitProviderError


def register_git_knowledge_routes(
    app,
    *,
    workspace: Path,
    config,
    tenant_manager,
    task_queue,
    plugin_summary,
    get_user_gitee_token: Callable[[Request], str | None],
    get_git_provider_instance: Callable[[object, dict | None], object],
    resolve_git_runtime_config: Callable[[object, dict | None], tuple[str, str, str]],
    load_enterprise_repo_index: Callable[[Path, str], dict],
    save_enterprise_repo_index: Callable[[Path, str, dict], None],
    summarize_enterprise_repo_index: Callable[[dict], dict],
    build_tenant_knowledge_containers: Callable[[Path, object, str, object], list[dict]],
    build_enterprise_repo_index_template: Callable[..., dict],
    scan_enterprise_repo_contents: Callable[..., object],
    normalize_git_knowledge_payload: Callable[[dict], dict],
    sanitize_repo_name: Callable[[object], str],
    get_tenant_git_repo: Callable[[object, str, str, str, str], tuple[str, str]],
    load_autonomy_runtime: Callable[[Path], dict],
    build_evolution_overview: Callable[..., dict],
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    def collect_child_experience_journals(runtime: dict) -> tuple[list[dict], dict]:
        child_members = runtime.get("child_members", {}) if isinstance(runtime.get("child_members"), dict) else {}
        items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
        journals: list[dict] = []
        card_total = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            journal = item.get("experience_journal", {}) if isinstance(item.get("experience_journal"), dict) else {}
            cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
            normalized_cards = [card for card in cards if isinstance(card, dict)]
            if not normalized_cards:
                continue
            card_total += len(normalized_cards)
            journals.append({
                "member_id": str(item.get("member_id") or "").strip() or None,
                "name": str(item.get("name") or "").strip() or None,
                "primary_role": str(item.get("primary_role") or "").strip() or None,
                "last_compiled_at": journal.get("last_compiled_at"),
                "latest_card_id": journal.get("latest_card_id"),
                "card_count": len(normalized_cards),
                "cards": normalized_cards[:8],
            })
        journals.sort(key=lambda item: str(item.get("last_compiled_at") or ""), reverse=True)
        summary = {
            "member_count": len(journals),
            "card_total": card_total,
            "latest_compiled_at": journals[0].get("last_compiled_at") if journals else None,
        }
        return journals, summary

    @app.get("/api/knowledge/skills")
    async def list_skills(tenant_id: str = "default"):
        target_repo, target_url = get_tenant_git_repo(
            tenant_manager,
            tenant_id,
            "skills",
            config.knowledge.full_name,
            config.knowledge.url,
        )
        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        knowledge_containers = build_tenant_knowledge_containers(workspace, tenant_manager, tenant_id, config)
        evolution_overview = build_evolution_overview(
            workspace=workspace,
            tenant_id=tenant_id,
            task_queue=task_queue,
            plugin_summary=plugin_summary,
            tenant_manager=tenant_manager,
        )
        skill_entries: list[dict] = []

        for trust_level in ("verified", "draft"):
            skills_dir = workspace / ".tenants" / tenant_id / "skills" / trust_level
            if not skills_dir.is_dir():
                continue
            for skill_file in sorted(skills_dir.glob("*.json")):
                try:
                    with open(skill_file, encoding="utf-8") as f:
                        skill_data = json.load(f)
                    skill_entries.append({
                        "id": skill_data.get("id", skill_file.stem),
                        "name": skill_data.get("name", skill_file.stem),
                        "domain": skill_data.get("domain", "javascript"),
                        "trust_level": trust_level,
                        "source": skill_data.get("source", "local"),
                        "path": str(skill_file),
                        "usage_count": skill_data.get("usage_count", 0),
                        "success_rate": skill_data.get("success_rate"),
                        "updated_at": skill_data.get("updated_at") or skill_data.get("created_at"),
                    })
                except Exception:
                    skill_entries.append({
                        "id": skill_file.stem,
                        "name": skill_file.stem,
                        "domain": "unknown",
                        "trust_level": trust_level,
                        "source": "local",
                        "path": str(skill_file),
                    })

        auto_generated_skills = [
            item for item in skill_entries
            if str(item.get("source") or "").startswith("stable_experience_")
            or str(item.get("source") or "").startswith("mission_delivery_")
        ]
        auto_draft_count = len([
            item for item in auto_generated_skills
            if str(item.get("trust_level") or "") == "draft"
        ])
        auto_verified_count = len([
            item for item in auto_generated_skills
            if str(item.get("trust_level") or "") == "verified"
        ])
        recent_autonomy_skills = sorted(
            auto_generated_skills,
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )[:6]

        return success_response({
            "tenant_id": tenant_id,
            "repo": target_url,
            "repo_full_name": target_repo,
            "git_knowledge": git_knowledge,
            "knowledge_containers": knowledge_containers,
            "knowledge_layer_advice": evolution_overview.get("knowledge_layer_advice", {}),
            "autonomy_skill_summary": {
                "auto_generated_total": len(auto_generated_skills),
                "auto_draft_count": auto_draft_count,
                "auto_verified_count": auto_verified_count,
            },
            "recent_autonomy_skills": recent_autonomy_skills,
            "skills": skill_entries,
        })

    @app.post("/api/knowledge/sync-local-skills")
    async def sync_local_skills(request: Request):
        data = await request.json()
        tenant_id = data.get("tenant_id", "default")
        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token or token == "your_real_token_here":
            return error_response("未找到可用的 Gitee Token", 400)

        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        provider = get_git_provider_instance(config, git_knowledge)
        target_repo, target_url = get_tenant_git_repo(
            tenant_manager,
            tenant_id,
            "skills",
            config.knowledge.full_name,
            config.knowledge.url,
        )
        skills_dir = workspace / ".tenants" / tenant_id / "skills" / "draft"
        if not skills_dir.is_dir():
            return success_response({
                "tenant_id": tenant_id,
                "count": 0,
                "repo": target_url,
                "uploaded": [],
            }, "当前租户没有本地技能草稿")

        uploaded: list[dict] = []
        for skill_file in sorted(skills_dir.glob("*.json")):
            try:
                with open(skill_file, encoding="utf-8") as f:
                    skill_data = json.load(f)
                domain = skill_data.get("domain", "javascript")
                skill_name = skill_data.get("name", skill_file.stem)
                file_path = f"skills/{domain}/{skill_name}.json"
                await provider.upsert_text_file(
                    token=token,
                    repo_full_name=target_repo,
                    file_path=file_path,
                    content=json.dumps(skill_data, indent=2, ensure_ascii=False),
                    message=f"Sync local skill: {skill_name}",
                    branch="master",
                )
                uploaded.append({
                    "name": skill_name,
                    "domain": domain,
                    "path": file_path,
                })
            except Exception as exc:
                uploaded.append({
                    "name": skill_file.stem,
                    "error": str(exc),
                })

        return success_response({
            "tenant_id": tenant_id,
            "count": len([item for item in uploaded if "error" not in item]),
            "repo": target_url,
            "uploaded": uploaded,
        }, "本地技能同步完成")

    @app.get("/api/knowledge/skills/{domain}/{skill_name}")
    async def get_skill_detail(domain: str, skill_name: str, tenant_id: str = "default"):
        for trust_level in ("verified", "draft"):
            skill_file = workspace / ".tenants" / tenant_id / "skills" / trust_level / f"{skill_name}.json"
            if not skill_file.is_file():
                continue
            try:
                with open(skill_file, encoding="utf-8") as f:
                    skill_data = json.load(f)
                return success_response({
                    **skill_data,
                    "trust_level": skill_data.get("trust_level", trust_level),
                    "path": str(skill_file),
                })
            except Exception as exc:
                return error_response(f"技能详情读取失败: {exc}", 500)

        return success_response({
            "name": skill_name,
            "domain": domain,
            "trust_level": "unknown",
            "description": f"Skill {skill_name} not found in tenant {tenant_id}",
        })

    @app.post("/api/skills/upload")
    async def upload_skill(request: Request):
        data = await request.json()
        skill_data = data.get("skill")
        tenant_id = data.get("tenant_id", "default")
        if not skill_data:
            return error_response("缺少 skill 数据", 400)

        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token or token == "your_real_token_here":
            return error_response("未找到可用的 Gitee Token", 500)

        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        provider = get_git_provider_instance(config, git_knowledge)
        domain = skill_data.get("domain", "javascript")
        skill_name = skill_data.get("name", f"skill_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        file_path = f"skills/{domain}/{skill_name}.json"
        content = json.dumps(skill_data, indent=2, ensure_ascii=False)
        target_repo, target_url = get_tenant_git_repo(
            tenant_manager,
            tenant_id,
            "skills",
            config.knowledge.full_name,
            config.knowledge.url,
        )
        try:
            await provider.upsert_text_file(
                token=token,
                repo_full_name=target_repo,
                file_path=file_path,
                content=content,
                message=f"Upload skill: {skill_name}",
                branch="master",
            )
        except GitProviderError as exc:
            return error_response(str(exc), 500)

        return success_response({
            "url": f"{target_url}/blob/master/{file_path}",
            "tenant_id": tenant_id,
            "file_path": file_path,
        }, f"技能 {skill_name} 已上传到知识库")

    @app.get("/api/git/provider/status")
    async def git_provider_status(request: Request):
        token = get_user_gitee_token(request)
        tenant_id = request.query_params.get("tenant_id", "default")
        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        provider = get_git_provider_instance(config, git_knowledge)
        _, api_base, _ = resolve_git_runtime_config(config, git_knowledge)
        repo_index = load_enterprise_repo_index(workspace, tenant_id)
        return success_response({
            "provider": provider.provider_name,
            "api_base": api_base,
            "has_user_token": bool(token),
            "tenant_id": tenant_id,
            "git_knowledge": git_knowledge,
            "repo_index": repo_index,
            "repo_index_summary": summarize_enterprise_repo_index(repo_index),
            "knowledge_containers": build_tenant_knowledge_containers(workspace, tenant_manager, tenant_id, config),
        })

    @app.get("/api/tenants/{tenant_id}/knowledge-containers")
    async def get_tenant_knowledge_containers(tenant_id: str):
        return success_response({
            "tenant_id": tenant_id,
            "containers": build_tenant_knowledge_containers(workspace, tenant_manager, tenant_id, config),
        })

    @app.get("/api/tenants/{tenant_id}/git-knowledge/config")
    async def get_tenant_git_knowledge_config(tenant_id: str):
        repo_index = load_enterprise_repo_index(workspace, tenant_id)
        return success_response({
            "tenant_id": tenant_id,
            "git_knowledge": tenant_manager.get_git_knowledge_config(tenant_id),
            "repo_index": repo_index,
            "repo_index_summary": summarize_enterprise_repo_index(repo_index),
            "knowledge_containers": build_tenant_knowledge_containers(workspace, tenant_manager, tenant_id, config),
        })

    @app.get("/api/tenants/{tenant_id}/git-knowledge/index-template")
    async def get_tenant_git_knowledge_index_template(tenant_id: str):
        template = build_enterprise_repo_index_template(
            workspace=workspace,
            tenant_id=tenant_id,
            task_queue=task_queue,
            plugin_summary=plugin_summary,
            tenant_manager=tenant_manager,
        )
        repo_index = load_enterprise_repo_index(workspace, tenant_id)
        return success_response({
            "tenant_id": tenant_id,
            "template": template,
            "repo_index": repo_index,
            "repo_index_summary": summarize_enterprise_repo_index(repo_index),
        })

    @app.post("/api/tenants/{tenant_id}/git-knowledge/index-template/export")
    async def export_tenant_git_knowledge_index_template(tenant_id: str, request: Request):
        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token:
            return error_response("当前用户未绑定可用 Token，且服务端也未配置 GITEE_TOKEN", 400)

        payload = await request.json()
        repo_key = str(payload.get("repo_key") or "config").strip() or "config"
        file_path = str(payload.get("file_path") or "evo/index.json").strip() or "evo/index.json"
        scan_after_write = bool(payload.get("scan_after_write", True))

        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        repo = repos.get(repo_key) if isinstance(repos, dict) else None
        if not isinstance(repo, dict):
            return error_response(f"当前租户不存在 repo_key={repo_key} 的知识仓", 400)

        template = build_enterprise_repo_index_template(
            workspace=workspace,
            tenant_id=tenant_id,
            task_queue=task_queue,
            plugin_summary=plugin_summary,
            tenant_manager=tenant_manager,
        )
        provider = get_git_provider_instance(config, git_knowledge)
        branch = str(repo.get("branch") or "main")
        repo_full_name = str(repo.get("full_name") or "")
        repo_url = str(repo.get("url") or "")
        if not repo_full_name:
            return error_response(f"repo_key={repo_key} 缺少 full_name 配置", 400)

        try:
            await provider.upsert_text_file(
                token=token,
                repo_full_name=repo_full_name,
                file_path=file_path,
                content=json.dumps(template, indent=2, ensure_ascii=False),
                message=f"Export evo index template for tenant {tenant_id}",
                branch=branch,
            )
        except GitProviderError as exc:
            return error_response(str(exc), 500)

        scan_result: dict | None = None
        if scan_after_write:
            try:
                scanned = await scan_enterprise_repo_contents(
                    workspace=workspace,
                    tenant_id=tenant_id,
                    repo_key=repo_key,
                    repo=repo,
                    provider=provider,
                    token=token,
                )
                repo_index = load_enterprise_repo_index(workspace, tenant_id)
                repo_index["repos"] = {
                    **(repo_index.get("repos", {}) if isinstance(repo_index.get("repos"), dict) else {}),
                    repo_key: scanned,
                }
                save_enterprise_repo_index(workspace, tenant_id, repo_index)
                scan_result = scanned
            except GitProviderError as exc:
                scan_result = {
                    "repo_key": repo_key,
                    "error": str(exc),
                }

        repo_index = load_enterprise_repo_index(workspace, tenant_id)
        return success_response({
            "tenant_id": tenant_id,
            "repo_key": repo_key,
            "file_path": file_path,
            "repo_full_name": repo_full_name,
            "repo_url": repo_url,
            "branch": branch,
            "template": template,
            "scan_after_write": scan_after_write,
            "scan_result": scan_result,
            "repo_index": repo_index,
            "repo_index_summary": summarize_enterprise_repo_index(repo_index),
        }, "企业索引模板已写入知识仓")

    @app.put("/api/tenants/{tenant_id}/git-knowledge/config")
    async def update_tenant_git_knowledge_config(tenant_id: str, request: Request):
        data = await request.json()
        try:
            git_knowledge = normalize_git_knowledge_payload(data.get("git_knowledge", data))
        except ValueError as exc:
            return error_response(str(exc), 400)

        tenant_manager.set_git_knowledge_config(tenant_id, git_knowledge)
        return success_response({
            "tenant_id": tenant_id,
            "git_knowledge": tenant_manager.get_git_knowledge_config(tenant_id),
            "knowledge_containers": build_tenant_knowledge_containers(workspace, tenant_manager, tenant_id, config),
        }, "租户 Git knowledge 配置已更新")

    @app.post("/api/tenants/{tenant_id}/git-knowledge/scan")
    async def scan_tenant_git_knowledge(tenant_id: str, request: Request):
        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token:
            return error_response("当前用户未绑定可用 Token，且服务端也未配置 GITEE_TOKEN", 400)

        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        if not isinstance(repos, dict) or not repos:
            return error_response("当前租户还没有可扫描的 Git knowledge 仓库", 400)

        provider = get_git_provider_instance(config, git_knowledge)
        scanned: dict[str, dict] = {}
        errors: list[dict] = []
        for repo_key, repo in repos.items():
            if not isinstance(repo_key, str) or not isinstance(repo, dict):
                continue
            try:
                scanned[repo_key] = await scan_enterprise_repo_contents(
                    workspace=workspace,
                    tenant_id=tenant_id,
                    repo_key=repo_key,
                    repo=repo,
                    provider=provider,
                    token=token,
                )
            except GitProviderError as exc:
                errors.append({"repo_key": repo_key, "error": str(exc)})

        index_payload = load_enterprise_repo_index(workspace, tenant_id)
        index_payload["repos"] = {
            **(index_payload.get("repos", {}) if isinstance(index_payload.get("repos"), dict) else {}),
            **scanned,
        }
        save_enterprise_repo_index(workspace, tenant_id, index_payload)

        latest_index = load_enterprise_repo_index(workspace, tenant_id)
        return success_response({
            "tenant_id": tenant_id,
            "provider": provider.provider_name,
            "scanned": scanned,
            "errors": errors,
            "repo_index": latest_index,
            "repo_index_summary": summarize_enterprise_repo_index(latest_index),
        }, "企业 Git knowledge 索引扫描已完成")

    @app.post("/api/tenants/{tenant_id}/git-knowledge/bootstrap")
    async def bootstrap_tenant_git_knowledge(tenant_id: str, request: Request):
        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token:
            return error_response("当前用户未绑定 Gitee Token，且服务端也未配置 GITEE_TOKEN", 400)

        data = await request.json()
        runtime_git_knowledge = {
            "provider": data.get("provider"),
            "api_base": data.get("api_base"),
            "base_url": data.get("base_url"),
            "namespace": data.get("namespace"),
        }
        provider = get_git_provider_instance(config, runtime_git_knowledge)

        base_name = sanitize_repo_name(data.get("base_name") or f"evo-{tenant_id}")
        namespace = str(data.get("namespace") or "").strip() or None
        repo_specs = [
            ("skills", f"{base_name}-skills", "Tenant skills knowledge"),
            ("experiences", f"{base_name}-experiences", "Tenant curated experiences"),
            ("strategies", f"{base_name}-strategies", "Tenant strategies and evaluators"),
            ("toutiao", f"{base_name}-toutiao", "Tenant self media content and analytics"),
            ("reports", f"{base_name}-reports", "Tenant reports and snapshots"),
            ("config", f"{base_name}-config", "Tenant git knowledge config"),
        ]

        created_repos: dict[str, dict] = {}
        try:
            for key, repo_name, description in repo_specs:
                repo = await provider.ensure_repo(
                    token=token,
                    name=repo_name,
                    description=description,
                    private=bool(data.get("private", True)),
                    auto_init=True,
                    namespace=namespace,
                )
                created_repos[key] = {
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "url": repo.html_url,
                    "branch": repo.branch,
                    "private": repo.private,
                }
        except GitProviderError as exc:
            return error_response(str(exc), 500)

        tenant_manager.set_git_knowledge_config(tenant_id, {
            "provider": provider.provider_name,
            "api_base": str(data.get("api_base") or "").strip() or config.api_base,
            "base_url": str(data.get("base_url") or "").strip() or config.knowledge.base_url,
            "namespace": namespace,
            "base_name": base_name,
            "repos": created_repos,
            "bootstrapped_at": datetime.now().isoformat(),
        })
        return success_response({
            "tenant_id": tenant_id,
            "git_knowledge": tenant_manager.get_git_knowledge_config(tenant_id),
            "knowledge_containers": build_tenant_knowledge_containers(workspace, tenant_manager, tenant_id, config),
        }, "租户知识仓库已初始化")

    @app.post("/api/tenants/{tenant_id}/git-knowledge/export/experiences")
    async def export_tenant_experiences_to_git(tenant_id: str, request: Request):
        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token or token == "your_real_token_here":
            return error_response("未找到可用的 Gitee Token", 400)

        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        provider = get_git_provider_instance(config, git_knowledge)
        target_repo, target_url = get_tenant_git_repo(
            tenant_manager,
            tenant_id,
            "experiences",
            config.experiences.full_name,
            config.experiences.url,
        )
        store = ExperienceStore(workspace, tenant_id)
        autonomy_runtime = load_autonomy_runtime(workspace, tenant_id)
        child_experience_journals, journal_summary = collect_child_experience_journals(autonomy_runtime)
        payload = {
            "tenant_id": tenant_id,
            "exported_at": datetime.now().isoformat(),
            "growth_events": [exp.to_dict() for exp in store.load_by_task("evolution", "growth_event", limit=30)],
            "replay_validations": [exp.to_dict() for exp in store.load_by_task("evolution", "replay_validation", limit=20)],
            "child_experience_journals": child_experience_journals,
            "journal_summary": journal_summary,
        }
        file_path = f"exports/experiences/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            await provider.upsert_text_file(
                token=token,
                repo_full_name=target_repo,
                file_path=file_path,
                content=json.dumps(payload, indent=2, ensure_ascii=False),
                message=f"Export experiences for tenant {tenant_id}",
                branch="master",
            )
        except GitProviderError as exc:
            return error_response(str(exc), 500)

        return success_response({
            "tenant_id": tenant_id,
            "repo": target_url,
            "file_path": file_path,
            "journal_summary": journal_summary,
        }, "经验摘要已导出到 Git knowledge")

    @app.post("/api/tenants/{tenant_id}/git-knowledge/export/report")
    async def export_tenant_report_to_git(tenant_id: str, request: Request):
        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token or token == "your_real_token_here":
            return error_response("未找到可用的 Gitee Token", 400)

        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        provider = get_git_provider_instance(config, git_knowledge)
        target_repo, target_url = get_tenant_git_repo(
            tenant_manager,
            tenant_id,
            "reports",
            config.knowledge.full_name,
            config.knowledge.url,
        )
        overview = build_evolution_overview(
            workspace=workspace,
            tenant_id=tenant_id,
            task_queue=task_queue,
            plugin_summary=plugin_summary,
            tenant_manager=tenant_manager,
        )
        file_path = f"reports/evolution_overview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            await provider.upsert_text_file(
                token=token,
                repo_full_name=target_repo,
                file_path=file_path,
                content=json.dumps(overview, indent=2, ensure_ascii=False),
                message=f"Export evolution overview for tenant {tenant_id}",
                branch="master",
            )
        except GitProviderError as exc:
            return error_response(str(exc), 500)

        return success_response({
            "tenant_id": tenant_id,
            "repo": target_url,
            "file_path": file_path,
        }, "成长总览已导出到 Git knowledge")
