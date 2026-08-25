"""
Session 运行时：本地会话持久化与请求用户解析。
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import Request


def load_sessions(session_file: Path | None) -> dict:
    if not session_file or not session_file.is_file():
        return {}
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def persist_sessions(session_file: Path | None, sessions: dict) -> None:
    if not session_file:
        return
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(
        json.dumps(sessions if isinstance(sessions, dict) else {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_session(session_file: Path | None, sessions: dict, user: dict) -> str:
    session_id = secrets.token_hex(24)
    sessions[session_id] = user
    persist_sessions(session_file, sessions)
    return session_id


def delete_session(session_file: Path | None, sessions: dict, session_id: str | None) -> None:
    if not session_id:
        return
    if session_id in sessions:
        del sessions[session_id]
        persist_sessions(session_file, sessions)


def get_session_user(sessions: dict, request: Request) -> dict | None:
    session_id = request.cookies.get("session")
    if not session_id:
        return None
    user = sessions.get(session_id)
    return user if isinstance(user, dict) else None


def get_user_gitee_token(sessions: dict, request: Request) -> str | None:
    user = get_session_user(sessions, request) or {}
    token = user.get("token")
    return token if isinstance(token, str) and token else None
