"""
自媒体执行运行时：头条执行器、连接器探测、分析、评论与账号辅助。

当前默认只走 Evo 自己的本地执行器骨架，后续再逐步补齐真实浏览器、
移动端接入与更稳定的发布链路。
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable

from core import ExperienceStore


def create_self_media_runtime_bindings(
    *,
    trim_candidate_text: Callable[[str | None, int], str],
    load_autonomy_runtime: Callable[[Path], dict],
):
    def _named_executor_candidates(workspace: Path, payload: dict | None = None) -> list[dict]:
        payload = payload if isinstance(payload, dict) else {}
        autonomy_runtime = load_autonomy_runtime(workspace)
        self_media_runtime = autonomy_runtime.get("self_media", {}) if isinstance(autonomy_runtime.get("self_media"), dict) else {}
        _ = self_media_runtime.get("executor", {}) if isinstance(self_media_runtime.get("executor"), dict) else {}
        candidates: list[dict] = [
            {
                "key": "evo_toutiao_executor",
                "label": "Evo Toutiao Executor",
                "adapter": "evo_local",
                "source": "evo",
                "root_dir": str(workspace / "executors" / "toutiao"),
            },
        ]
        return candidates

    def describe_toutiao_executor_registry(workspace: Path, payload: dict | None = None) -> dict:
        payload = payload if isinstance(payload, dict) else {}
        autonomy_runtime = load_autonomy_runtime(workspace)
        self_media_runtime = autonomy_runtime.get("self_media", {}) if isinstance(autonomy_runtime.get("self_media"), dict) else {}
        executor_runtime = self_media_runtime.get("executor", {}) if isinstance(self_media_runtime.get("executor"), dict) else {}
        preferred_mode = str(
            payload.get("executor_mode")
            or payload.get("executor_preference")
            or executor_runtime.get("preferred_mode")
            or "evo"
        ).strip().lower() or "evo"
        candidates = _named_executor_candidates(workspace, payload)
        executors: list[dict] = []
        for item in candidates:
            root_dir = str(item.get("root_dir") or "").strip()
            available = Path(root_dir).is_dir() if root_dir else False
            executors.append({
                **item,
                "available": available,
            })
        preferred_order = {
            "evo": ["evo_toutiao_executor"],
            "auto": ["evo_toutiao_executor"],
        }
        order = preferred_order.get(preferred_mode, preferred_order["auto"])
        indexed = {item["key"]: item for item in executors}
        selected = next(
            (indexed[key] for key in order if indexed.get(key, {}).get("available")),
            None,
        )
        return {
            "preferred_mode": preferred_mode,
            "configured_runtime": executor_runtime,
            "executors": executors,
            "selected": selected,
        }

    def resolve_toutiao_login_target(workspace: Path, payload: dict | None = None) -> str | None:
        payload = payload if isinstance(payload, dict) else {}
        autonomy_runtime = load_autonomy_runtime(workspace)
        self_media_runtime = autonomy_runtime.get("self_media", {}) if isinstance(autonomy_runtime.get("self_media"), dict) else {}
        executor_runtime = self_media_runtime.get("executor", {}) if isinstance(self_media_runtime.get("executor"), dict) else {}
        target = str(
            payload.get("login_target_url")
            or executor_runtime.get("login_target_url")
            or os.getenv("EVO_TOUTIAO_LOGIN_TARGET_URL")
            or ""
        ).strip()
        return target or None

    def resolve_toutiao_executor(workspace: Path, payload: dict | None = None) -> dict:
        payload = payload if isinstance(payload, dict) else {}
        registry = describe_toutiao_executor_registry(workspace, payload)
        selected = registry.get("selected") if isinstance(registry.get("selected"), dict) else None
        if selected is None:
            return {
                "name": str(payload.get("executor_name") or "toutiao_executor"),
                "key": None,
                "adapter": "unavailable",
                "source": "unavailable",
                "available": False,
                "preferred_mode": registry.get("preferred_mode"),
            }
        executor_dir = Path(str(selected.get("root_dir") or ""))
        return {
            "name": str(payload.get("executor_name") or "toutiao_executor"),
            "key": selected.get("key"),
            "label": selected.get("label"),
            "adapter": selected.get("adapter"),
            "source": selected.get("source"),
            "available": True,
            "root_dir": str(executor_dir),
            "preferred_mode": registry.get("preferred_mode"),
        }

    def resolve_toutiao_executor_dir(workspace: Path) -> Path | None:
        executor = resolve_toutiao_executor(workspace)
        root_dir = str(executor.get("root_dir") or "").strip()
        return Path(root_dir) if root_dir else None

    def execute_toutiao_executor_command(
        workspace: Path,
        *,
        payload: dict | None = None,
        args: list[str],
        timeout: int = 45,
    ) -> dict:
        def _parse_command_output(stdout: str) -> dict | list | None:
            text = str(stdout or "").strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except Exception:
                pass
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for line in reversed(lines):
                try:
                    return json.loads(line)
                except Exception:
                    continue
            return None

        def _consume_option(option_args: list[str], name: str) -> str | None:
            if name in option_args:
                index = option_args.index(name)
                if index + 1 < len(option_args):
                    return option_args[index + 1]
            return None

        def _strip_legacy_script_prefix(raw_args: list[str]) -> list[str]:
            if not raw_args:
                return []
            args_local = list(raw_args)
            if args_local and args_local[0] == "scripts/cli.py":
                args_local = args_local[1:]
            return args_local

        executor = resolve_toutiao_executor(workspace, payload)
        root_dir = str(executor.get("root_dir") or "").strip()
        if not executor.get("available") or not root_dir:
            return {
                "ok": False,
                "message": "toutiao executor not found",
                "stdout": "",
                "stderr": "",
                "code": -1,
                "executor": executor,
            }
        executor_dir = Path(root_dir)
        adapter = str(executor.get("adapter") or "").strip().lower()
        command = ["python3", *args]
        command_cwd = executor_dir
        if adapter == "evo_local":
            normalized_args = _strip_legacy_script_prefix(args)
            cli_entry = executor_dir / "scripts" / "cli.py"
            if cli_entry.is_file():
                command = ["python3", str(cli_entry), *normalized_args]
        try:
            completed = subprocess.run(
                command,
                cwd=str(command_cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = completed.stdout or ""
            parsed = _parse_command_output(stdout)
            return {
                "ok": completed.returncode == 0,
                "message": "ok" if completed.returncode == 0 else "command_failed",
                "stdout": stdout,
                "stderr": completed.stderr or "",
                "code": completed.returncode,
                "parsed": parsed,
                "executor": executor,
                "ops_dir": str(command_cwd),
                "command": command,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "message": "timeout",
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "code": -2,
                "parsed": None,
                "executor": executor,
                "ops_dir": str(command_cwd),
                "command": command,
            }
        except Exception as exc:
            return {
                "ok": False,
                "message": str(exc),
                "stdout": "",
                "stderr": "",
                "code": -3,
                "parsed": None,
                "executor": executor,
                "ops_dir": str(command_cwd),
                "command": command,
            }

    def run_toutiao_executor_cli(
        workspace: Path,
        args: list[str],
        timeout: int = 45,
        payload: dict | None = None,
    ) -> dict:
        return execute_toutiao_executor_command(
            workspace,
            payload=payload,
            args=args,
            timeout=timeout,
        )

    def probe_toutiao_connector(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        command_result = execute_toutiao_executor_command(
            workspace,
            payload=payload,
            args=["scripts/cli.py", "account", "status", "--account", account],
            timeout=45,
        )
        if not command_result.get("ok"):
            stderr = str(command_result.get("stderr") or "").lower()
            if "not logged in" in stderr or "login" in stderr:
                return {
                    "validation_outcome": "auth_required",
                    "message": "头条账号未登录，需要先完成登录态",
                    "command_result": command_result,
                }
            if "no such file" in stderr or "not found" in stderr:
                return {
                    "validation_outcome": "connector_missing",
                    "message": "toutiao executor/cli missing",
                    "command_result": command_result,
                }
            return {
                "validation_outcome": "failed",
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "connector probe failed", 160),
                "command_result": command_result,
            }

        status_payload = command_result.get("parsed")
        if not isinstance(status_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                status_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                status_payload = {"raw": stdout.strip()}
        logged_in = bool(status_payload.get("logged_in")) if isinstance(status_payload, dict) else False
        return {
            "validation_outcome": "passed" if logged_in else "auth_required",
            "message": "执行器可用且账号已登录" if logged_in else "执行器可用，但账号还未登录",
            "command_result": command_result,
            "account_status": status_payload,
            "probe_result": status_payload,
            "executor": command_result.get("executor"),
        }

    def run_toutiao_analytics(workspace: Path, payload: dict) -> dict:
        analytics_type = str(payload.get("analytics_type") or "fans").strip().lower()
        account = str(payload.get("account_id") or "default")
        args = ["scripts/cli.py", "analytics", analytics_type, "--account", account, "--json"]
        if payload.get("content_type"):
            args.extend(["--content-type", str(payload["content_type"])])
        if payload.get("detail_content_type"):
            args.extend(["--detail-content-type", str(payload["detail_content_type"])])
        if payload.get("content_id"):
            args.extend(["--content-id", str(payload["content_id"])])
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=60)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "analytics failed", 180),
                "command_result": command_result,
                "analytics_type": analytics_type,
            }
        payload_json = command_result.get("parsed")
        if not isinstance(payload_json, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                payload_json = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                payload_json = {"raw": stdout.strip()}
        return {
            "ok": True,
            "analytics_type": analytics_type,
            "result": payload_json,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def load_recent_toutiao_automation_experiences(workspace: Path, tenant_id: str, limit: int = 12) -> list:
        store = ExperienceStore(workspace, tenant_id)
        items = store.load_by_task("self_media", "automation_operation", limit=limit)
        if not items:
            items = store.load_by_domain("self_media", limit=limit)
        return items[:limit]

    def extract_feedback_entries_from_result(result: dict) -> list[dict]:
        if not isinstance(result, dict):
            return []
        feedback = result.get("feedback_entries", [])
        if isinstance(feedback, list):
            return [item for item in feedback if isinstance(item, dict)]
        collect = result.get("collect_result", {}) if isinstance(result.get("collect_result"), dict) else {}
        entries = collect.get("entries", [])
        if isinstance(entries, list):
            return [item for item in entries if isinstance(item, dict)]
        return []

    def safe_percent_value(value) -> float:
        try:
            return round(float(value or 0.0), 2)
        except (TypeError, ValueError):
            return 0.0

    def pick_top_distribution_item(items: list[dict] | None, *, percent_key: str = "percent") -> dict | None:
        if not isinstance(items, list):
            return None
        normalized = [item for item in items if isinstance(item, dict)]
        if not normalized:
            return None
        return max(normalized, key=lambda item: safe_percent_value(item.get(percent_key)))

    def top_region_entries(metrics: dict, limit: int = 3) -> list[dict]:
        if not isinstance(metrics, dict):
            return []
        regions = metrics.get("top_regions", [])
        if not isinstance(regions, list):
            return []
        normalized = [item for item in regions if isinstance(item, dict)]
        normalized.sort(key=lambda item: safe_percent_value(item.get("percent")), reverse=True)
        return normalized[:limit]

    def run_toutiao_comment_list(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        max_comments = int(payload.get("max_comments") or 8)
        args = ["scripts/cli.py", "comment", "list", "--account", account, "--limit", str(max_comments), "--json"]
        if payload.get("topic"):
            args.extend(["--topic", str(payload["topic"])])
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=90)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "comment list failed", 180),
                "command_result": command_result,
                "entries": [],
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        entries = result_payload.get("entries", []) if isinstance(result_payload, dict) else []
        return {
            "ok": True,
            "message": "ok",
            "entries": entries if isinstance(entries, list) else [],
            "raw_result": result_payload,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def run_toutiao_comment_reply(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        comment_id = str(payload.get("comment_id") or "")
        content = str(payload.get("content") or "").strip()
        if not comment_id or not content:
            return {
                "ok": False,
                "message": "comment_id/content required",
                "command_result": None,
            }
        args = [
            "scripts/cli.py", "comment", "reply",
            "--account", account,
            "--comment-id", comment_id,
            "--content", content,
            "--json",
        ]
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=90)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "comment reply failed", 180),
                "command_result": command_result,
            }
        reply_payload = command_result.get("parsed")
        if not isinstance(reply_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                reply_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                reply_payload = {"raw": stdout.strip()}
        return {
            "ok": True,
            "message": "ok",
            "result": reply_payload,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def get_toutiao_account_identity(workspace: Path, account: str) -> dict:
        def _meta_path_for_executor(executor_payload: dict, account_id: str) -> Path | None:
            adapter = str(executor_payload.get("adapter") or "").strip().lower()
            root_dir = str(executor_payload.get("root_dir") or "").strip()
            if adapter != "evo_local" or not root_dir:
                return None
            safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(account_id or "default"))
            return Path(root_dir) / "data" / "accounts" / f"{safe}.json"
            return None

        def _load_saved_account_meta(account_id: str) -> dict:
            executor = resolve_toutiao_executor(workspace, {"account_id": account_id})
            meta_path = _meta_path_for_executor(executor, account_id)
            if meta_path is None:
                return {}
            if not meta_path.is_file():
                return {}
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
            return payload if isinstance(payload, dict) else {}

        def _write_saved_account_meta(account_id: str, patch: dict | None = None, *, clear_session: bool = False) -> dict:
            patch = patch if isinstance(patch, dict) else {}
            executor = resolve_toutiao_executor(workspace, {"account_id": account_id})
            meta_path = _meta_path_for_executor(executor, account_id)
            if meta_path is None:
                return {}
            current = _load_saved_account_meta(account_id)
            merged = {
                **current,
                **{key: value for key, value in patch.items() if value is not None},
            }
            if clear_session:
                merged["logged_in"] = False
                merged["login_status"] = "logged_out"
                merged["lastLogout"] = datetime.now().isoformat()
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return merged

        saved_meta = _load_saved_account_meta(account)
        command_result = execute_toutiao_executor_command(
            workspace,
            payload={"account_id": account},
            args=["scripts/cli.py", "account", "status", "--account", str(account or "default"), "--json"],
            timeout=45,
        )
        if not command_result.get("ok"):
            return {
                "account_id": account,
                "display_name": (
                    saved_meta.get("display_name")
                    or saved_meta.get("username")
                    or saved_meta.get("account")
                ),
                "logged_in": False,
                "profile": saved_meta or None,
                "command_result": command_result,
                "executor": command_result.get("executor"),
            }
        payload = command_result.get("parsed")
        if not isinstance(payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                payload = {"raw": stdout.strip()}
        merged_profile = {
            **saved_meta,
            **(payload if isinstance(payload, dict) else {}),
        }
        return {
            "account_id": account,
            "display_name": (
                merged_profile.get("display_name")
                or merged_profile.get("username")
                or merged_profile.get("account")
            ) if isinstance(merged_profile, dict) else None,
            "logged_in": bool(merged_profile.get("logged_in")) if isinstance(merged_profile, dict) else False,
            "profile": merged_profile,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def list_toutiao_accounts(workspace: Path, payload: dict | None = None) -> dict:
        command_result = execute_toutiao_executor_command(
            workspace,
            payload=payload,
            args=["scripts/cli.py", "account", "list", "--json"],
            timeout=45,
        )
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "account list failed", 180),
                "items": [],
                "command_result": command_result,
            }
        payload_json = command_result.get("parsed")
        if not isinstance(payload_json, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                payload_json = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                payload_json = {"raw": stdout.strip()}
        items = payload_json.get("items", []) if isinstance(payload_json, dict) else []
        if (not items) and isinstance(payload_json.get("accounts"), list):
            items = [
                {
                    "account_id": item.get("account") or item.get("account_id"),
                    "display_name": item.get("username") or item.get("display_name") or item.get("account"),
                    "logged_in": bool(item.get("has_session")),
                    **item,
                }
                for item in payload_json.get("accounts", [])
                if isinstance(item, dict)
            ]
        return {
            "ok": True,
            "message": "ok",
            "items": items if isinstance(items, list) else [],
            "total": (
                int(payload_json.get("total") or 0)
                if isinstance(payload_json, dict) and payload_json.get("total") is not None
                else len(items if isinstance(items, list) else [])
            ),
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def begin_toutiao_account_login(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        display_name = str(payload.get("display_name") or "").strip()
        login_target_url = resolve_toutiao_login_target(workspace, payload)
        args = ["scripts/cli.py", "account", "begin-login", "--account", account, "--json"]
        if display_name:
            args.extend(["--display-name", display_name])
        if login_target_url:
            args.extend(["--login-target-url", login_target_url])
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=45)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "begin login failed", 180),
                "command_result": command_result,
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        return {
            "ok": True,
            "message": "已创建本地登录占位会话",
            "result": result_payload,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def launch_toutiao_account_login(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        session_id = str(payload.get("session_id") or "").strip()
        login_target_url = resolve_toutiao_login_target(workspace, payload)
        args = ["scripts/cli.py", "account", "launch-login", "--account", account, "--json"]
        if session_id:
            args.extend(["--session-id", session_id])
        if login_target_url:
            args.extend(["--login-target-url", login_target_url])
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=45)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "launch login failed", 180),
                "command_result": command_result,
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        return {
            "ok": True,
            "message": "已记录登录目标发起动作",
            "result": result_payload,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def get_toutiao_login_session(workspace: Path, payload: dict) -> dict:
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            return {
                "ok": False,
                "message": "session_id required",
                "command_result": None,
            }
        command_result = execute_toutiao_executor_command(
            workspace,
            payload=payload,
            args=["scripts/cli.py", "account", "session-status", "--session-id", session_id, "--json"],
            timeout=45,
        )
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "session status failed", 180),
                "command_result": command_result,
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        return {
            "ok": True,
            "message": "ok",
            "result": result_payload,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def list_toutiao_login_sessions(workspace: Path, payload: dict | None = None) -> dict:
        payload = payload if isinstance(payload, dict) else {}
        account = str(payload.get("account_id") or "").strip()
        args = ["scripts/cli.py", "account", "sessions", "--json"]
        if account:
            args.extend(["--account", account])
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=45)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "session list failed", 180),
                "items": [],
                "command_result": command_result,
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        items = result_payload.get("items", []) if isinstance(result_payload, dict) else []
        return {
            "ok": True,
            "message": "ok",
            "items": items if isinstance(items, list) else [],
            "total": int(result_payload.get("total") or 0) if isinstance(result_payload, dict) else 0,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def confirm_toutiao_account_login(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        display_name = str(payload.get("display_name") or "").strip()
        profile_url = str(payload.get("profile_url") or "").strip()
        executor = resolve_toutiao_executor(workspace, payload)
        args = ["scripts/cli.py", "account", "confirm-login", "--account", account, "--json"]
        if display_name:
            args.extend(["--display-name", display_name])
        if profile_url:
            args.extend(["--profile-url", profile_url])
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=45)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "confirm login failed", 180),
                "command_result": command_result,
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        return {
            "ok": True,
            "message": "账号已标记为登录就绪",
            "result": result_payload,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def update_toutiao_account(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        args = ["scripts/cli.py", "account", "update", "--account", account, "--json"]
        if str(payload.get("display_name") or "").strip():
            args.extend(["--display-name", str(payload["display_name"]).strip()])
        if str(payload.get("profile_url") or "").strip():
            args.extend(["--profile-url", str(payload["profile_url"]).strip()])
        if str(payload.get("login_target_url") or "").strip():
            args.extend(["--login-target-url", str(payload["login_target_url"]).strip()])
        if str(payload.get("notes") or "").strip():
            args.extend(["--notes", str(payload["notes"]).strip()])
        if str(payload.get("login_status") or "").strip():
            args.extend(["--login-status", str(payload["login_status"]).strip()])
        if payload.get("logged_in") is True:
            args.extend(["--logged-in", "true"])
        elif payload.get("logged_in") is False:
            args.extend(["--logged-in", "false"])
        command_result = execute_toutiao_executor_command(workspace, payload=payload, args=args, timeout=45)
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "update account failed", 180),
                "command_result": command_result,
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        return {
            "ok": True,
            "message": "账号信息已更新",
            "result": result_payload,
            "command_result": command_result,
            "executor": command_result.get("executor"),
        }

    def logout_toutiao_account(workspace: Path, payload: dict) -> dict:
        account = str(payload.get("account_id") or "default")
        saved_before_logout = get_toutiao_account_identity(workspace, account)
        command_result = execute_toutiao_executor_command(
            workspace,
            payload=payload,
            args=["scripts/cli.py", "account", "logout", "--account", account, "--json"],
            timeout=45,
        )
        if not command_result.get("ok"):
            return {
                "ok": False,
                "message": trim_candidate_text(command_result.get("stderr") or command_result.get("message") or "logout failed", 180),
                "command_result": command_result,
            }
        result_payload = command_result.get("parsed")
        if not isinstance(result_payload, dict):
            stdout = str(command_result.get("stdout") or "")
            try:
                result_payload = json.loads(stdout) if stdout.strip() else {}
            except Exception:
                result_payload = {"raw": stdout.strip()}
        executor = command_result.get("executor") if isinstance(command_result.get("executor"), dict) else resolve_toutiao_executor(workspace, payload)
        restored = _write_saved_account_meta(
            account,
            {
                "display_name": saved_before_logout.get("display_name"),
                "username": (saved_before_logout.get("profile") or {}).get("username") if isinstance(saved_before_logout.get("profile"), dict) else None,
                "avatar": (saved_before_logout.get("profile") or {}).get("avatar") if isinstance(saved_before_logout.get("profile"), dict) else None,
                "userId": (saved_before_logout.get("profile") or {}).get("userId") if isinstance(saved_before_logout.get("profile"), dict) else None,
                "profileUrl": (saved_before_logout.get("profile") or {}).get("profileUrl") if isinstance(saved_before_logout.get("profile"), dict) else None,
            },
            clear_session=True,
        )
        result_payload = {
            **(result_payload if isinstance(result_payload, dict) else {}),
            "preserved_profile": restored,
        }
        return {
            "ok": True,
            "message": "账号已登出",
            "result": result_payload,
            "command_result": command_result,
            "executor": executor,
        }

    return {
        "describe_toutiao_executor_registry": describe_toutiao_executor_registry,
        "resolve_toutiao_executor": resolve_toutiao_executor,
        "resolve_toutiao_login_target": resolve_toutiao_login_target,
        "execute_toutiao_executor_command": execute_toutiao_executor_command,
        "resolve_toutiao_executor_dir": resolve_toutiao_executor_dir,
        "run_toutiao_executor_cli": run_toutiao_executor_cli,
        "probe_toutiao_connector": probe_toutiao_connector,
        "run_toutiao_analytics": run_toutiao_analytics,
        "load_recent_toutiao_automation_experiences": load_recent_toutiao_automation_experiences,
        "extract_feedback_entries_from_result": extract_feedback_entries_from_result,
        "safe_percent_value": safe_percent_value,
        "pick_top_distribution_item": pick_top_distribution_item,
        "top_region_entries": top_region_entries,
        "run_toutiao_comment_list": run_toutiao_comment_list,
        "run_toutiao_comment_reply": run_toutiao_comment_reply,
        "get_toutiao_account_identity": get_toutiao_account_identity,
        "list_toutiao_accounts": list_toutiao_accounts,
        "begin_toutiao_account_login": begin_toutiao_account_login,
        "launch_toutiao_account_login": launch_toutiao_account_login,
        "get_toutiao_login_session": get_toutiao_login_session,
        "list_toutiao_login_sessions": list_toutiao_login_sessions,
        "confirm_toutiao_account_login": confirm_toutiao_account_login,
        "update_toutiao_account": update_toutiao_account,
        "logout_toutiao_account": logout_toutiao_account,
    }
