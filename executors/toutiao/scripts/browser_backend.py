"""
可选 Playwright 浏览器后端（执行器层）。

默认不启用；`EVO_CHANNEL_BROWSER=playwright` 时使用真实浏览器。
未安装 / 失败时回退本地 stub，不把品牌逻辑泄漏到 intake 核心。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BROWSER_DIR = DATA_DIR / "browser"
STATES_DIR = BROWSER_DIR / "states"
SHOTS_DIR = BROWSER_DIR / "screenshots"


def browser_mode() -> str:
    raw = str(
        os.getenv("EVO_CHANNEL_BROWSER")
        or os.getenv("EVO_TOUTIAO_BROWSER")
        or "local"
    ).strip().lower()
    if raw in {"playwright", "pw", "browser"}:
        return "playwright"
    return "local"


def playwright_available() -> tuple[bool, str | None]:
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, f"playwright_import_failed:{exc}"
    return True, None


def _ensure_browser_dirs() -> None:
    for path in (BROWSER_DIR, STATES_DIR, SHOTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def state_path(account: str) -> Path:
    _ensure_browser_dirs()
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in (account or "default"))
    return STATES_DIR / f"{safe}.json"


def resolve_login_target(login_target_url: str = "") -> str:
    return str(
        login_target_url
        or os.getenv("EVO_CHANNEL_LOGIN_URL")
        or os.getenv("EVO_TOUTIAO_LOGIN_TARGET_URL")
        or ""
    ).strip()


def launch_login_with_playwright(
    *,
    account: str,
    login_target_url: str = "",
    session_id: str = "",
    headless: bool | None = None,
    wait_ms: int = 1500,
) -> dict[str, Any]:
    ok, reason = playwright_available()
    if not ok:
        return {
            "ok": False,
            "backend": "playwright",
            "status": "unavailable",
            "detail": reason,
            "fallback": "local",
        }

    target = resolve_login_target(login_target_url)
    if not target:
        return {
            "ok": False,
            "backend": "playwright",
            "status": "missing_login_url",
            "detail": "set EVO_CHANNEL_LOGIN_URL or pass login_target_url",
            "fallback": "local",
        }

    if headless is None:
        headless = str(os.getenv("EVO_CHANNEL_BROWSER_HEADLESS") or "").strip().lower() in {
            "1", "true", "yes",
        }

    from playwright.sync_api import sync_playwright

    _ensure_browser_dirs()
    storage = state_path(account)
    shot = SHOTS_DIR / f"{account}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    started = datetime.now().isoformat()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context_kwargs: dict[str, Any] = {"viewport": {"width": 1280, "height": 900}}
            if storage.is_file():
                context_kwargs["storage_state"] = str(storage)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(target, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(max(200, int(wait_ms)))
            try:
                page.screenshot(path=str(shot), full_page=False)
            except Exception:
                shot = None
            context.storage_state(path=str(storage))
            title = ""
            try:
                title = page.title()
            except Exception:
                title = ""
            # Non-headless: leave a short window for manual login if needed
            if not headless:
                page.wait_for_timeout(int(os.getenv("EVO_CHANNEL_LOGIN_HOLD_MS") or "8000"))
                context.storage_state(path=str(storage))
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "backend": "playwright",
            "status": "error",
            "detail": str(exc)[:300],
            "fallback": "local",
            "login_target_url": target,
            "session_id": session_id or None,
        }

    cookie_count = 0
    try:
        payload = json.loads(storage.read_text(encoding="utf-8"))
        cookies = payload.get("cookies") if isinstance(payload, dict) else []
        cookie_count = len(cookies) if isinstance(cookies, list) else 0
    except Exception:
        cookie_count = 0

    return {
        "ok": True,
        "backend": "playwright",
        "status": "browser_opened",
        "account_id": account,
        "session_id": session_id or None,
        "login_target_url": target,
        "storage_state": str(storage),
        "screenshot": str(shot) if shot else None,
        "page_title": title,
        "cookie_count": cookie_count,
        "headless": bool(headless),
        "started_at": started,
        "finished_at": datetime.now().isoformat(),
        "hint": "若需人工扫码/登录，请将 EVO_CHANNEL_BROWSER_HEADLESS=0 并完成登录后再次 account status",
    }


def probe_account_with_playwright(*, account: str, login_target_url: str = "") -> dict[str, Any]:
    ok, reason = playwright_available()
    if not ok:
        return {
            "ok": False,
            "backend": "playwright",
            "status": "unavailable",
            "detail": reason,
            "fallback": "local",
        }

    storage = state_path(account)
    if not storage.is_file():
        return {
            "ok": True,
            "backend": "playwright",
            "logged_in": False,
            "status": "no_storage_state",
            "detail": "尚未发起 Playwright 登录或未保存会话",
            "storage_state": str(storage),
        }

    try:
        payload = json.loads(storage.read_text(encoding="utf-8"))
        cookies = payload.get("cookies") if isinstance(payload, dict) else []
        cookie_count = len(cookies) if isinstance(cookies, list) else 0
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "backend": "playwright",
            "logged_in": False,
            "status": "invalid_storage_state",
            "detail": str(exc)[:200],
            "fallback": "local",
        }

    # Heuristic: any persisted cookies ⇒ treat as session present
    logged_in = cookie_count > 0
    target = resolve_login_target(login_target_url)
    return {
        "ok": True,
        "backend": "playwright",
        "logged_in": logged_in,
        "status": "ready" if logged_in else "pending",
        "cookie_count": cookie_count,
        "storage_state": str(storage),
        "login_target_url": target or None,
        "notes": "session inferred from playwright storage_state cookies",
    }


def publish_draft_with_playwright(
    *,
    account: str,
    content: str,
    topic: str = "",
    title: str = "",
    content_type: str = "article",
    headless: bool = True,
) -> dict[str, Any]:
    """
    Best-effort: open editor URL if configured, dump content into a local artifact,
    and capture a screenshot. Full site automation varies by channel; keep local draft as source of truth.
    """
    ok, reason = playwright_available()
    if not ok:
        return {"ok": False, "backend": "playwright", "status": "unavailable", "detail": reason, "fallback": "local"}

    editor_url = str(
        os.getenv("EVO_CHANNEL_EDITOR_URL")
        or os.getenv("EVO_TOUTIAO_EDITOR_URL")
        or ""
    ).strip()
    if not editor_url:
        return {
            "ok": False,
            "backend": "playwright",
            "status": "missing_editor_url",
            "detail": "set EVO_CHANNEL_EDITOR_URL to enable browser-assisted publish",
            "fallback": "local",
        }

    from playwright.sync_api import sync_playwright

    _ensure_browser_dirs()
    storage = state_path(account)
    shot = SHOTS_DIR / f"publish_{account}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context_kwargs: dict[str, Any] = {}
            if storage.is_file():
                context_kwargs["storage_state"] = str(storage)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(editor_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)
            # Soft attempt: focus body and type (selectors vary by site)
            try:
                page.keyboard.type((title or topic or "")[:80])
                page.keyboard.press("Tab")
                page.keyboard.type((content or "")[:2000])
            except Exception:
                pass
            try:
                page.screenshot(path=str(shot), full_page=False)
            except Exception:
                shot = None
            context.storage_state(path=str(storage))
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "backend": "playwright",
            "status": "error",
            "detail": str(exc)[:300],
            "fallback": "local",
        }

    return {
        "ok": True,
        "backend": "playwright",
        "status": "browser_assisted",
        "account_id": account,
        "content_type": content_type,
        "editor_url": editor_url,
        "screenshot": str(shot) if shot else None,
        "storage_state": str(storage),
        "hint": "浏览器已打开编辑页并尝试填入内容；请人工确认发布，本地草稿仍会保存",
    }
