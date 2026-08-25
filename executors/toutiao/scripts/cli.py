#!/usr/bin/env python3
"""
Evo 自己的最小头条执行器 CLI 骨架。

当前以本地状态文件和模拟返回为主，用于：
1. 固定住执行器协议
2. 让上层不再直接依赖第三方项目名
3. 后续逐步替换成真实浏览器/移动端执行器
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ACCOUNTS_DIR = DATA_DIR / "accounts"
SESSIONS_DIR = DATA_DIR / "sessions"
DRAFTS_DIR = DATA_DIR / "drafts"
COMMENTS_DIR = DATA_DIR / "comments"


def ensure_dirs() -> None:
    for path in (DATA_DIR, ACCOUNTS_DIR, SESSIONS_DIR, DRAFTS_DIR, COMMENTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def account_file(account: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in (account or "default"))
    return ACCOUNTS_DIR / f"{safe}.json"


def load_account(account: str) -> dict:
    ensure_dirs()
    path = account_file(account)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    payload = {
        "account_id": account or "default",
        "logged_in": False,
        "display_name": "Evo Toutiao",
        "profile_url": "",
        "notes": "set logged_in=true after real login integration",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def save_account(account: str, payload: dict) -> dict:
    ensure_dirs()
    normalized = {
        "account_id": str(payload.get("account_id") or account or "default"),
        "logged_in": bool(payload.get("logged_in", False)),
        "display_name": str(payload.get("display_name") or "Evo Toutiao"),
        "profile_url": str(payload.get("profile_url") or ""),
        "notes": str(payload.get("notes") or ""),
        "login_target_url": str(payload.get("login_target_url") or ""),
        "login_session_id": str(payload.get("login_session_id") or "") or None,
        "login_status": str(payload.get("login_status") or ("ready" if payload.get("logged_in") else "pending")),
        "updated_at": str(payload.get("updated_at") or datetime.now().isoformat()),
    }
    account_file(account).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def session_file(session_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in (session_id or "session"))
    return SESSIONS_DIR / f"{safe}.json"


def load_session(session_id: str) -> dict | None:
    ensure_dirs()
    path = session_file(session_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def save_session(session_id: str, payload: dict) -> dict:
    ensure_dirs()
    now = datetime.now().isoformat()
    current_events = payload.get("events", []) if isinstance(payload.get("events"), list) else []
    normalized = {
        "session_id": str(payload.get("session_id") or session_id),
        "account_id": str(payload.get("account_id") or "default"),
        "status": str(payload.get("status") or "awaiting_confirmation"),
        "display_name": str(payload.get("display_name") or "Evo Toutiao"),
        "profile_url": str(payload.get("profile_url") or ""),
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
        "notes": str(payload.get("notes") or ""),
        "login_target_url": str(payload.get("login_target_url") or ""),
        "events": current_events,
    }
    session_file(session_id).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def append_session_event(session_id: str, event_type: str, detail: str) -> dict | None:
    current = load_session(session_id)
    if not isinstance(current, dict):
        return None
    events = current.get("events", []) if isinstance(current.get("events"), list) else []
    events.append({
        "at": datetime.now().isoformat(),
        "type": event_type,
        "detail": detail,
    })
    current["events"] = events[-20:]
    return save_session(session_id, current)


def list_sessions(account: str | None = None) -> list[dict]:
    ensure_dirs()
    items: list[dict] = []
    for path in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if account and str(payload.get("account_id") or "") != str(account):
            continue
        items.append(payload)
    items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return items


def list_accounts() -> list[dict]:
    ensure_dirs()
    items: list[dict] = []
    for path in sorted(ACCOUNTS_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def begin_login(account: str, display_name: str = "", login_target_url: str = "") -> dict:
    current = load_account(account)
    session_id = f"login_{account}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    payload = {
        **current,
        "account_id": account,
        "logged_in": False,
        "display_name": display_name or current.get("display_name") or "Evo Toutiao",
        "login_session_id": session_id,
        "login_status": "awaiting_confirmation",
        "notes": "placeholder login session created by evo executor",
        "updated_at": datetime.now().isoformat(),
    }
    saved = save_account(account, payload)
    save_session(session_id, {
        "session_id": session_id,
        "account_id": account,
        "status": "awaiting_confirmation",
        "display_name": saved.get("display_name"),
        "profile_url": saved.get("profile_url") or "",
        "notes": "login session created by evo executor",
        "login_target_url": login_target_url or "",
        "events": [{
            "at": datetime.now().isoformat(),
            "type": "created",
            "detail": "login session created",
        }],
    })
    return {
        "account_id": account,
        "login_session_id": session_id,
        "login_status": "awaiting_confirmation",
        "display_name": saved.get("display_name"),
        "hint": "当前为本地登录占位会话，后续可替换成真实浏览器或设备登录流程",
        "login_target_url": login_target_url or "",
    }


def launch_login(account: str, login_target_url: str = "", session_id: str = "") -> dict:
    current = load_account(account)
    resolved_session_id = session_id or str(current.get("login_session_id") or "")
    if not resolved_session_id:
        created = begin_login(account, str(current.get("display_name") or ""), login_target_url)
        resolved_session_id = str(created.get("login_session_id") or "")
    session = load_session(resolved_session_id) or {}
    target_url = login_target_url or str(session.get("login_target_url") or "")

    browser_result = None
    try:
        from browser_backend import browser_mode, launch_login_with_playwright

        if browser_mode() == "playwright":
            browser_result = launch_login_with_playwright(
                account=account,
                login_target_url=target_url,
                session_id=resolved_session_id,
            )
            if isinstance(browser_result, dict) and browser_result.get("ok"):
                target_url = str(browser_result.get("login_target_url") or target_url)
                save_account(account, {
                    **current,
                    "account_id": account,
                    "login_session_id": resolved_session_id,
                    "login_target_url": target_url,
                    "login_status": "browser_opened",
                    "notes": f"playwright session: {browser_result.get('storage_state') or ''}",
                    "updated_at": datetime.now().isoformat(),
                })
    except Exception as exc:  # noqa: BLE001
        browser_result = {"ok": False, "backend": "playwright", "detail": str(exc)[:200], "fallback": "local"}

    status = "browser_opened" if isinstance(browser_result, dict) and browser_result.get("ok") else "browser_open_requested"
    payload = save_session(resolved_session_id, {
        **session,
        "session_id": resolved_session_id,
        "account_id": account,
        "status": status,
        "display_name": str(session.get("display_name") or current.get("display_name") or "Evo Toutiao"),
        "profile_url": str(session.get("profile_url") or current.get("profile_url") or ""),
        "notes": str(session.get("notes") or ""),
        "login_target_url": target_url,
        "events": [
            *(session.get("events", []) if isinstance(session.get("events"), list) else []),
            {
                "at": datetime.now().isoformat(),
                "type": "launch_requested",
                "detail": (
                    f"playwright:{browser_result.get('status')}"
                    if isinstance(browser_result, dict)
                    else f"login target requested: {target_url or 'not_configured'}"
                ),
            },
        ],
    })
    result = {
        "account_id": account,
        "session_id": resolved_session_id,
        "status": payload.get("status"),
        "login_target_url": target_url or None,
    }
    if isinstance(browser_result, dict):
        result["browser"] = browser_result
    return result


def confirm_login(account: str, display_name: str = "", profile_url: str = "") -> dict:
    current = load_account(account)
    session_id = str(current.get("login_session_id") or "")
    payload = {
        **current,
        "account_id": account,
        "logged_in": True,
        "display_name": display_name or current.get("display_name") or "Evo Toutiao",
        "profile_url": profile_url or current.get("profile_url") or "",
        "login_target_url": current.get("login_target_url") or "",
        "login_status": "ready",
        "updated_at": datetime.now().isoformat(),
    }
    saved = save_account(account, payload)
    if session_id:
        save_session(session_id, {
            **(load_session(session_id) or {}),
            "session_id": session_id,
            "account_id": account,
            "status": "confirmed",
            "display_name": saved.get("display_name"),
            "profile_url": saved.get("profile_url") or "",
            "notes": saved.get("notes") or "",
            "events": [
                *((load_session(session_id) or {}).get("events", []) if isinstance((load_session(session_id) or {}).get("events", []), list) else []),
                {
                    "at": datetime.now().isoformat(),
                    "type": "confirmed",
                    "detail": "account marked as logged in",
                },
            ],
        })
    return saved


def logout_account(account: str) -> dict:
    current = load_account(account)
    session_id = str(current.get("login_session_id") or "")
    payload = {
        **current,
        "account_id": account,
        "logged_in": False,
        "login_target_url": current.get("login_target_url") or "",
        "login_status": "logged_out",
        "updated_at": datetime.now().isoformat(),
    }
    saved = save_account(account, payload)
    if session_id:
        save_session(session_id, {
            **(load_session(session_id) or {}),
            "session_id": session_id,
            "account_id": account,
            "status": "logged_out",
            "display_name": saved.get("display_name"),
            "profile_url": saved.get("profile_url") or "",
            "notes": saved.get("notes") or "",
            "events": [
                *((load_session(session_id) or {}).get("events", []) if isinstance((load_session(session_id) or {}).get("events", []), list) else []),
                {
                    "at": datetime.now().isoformat(),
                    "type": "logged_out",
                    "detail": "account marked as logged out",
                },
            ],
        })
    return saved


def save_draft(account: str, content: str, topic: str, *, content_type: str = "weitoutiao", title: str = "") -> dict:
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_type = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in (content_type or "draft"))
    path = DRAFTS_DIR / f"{account}_{safe_type}_{timestamp}.json"
    article_path = None
    if safe_type == "article":
        article_path = DRAFTS_DIR / f"{account}_{safe_type}_{timestamp}.md"
        article_markdown = "\n\n".join([
            f"# {title or topic or 'Evo Article Draft'}",
            content.strip(),
        ]).strip() + "\n"
        article_path.write_text(article_markdown, encoding="utf-8")
    payload = {
        "action": "draft_saved",
        "account": account,
        "content_type": safe_type,
        "title": title,
        "topic": topic,
        "content": content,
        "saved_at": datetime.now().isoformat(),
        "draft_path": str(path),
        "article_path": str(article_path) if article_path else None,
        "url": None,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def analytics_payload(kind: str, account: str) -> dict:
    if kind == "works":
        return {
            "analytics_type": "works",
            "account": account,
            "metrics": {
                "昨日展现量": "1280",
                "昨日阅读(播放)量": "342",
                "昨日点赞量": "29",
                "昨日评论量": "7",
                "top_regions": [
                    {"name": "广东", "percent": 21.3},
                    {"name": "浙江", "percent": 16.8},
                    {"name": "江苏", "percent": 12.1},
                ],
            },
        }
    if kind == "income":
        return {
            "analytics_type": "income",
            "account": account,
            "data": [
                {
                    "data": [
                        {
                            "type": "can_withdraw_amount",
                            "total": 25.6,
                            "settle_info": {
                                "settle_detail": {
                                    "article": 13.2,
                                    "micro_post": 7.1,
                                    "qa": 5.3,
                                }
                            },
                        },
                        {
                            "type": "total_income",
                            "total": 39.8,
                        },
                    ]
                }
            ],
        }
    return {
        "analytics_type": "fans",
        "account": account,
        "metrics": {
            "昨日活跃粉丝数": "218",
            "昨日粉丝总数": "1542",
            "昨日粉丝变化数": "18",
            "top_regions": [
                {"name": "广东", "percent": 24.5},
                {"name": "河南", "percent": 13.2},
                {"name": "山东", "percent": 10.4},
            ],
        },
        "distributions": {
            "age": [
                {"label": "31-40", "percent": 32.5},
                {"label": "24-30", "percent": 28.1},
            ],
            "gender": [
                {"label": "男性", "percent": 63.4},
                {"label": "女性", "percent": 36.6},
            ],
            "devicePrice": [
                {"label": "2000~2999", "percent": 27.2},
                {"label": "1000~1999", "percent": 19.8},
            ],
            "fansViewedWorks": [
                {"title": "自动化到底能不能真正带来收入"},
                {"title": "从 0 到 1 做自媒体执行器"},
                {"title": "头条运营的复盘到底怎么做"},
            ],
        },
    }


def comment_entries(limit: int, topic: str) -> list[dict]:
    base = [
        {"comment_id": "cmt_001", "username": "用户甲", "content": "这个思路挺实在", "topic": topic or "自动化运营"},
        {"comment_id": "cmt_002", "username": "用户乙", "content": "想看你后面怎么执行", "topic": topic or "自动化运营"},
        {"comment_id": "cmt_003", "username": "用户丙", "content": "这个方向值得继续做", "topic": topic or "自动化运营"},
    ]
    return base[: max(1, limit)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="group", required=True)

    account = sub.add_parser("account")
    account_sub = account.add_subparsers(dest="action", required=True)
    account_status = account_sub.add_parser("status")
    account_status.add_argument("--account", default="default")
    account_status.add_argument("--json", action="store_true")
    account_list = account_sub.add_parser("list")
    account_list.add_argument("--json", action="store_true")
    account_begin = account_sub.add_parser("begin-login")
    account_begin.add_argument("--account", default="default")
    account_begin.add_argument("--display-name", default="")
    account_begin.add_argument("--login-target-url", default="")
    account_begin.add_argument("--json", action="store_true")
    account_launch = account_sub.add_parser("launch-login")
    account_launch.add_argument("--account", default="default")
    account_launch.add_argument("--session-id", default="")
    account_launch.add_argument("--login-target-url", default="")
    account_launch.add_argument("--json", action="store_true")
    account_confirm = account_sub.add_parser("confirm-login")
    account_confirm.add_argument("--account", default="default")
    account_confirm.add_argument("--display-name", default="")
    account_confirm.add_argument("--profile-url", default="")
    account_confirm.add_argument("--json", action="store_true")
    account_update = account_sub.add_parser("update")
    account_update.add_argument("--account", default="default")
    account_update.add_argument("--display-name", default="")
    account_update.add_argument("--profile-url", default="")
    account_update.add_argument("--notes", default="")
    account_update.add_argument("--login-status", default="")
    account_update.add_argument("--login-target-url", default="")
    account_update.add_argument("--logged-in", choices=["true", "false"], default="")
    account_update.add_argument("--json", action="store_true")
    account_logout = account_sub.add_parser("logout")
    account_logout.add_argument("--account", default="default")
    account_logout.add_argument("--json", action="store_true")
    account_session_status = account_sub.add_parser("session-status")
    account_session_status.add_argument("--session-id", required=True)
    account_session_status.add_argument("--json", action="store_true")
    account_sessions = account_sub.add_parser("sessions")
    account_sessions.add_argument("--account", default="")
    account_sessions.add_argument("--json", action="store_true")

    publish = sub.add_parser("publish")
    publish.add_argument("content_type")
    publish.add_argument("--account", default="default")
    publish.add_argument("--content", required=True)
    publish.add_argument("--topic", default="")
    publish.add_argument("--title", default="")
    publish.add_argument("--draft", action="store_true")
    publish.add_argument("--headless", action="store_true")

    analytics = sub.add_parser("analytics")
    analytics.add_argument("analytics_type")
    analytics.add_argument("--account", default="default")
    analytics.add_argument("--json", action="store_true")
    analytics.add_argument("--content-type", default="")
    analytics.add_argument("--detail-content-type", default="")
    analytics.add_argument("--content-id", default="")

    comment = sub.add_parser("comment")
    comment_sub = comment.add_subparsers(dest="action", required=True)
    comment_list = comment_sub.add_parser("list")
    comment_list.add_argument("--account", default="default")
    comment_list.add_argument("--limit", type=int, default=8)
    comment_list.add_argument("--topic", default="")
    comment_list.add_argument("--json", action="store_true")

    comment_reply = comment_sub.add_parser("reply")
    comment_reply.add_argument("--account", default="default")
    comment_reply.add_argument("--comment-id", required=True)
    comment_reply.add_argument("--content", required=True)
    comment_reply.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    ensure_dirs()

    if args.group == "account" and args.action == "status":
        payload = load_account(args.account)
        try:
            from browser_backend import browser_mode, probe_account_with_playwright

            if browser_mode() == "playwright":
                probe = probe_account_with_playwright(
                    account=args.account,
                    login_target_url=str(payload.get("login_target_url") or ""),
                )
                if isinstance(probe, dict) and probe.get("ok"):
                    if probe.get("logged_in") and not payload.get("logged_in"):
                        payload = save_account(args.account, {
                            **payload,
                            "logged_in": True,
                            "login_status": "ready",
                            "notes": str(probe.get("notes") or payload.get("notes") or ""),
                            "updated_at": datetime.now().isoformat(),
                        })
                    payload = {
                        **payload,
                        "browser": {
                            "backend": probe.get("backend"),
                            "status": probe.get("status"),
                            "cookie_count": probe.get("cookie_count"),
                            "storage_state": probe.get("storage_state"),
                        },
                    }
        except Exception as exc:  # noqa: BLE001
            payload = {**payload, "browser": {"backend": "playwright", "detail": str(exc)[:160]}}
        print(json.dumps(payload, ensure_ascii=False))
        if not payload.get("logged_in"):
            print("not logged in", file=sys.stderr)
            return 1
        return 0

    if args.group == "account" and args.action == "list":
        items = list_accounts()
        print(json.dumps({
            "items": items,
            "total": len(items),
        }, ensure_ascii=False))
        return 0

    if args.group == "account" and args.action == "session-status":
        payload = load_session(args.session_id)
        if not isinstance(payload, dict):
            print("session not found", file=sys.stderr)
            return 1
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args.group == "account" and args.action == "sessions":
        items = list_sessions(args.account or None)
        print(json.dumps({
            "items": items,
            "total": len(items),
        }, ensure_ascii=False))
        return 0

    if args.group == "account" and args.action == "begin-login":
        print(json.dumps(begin_login(args.account, args.display_name, args.login_target_url), ensure_ascii=False))
        return 0

    if args.group == "account" and args.action == "launch-login":
        print(json.dumps(launch_login(args.account, args.login_target_url, args.session_id), ensure_ascii=False))
        return 0

    if args.group == "account" and args.action == "confirm-login":
        print(json.dumps(confirm_login(args.account, args.display_name, args.profile_url), ensure_ascii=False))
        return 0

    if args.group == "account" and args.action == "update":
        current = load_account(args.account)
        logged_in = current.get("logged_in")
        if args.logged_in == "true":
            logged_in = True
        elif args.logged_in == "false":
            logged_in = False
        saved = save_account(args.account, {
            **current,
            "account_id": args.account,
            "display_name": args.display_name or current.get("display_name") or "Evo Toutiao",
            "profile_url": args.profile_url or current.get("profile_url") or "",
            "notes": args.notes or current.get("notes") or "",
            "login_target_url": args.login_target_url or current.get("login_target_url") or "",
            "login_status": args.login_status or current.get("login_status") or ("ready" if logged_in else "pending"),
            "logged_in": logged_in,
            "updated_at": datetime.now().isoformat(),
        })
        session_id = str(saved.get("login_session_id") or "")
        if session_id:
            append_session_event(session_id, "updated", "account profile updated")
        print(json.dumps(saved, ensure_ascii=False))
        return 0

    if args.group == "account" and args.action == "logout":
        print(json.dumps(logout_account(args.account), ensure_ascii=False))
        return 0

    if args.group == "publish":
        payload = load_account(args.account)
        if not payload.get("logged_in") and not args.draft:
            print("not logged in", file=sys.stderr)
            return 1
        result = save_draft(
            args.account,
            args.content,
            args.topic,
            content_type=args.content_type,
            title=args.title,
        )
        try:
            from browser_backend import browser_mode, publish_draft_with_playwright

            if browser_mode() == "playwright":
                browser_publish = publish_draft_with_playwright(
                    account=args.account,
                    content=args.content,
                    topic=args.topic,
                    title=args.title,
                    content_type=args.content_type,
                    headless=bool(args.headless),
                )
                if isinstance(browser_publish, dict):
                    result = {**result, "browser": browser_publish}
        except Exception as exc:  # noqa: BLE001
            result = {**result, "browser": {"ok": False, "detail": str(exc)[:160], "fallback": "local"}}
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.group == "analytics":
        payload = load_account(args.account)
        if not payload.get("logged_in"):
            print("not logged in", file=sys.stderr)
            return 1
        print(json.dumps(analytics_payload(args.analytics_type, args.account), ensure_ascii=False))
        return 0

    if args.group == "comment" and args.action == "list":
        payload = load_account(args.account)
        if not payload.get("logged_in"):
            print("not logged in", file=sys.stderr)
            return 1
        result = {
            "entries": comment_entries(args.limit, args.topic),
            "generated_at": datetime.now().isoformat(),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.group == "comment" and args.action == "reply":
        payload = load_account(args.account)
        if not payload.get("logged_in"):
            print("not logged in", file=sys.stderr)
            return 1
        result = {
            "comment_id": args.comment_id,
            "content": args.content,
            "status": "replied",
            "replied_at": datetime.now().isoformat(),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
