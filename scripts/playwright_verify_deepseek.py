#!/usr/bin/env python3
"""Playwright：登录 Admin → 公司制度页配置 DeepSeek → 真实 chat/completions 冒烟。"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BASE = os.getenv("EVO_ADMIN_BASE", "http://127.0.0.1:8000").rstrip("/")
API_KEY = (os.getenv("EVO_DEEPSEEK_API_KEY") or "").strip()
BASE_URL = (os.getenv("EVO_DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip()
MODEL = (os.getenv("EVO_DEEPSEEK_MODEL") or "deepseek-chat").strip()
ENDPOINT = (os.getenv("EVO_DEEPSEEK_ENDPOINT") or "/v1/chat/completions").strip()
OUT_DIR = ROOT / "test_output" / "playwright_deepseek"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def main() -> int:
    if not API_KEY:
        print("FAIL: set EVO_DEEPSEEK_API_KEY", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright
    from admin.model_provider_runtime import (
        _chat_completions_url,
        complete_chat,
        normalize_model_provider,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    username = f"pw_ds_{stamp}"
    password = "pw-deepseek-verify-1"
    report: dict = {
        "base": BASE,
        "username": username,
        "base_url": BASE_URL,
        "endpoint": ENDPOINT,
        "model": MODEL,
        "api_key_masked": _mask(API_KEY),
        "steps": [],
    }

    resolved = _chat_completions_url(BASE_URL)
    expected_suffix = ENDPOINT if ENDPOINT.startswith("/") else f"/{ENDPOINT}"
    report["resolved_chat_url"] = resolved
    report["endpoint_matches_ui"] = resolved.endswith(expected_suffix.lstrip("/")) or resolved.endswith(
        expected_suffix
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = context.new_page()

        # 1) register
        page.goto(f"{BASE}/register", wait_until="networkidle")
        page.get_by_placeholder("请输入用户名").fill(username)
        page.get_by_placeholder("请输入密码").fill(password)
        page.locator("form button[type='submit']").click()
        page.wait_for_timeout(1200)
        report["steps"].append({"register": page.url, "body_snip": page.locator("body").inner_text()[:240]})
        page.screenshot(path=str(OUT_DIR / f"{stamp}_01_register.png"), full_page=True)

        # 2) login
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.get_by_placeholder("请输入用户名").fill(username)
        page.get_by_placeholder("请输入密码").fill(password)
        page.locator("form button[type='submit']").click()
        page.wait_for_url("**/dashboard**", timeout=20000)
        report["steps"].append({"login_ok": page.url})
        page.screenshot(path=str(OUT_DIR / f"{stamp}_02_dashboard.png"), full_page=True)

        # 3) company policies
        page.goto(f"{BASE}/organization/parent/workspace?section=policies", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.get_by_text("自主学习模型（OpenAI 兼容）").wait_for(timeout=15000)
        page.screenshot(path=str(OUT_DIR / f"{stamp}_03_policies.png"), full_page=True)

        model_box = page.locator("div.rounded-xl.border.border-sky-100").filter(
            has_text="自主学习模型（OpenAI 兼容）"
        ).first
        enable = model_box.locator("label").filter(has_text="启用模型学习").locator("input[type='checkbox']")
        enable.evaluate(
            """el => {
              el.checked = true;
              el.dispatchEvent(new Event('change', { bubbles: true }));
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }"""
        )

        base_input = model_box.get_by_placeholder("https://api.deepseek.com")
        model_input = model_box.get_by_placeholder("deepseek-chat")
        key_input = model_box.get_by_placeholder("留空则保留原密钥")

        def _set_input(locator, value: str) -> None:
            locator.click()
            locator.fill("")
            locator.press_sequentially(value, delay=15)
            locator.dispatch_event("input")
            locator.dispatch_event("change")

        _set_input(base_input, BASE_URL)
        _set_input(model_input, MODEL)
        _set_input(key_input, API_KEY)

        page.screenshot(path=str(OUT_DIR / f"{stamp}_04_filled.png"), full_page=True)

        with page.expect_response(
            lambda r: "/external-learning-policy" in r.url and r.request.method == "PUT",
            timeout=20000,
        ) as resp_info:
            page.get_by_role("button", name="保存学习边界").click()
        put_resp = resp_info.value
        try:
            put_req = put_resp.request.post_data_json or {}
        except Exception:
            put_req = {}
        put_json = put_resp.json()
        report["steps"].append(
            {
                "save_status": put_resp.status,
                "put_model_provider": (put_req.get("model_provider") or {}),
                "response_model_provider": (
                    ((put_json.get("data") or {}).get("policy") or {}).get("model_provider") or {}
                ),
                "response_message": put_json.get("message"),
            }
        )
        # strip secrets from report
        for block_key in ("put_model_provider", "response_model_provider"):
            block = report["steps"][-1].get(block_key) or {}
            if isinstance(block, dict) and block.get("api_key"):
                block["api_key"] = _mask(str(block["api_key"]))
        page.get_by_text("学习边界已更新").or_(page.get_by_text("外部学习策略已更新")).first.wait_for(
            timeout=10000
        )
        page.screenshot(path=str(OUT_DIR / f"{stamp}_05_saved.png"), full_page=True)

        # 4) reload and assert configured badge / values
        page.goto(f"{BASE}/organization/parent/workspace?section=policies", wait_until="networkidle")
        page.wait_for_timeout(1500)
        model_box = page.locator("div.rounded-xl.border.border-sky-100").filter(
            has_text="自主学习模型（OpenAI 兼容）"
        ).first
        enable = model_box.locator("label").filter(has_text="启用模型学习").locator("input[type='checkbox']")
        base_input = model_box.get_by_placeholder("https://api.deepseek.com")
        model_input = model_box.get_by_placeholder("deepseek-chat")
        configured = model_box.get_by_text("已配置").count() > 0
        report["ui_after_reload"] = {
            "api_key_configured_badge": configured,
            "base_url": base_input.input_value(),
            "model": model_input.input_value(),
            "enabled": enable.is_checked(),
        }
        page.screenshot(path=str(OUT_DIR / f"{stamp}_06_reloaded.png"), full_page=True)

        # API confirm via cookie session
        cookies = {c["name"]: c["value"] for c in context.cookies()}
        browser.close()

    import urllib.request

    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req = urllib.request.Request(
        f"{BASE}/api/tenants/default/external-learning-policy",
        headers={"Cookie": cookie_header},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        api_policy = json.loads(resp.read().decode("utf-8"))
    mp = ((api_policy.get("data") or {}).get("policy") or {}).get("model_provider") or {}
    if mp.get("api_key"):
        mp = {**mp, "api_key": _mask(str(mp.get("api_key")))}
    report["api_policy_model_provider"] = mp

    # 5) live DeepSeek call (same resolution as runtime)
    provider = normalize_model_provider(
        {
            "enabled": True,
            "label": "deepseek",
            "base_url": BASE_URL,
            "api_key": API_KEY,
            "model": MODEL,
        }
    )
    chat = complete_chat(
        provider,
        messages=[
            {"role": "system", "content": "只回复一个词：pong"},
            {"role": "user", "content": "ping"},
        ],
        temperature=0,
        timeout_sec=60,
    )
    report["live_chat"] = {
        "status": chat.get("status"),
        "model": chat.get("model"),
        "detail": chat.get("detail"),
        "content_snip": str(chat.get("content") or "")[:200],
        "url": resolved,
    }

    api_mp = report.get("api_policy_model_provider") or {}
    put_mp = {}
    for step in report.get("steps") or []:
        if isinstance(step, dict) and "put_model_provider" in step:
            put_mp = step.get("put_model_provider") or {}
    ok = (
        bool(put_mp.get("enabled"))
        and put_mp.get("base_url") == BASE_URL
        and put_mp.get("model") == MODEL
        and bool(api_mp.get("enabled"))
        and api_mp.get("base_url") == BASE_URL
        and api_mp.get("model") == MODEL
        and bool(api_mp.get("api_key_configured"))
        and report["ui_after_reload"].get("base_url") == BASE_URL
        and report["ui_after_reload"].get("model") == MODEL
        and report["ui_after_reload"].get("enabled")
        and report["ui_after_reload"].get("api_key_configured_badge")
        and chat.get("status") == "completed"
        and bool(str(chat.get("content") or "").strip())
        and report.get("endpoint_matches_ui")
    )
    report["ok"] = bool(ok)
    report["finished_at"] = datetime.now().isoformat()

    out = OUT_DIR / f"{stamp}_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
