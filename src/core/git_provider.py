"""
Evo Core - Git Knowledge Provider

统一封装 Gitee / GitLab 等 Git 服务的知识仓库操作。
当前先落地 Gitee，接口设计保持可扩展。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class ManagedRepo:
    name: str
    full_name: str
    html_url: str
    branch: str = "master"
    private: bool = True


class GitProviderError(Exception):
    pass


class GitProvider:
    provider_name: str

    async def ensure_repo(
        self,
        *,
        token: str,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = True,
        namespace: str | None = None,
    ) -> ManagedRepo:
        raise NotImplementedError

    async def upsert_text_file(
        self,
        *,
        token: str,
        repo_full_name: str,
        file_path: str,
        content: str,
        message: str,
        branch: str = "master",
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def list_directory(
        self,
        *,
        token: str,
        repo_full_name: str,
        path: str = "",
        branch: str = "master",
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def read_text_file(
        self,
        *,
        token: str,
        repo_full_name: str,
        file_path: str,
        branch: str = "master",
    ) -> str | None:
        raise NotImplementedError


class GiteeProvider(GitProvider):
    provider_name = "gitee"

    def __init__(self, api_base: str = "https://gitee.com/api/v5", base_url: str = "https://gitee.com"):
        self.api_base = api_base.rstrip("/")
        self.base_url = base_url.rstrip("/")

    async def ensure_repo(
        self,
        *,
        token: str,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = True,
        namespace: str | None = None,
    ) -> ManagedRepo:
        headers = {"Authorization": f"token {token}"}
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(f"{self.api_base}/user", headers=headers)
            if user_resp.status_code != 200:
                raise GitProviderError(f"获取当前 Gitee 用户失败: {user_resp.text}")
            login = namespace or user_resp.json().get("login")
            if not login:
                raise GitProviderError("无法解析当前 Gitee 登录名")

            repo_resp = await client.get(f"{self.api_base}/repos/{login}/{name}", headers=headers)
            if repo_resp.status_code == 200:
                repo_data = repo_resp.json()
                return ManagedRepo(
                    name=repo_data.get("name", name),
                    full_name=repo_data.get("full_name", f"{login}/{name}"),
                    html_url=repo_data.get("html_url", f"{self.base_url}/{login}/{name}"),
                    branch=(repo_data.get("default_branch") or "master"),
                    private=bool(repo_data.get("private", private)),
                )
            if repo_resp.status_code not in {404}:
                raise GitProviderError(f"查询仓库失败: {repo_resp.text}")

            create_resp = await client.post(
                f"{self.api_base}/user/repos",
                headers=headers,
                json={
                    "name": name,
                    "description": description,
                    "private": private,
                    "auto_init": auto_init,
                },
            )
            if create_resp.status_code not in {201}:
                raise GitProviderError(f"创建仓库失败: {create_resp.text}")
            repo_data = create_resp.json()
            return ManagedRepo(
                name=repo_data.get("name", name),
                full_name=repo_data.get("full_name", f"{login}/{name}"),
                html_url=repo_data.get("html_url", f"{self.base_url}/{login}/{name}"),
                branch=(repo_data.get("default_branch") or "master"),
                private=bool(repo_data.get("private", private)),
            )

    async def upsert_text_file(
        self,
        *,
        token: str,
        repo_full_name: str,
        file_path: str,
        content: str,
        message: str,
        branch: str = "master",
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        async with httpx.AsyncClient() as client:
            check_resp = await client.get(
                f"{self.api_base}/repos/{repo_full_name}/contents/{file_path}",
                headers=headers,
                params={"ref": branch},
            )
            sha: Optional[str] = None
            if check_resp.status_code == 200:
                sha = check_resp.json().get("sha")
            elif check_resp.status_code not in {404}:
                raise GitProviderError(f"检查文件失败: {check_resp.text}")

            payload: dict[str, Any] = {
                "message": message,
                "content": encoded_content,
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha

            write_resp = await client.put(
                f"{self.api_base}/repos/{repo_full_name}/contents/{file_path}",
                headers=headers,
                json=payload,
            )
            if write_resp.status_code not in {200, 201}:
                raise GitProviderError(f"写入文件失败: {write_resp.text}")
            return write_resp.json()

    async def list_directory(
        self,
        *,
        token: str,
        repo_full_name: str,
        path: str = "",
        branch: str = "master",
    ) -> list[dict[str, Any]]:
        headers = {"Authorization": f"token {token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/repos/{repo_full_name}/contents/{path}".rstrip("/"),
                headers=headers,
                params={"ref": branch},
            )
            if resp.status_code == 404:
                return []
            if resp.status_code != 200:
                raise GitProviderError(f"读取目录失败: {resp.text}")
            data = resp.json()
            if isinstance(data, list):
                return data
            return [data] if isinstance(data, dict) else []

    async def read_text_file(
        self,
        *,
        token: str,
        repo_full_name: str,
        file_path: str,
        branch: str = "master",
    ) -> str | None:
        headers = {"Authorization": f"token {token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/repos/{repo_full_name}/contents/{file_path}",
                headers=headers,
                params={"ref": branch},
            )
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise GitProviderError(f"读取文件失败: {resp.text}")
            data = resp.json() if isinstance(resp.json(), dict) else {}
            content = data.get("content")
            if not isinstance(content, str):
                return None
            try:
                return base64.b64decode(content).decode("utf-8", errors="ignore")
            except Exception:
                return None


class GitLabProvider(GitProvider):
    provider_name = "gitlab"

    def __init__(self, api_base: str = "https://gitlab.com/api/v4", base_url: str = "https://gitlab.com"):
        self.api_base = api_base.rstrip("/")
        self.base_url = base_url.rstrip("/")

    async def ensure_repo(
        self,
        *,
        token: str,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = True,
        namespace: str | None = None,
    ) -> ManagedRepo:
        headers = {"PRIVATE-TOKEN": token}
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(f"{self.api_base}/user", headers=headers)
            if user_resp.status_code != 200:
                raise GitProviderError(f"获取当前 GitLab 用户失败: {user_resp.text}")
            user = user_resp.json()
            namespace_path = namespace or user.get("username")
            if not namespace_path:
                raise GitProviderError("无法解析当前 GitLab namespace")

            project_path = f"{namespace_path}/{name}"
            encoded_project = project_path.replace("/", "%2F")
            project_resp = await client.get(f"{self.api_base}/projects/{encoded_project}", headers=headers)
            if project_resp.status_code == 200:
                project = project_resp.json()
                return ManagedRepo(
                    name=project.get("name", name),
                    full_name=project.get("path_with_namespace", project_path),
                    html_url=project.get("web_url", f"{self.base_url}/{project_path}"),
                    branch=(project.get("default_branch") or "main"),
                    private=project.get("visibility", "private") != "public",
                )
            if project_resp.status_code not in {404}:
                raise GitProviderError(f"查询 GitLab 项目失败: {project_resp.text}")

            payload: dict[str, Any] = {
                "name": name,
                "description": description,
                "visibility": "private" if private else "public",
                "initialize_with_readme": auto_init,
            }
            if namespace:
                ns_resp = await client.get(
                    f"{self.api_base}/namespaces",
                    headers=headers,
                    params={"search": namespace},
                )
                if ns_resp.status_code != 200:
                    raise GitProviderError(f"查询 GitLab namespace 失败: {ns_resp.text}")
                namespaces = ns_resp.json() if isinstance(ns_resp.json(), list) else []
                matched = next(
                    (
                        item for item in namespaces
                        if isinstance(item, dict)
                        and str(item.get("full_path") or item.get("path") or "") == namespace
                    ),
                    None,
                )
                if not matched:
                    raise GitProviderError(f"未找到 GitLab namespace: {namespace}")
                payload["namespace_id"] = matched.get("id")

            create_resp = await client.post(f"{self.api_base}/projects", headers=headers, json=payload)
            if create_resp.status_code not in {201}:
                raise GitProviderError(f"创建 GitLab 项目失败: {create_resp.text}")
            project = create_resp.json()
            return ManagedRepo(
                name=project.get("name", name),
                full_name=project.get("path_with_namespace", project_path),
                html_url=project.get("web_url", f"{self.base_url}/{project_path}"),
                branch=(project.get("default_branch") or "main"),
                private=project.get("visibility", "private") != "public",
            )

    async def upsert_text_file(
        self,
        *,
        token: str,
        repo_full_name: str,
        file_path: str,
        content: str,
        message: str,
        branch: str = "main",
    ) -> dict[str, Any]:
        headers = {"PRIVATE-TOKEN": token}
        encoded_project = repo_full_name.replace("/", "%2F")
        encoded_path = file_path.replace("/", "%2F")
        async with httpx.AsyncClient() as client:
            check_resp = await client.get(
                f"{self.api_base}/projects/{encoded_project}/repository/files/{encoded_path}",
                headers=headers,
                params={"ref": branch},
            )
            exists = check_resp.status_code == 200
            if check_resp.status_code not in {200, 404}:
                raise GitProviderError(f"检查 GitLab 文件失败: {check_resp.text}")

            payload = {
                "branch": branch,
                "content": content,
                "commit_message": message,
                "encoding": "text",
            }
            if exists:
                write_resp = await client.put(
                    f"{self.api_base}/projects/{encoded_project}/repository/files/{encoded_path}",
                    headers=headers,
                    json=payload,
                )
                if write_resp.status_code not in {200}:
                    raise GitProviderError(f"更新 GitLab 文件失败: {write_resp.text}")
            else:
                write_resp = await client.post(
                    f"{self.api_base}/projects/{encoded_project}/repository/files/{encoded_path}",
                    headers=headers,
                    json=payload,
                )
                if write_resp.status_code not in {201}:
                    raise GitProviderError(f"创建 GitLab 文件失败: {write_resp.text}")
            return write_resp.json()

    async def list_directory(
        self,
        *,
        token: str,
        repo_full_name: str,
        path: str = "",
        branch: str = "main",
    ) -> list[dict[str, Any]]:
        headers = {"PRIVATE-TOKEN": token}
        encoded_project = repo_full_name.replace("/", "%2F")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/projects/{encoded_project}/repository/tree",
                headers=headers,
                params={"path": path, "ref": branch, "per_page": 100},
            )
            if resp.status_code == 404:
                return []
            if resp.status_code != 200:
                raise GitProviderError(f"读取 GitLab 目录失败: {resp.text}")
            data = resp.json()
            return data if isinstance(data, list) else []

    async def read_text_file(
        self,
        *,
        token: str,
        repo_full_name: str,
        file_path: str,
        branch: str = "main",
    ) -> str | None:
        headers = {"PRIVATE-TOKEN": token}
        encoded_project = repo_full_name.replace("/", "%2F")
        encoded_path = file_path.replace("/", "%2F")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/projects/{encoded_project}/repository/files/{encoded_path}",
                headers=headers,
                params={"ref": branch},
            )
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise GitProviderError(f"读取 GitLab 文件失败: {resp.text}")
            data = resp.json() if isinstance(resp.json(), dict) else {}
            content = data.get("content")
            if not isinstance(content, str):
                return None
            encoding = str(data.get("encoding") or "").lower()
            try:
                if encoding == "base64":
                    return base64.b64decode(content).decode("utf-8", errors="ignore")
                return content
            except Exception:
                return None


def get_git_provider(platform: str, api_base: str, base_url: str) -> GitProvider:
    platform_name = (platform or "").lower()
    if platform_name == "gitee" or "gitee.com" in api_base or "gitee.com" in base_url:
        return GiteeProvider(api_base=api_base, base_url=base_url)
    if platform_name == "gitlab" or "gitlab" in api_base or "gitlab" in base_url:
        return GitLabProvider(api_base=api_base, base_url=base_url)
    raise GitProviderError(f"暂不支持的 Git provider: {platform}")


__all__ = [
    "ManagedRepo",
    "GitProvider",
    "GitProviderError",
    "GiteeProvider",
    "GitLabProvider",
    "get_git_provider",
]
