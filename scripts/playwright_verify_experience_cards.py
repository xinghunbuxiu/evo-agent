#!/usr/bin/env python3
"""实网补知识落盘成员 → Playwright 打开员工成长页核对经验卡。"""

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
OUT_DIR = ROOT / "test_output" / "playwright_experience"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    os.environ["EVO_M1_LIVE_MODEL"] = "1"
    os.environ["EVO_M1_KEEP_PROBE_MEMBER"] = "1"
    os.environ.pop("EVO_MODEL_PROVIDER_MOCK", None)

    from admin.m1_knowledge_learning_probe_runtime import run_knowledge_learning_probe
    from playwright.sync_api import sync_playwright

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report: dict = {"steps": [], "ok": False}

    reuse_member = str(os.getenv("EVO_PW_REUSE_MEMBER_ID") or "").strip()
    if reuse_member:
        member_id = reuse_member
        report["probe"] = {
            "ok": True,
            "kept": True,
            "member_id": member_id,
            "reused": True,
        }
    else:
        probe = run_knowledge_learning_probe(ROOT, tenant_id="default")
        report["probe"] = {
            "ok": probe.get("ok"),
            "kept": probe.get("kept"),
            "member_id": probe.get("member_id"),
            "mode": probe.get("mode"),
            "journal_card_ok": probe.get("journal_card_ok"),
            "live_model": probe.get("live_model"),
        }
        member_id = str(probe.get("member_id") or "").strip()
        if not probe.get("ok") or not probe.get("kept") or not member_id:
            report["detail"] = "probe_seed_failed"
            (OUT_DIR / f"{stamp}_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

    username = f"pw_exp_{stamp}"
    password = "pw-experience-verify-1"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})

        page.goto(f"{BASE}/register", wait_until="networkidle")
        page.get_by_placeholder("请输入用户名").fill(username)
        page.get_by_placeholder("请输入密码").fill(password)
        page.locator("form button[type='submit']").click()
        page.wait_for_timeout(800)

        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.get_by_placeholder("请输入用户名").fill(username)
        page.get_by_placeholder("请输入密码").fill(password)
        page.locator("form button[type='submit']").click()
        page.wait_for_url("**/dashboard**", timeout=20000)
        report["steps"].append({"login": page.url})

        target = f"{BASE}/organization/child/{member_id}/workspace?tab=growth"
        page.goto(target, wait_until="networkidle")
        page.wait_for_timeout(1500)
        # Sub-nav title is「成长状态」; click if deep-link tab was ignored
        growth_nav = page.get_by_text("成长状态", exact=True)
        if growth_nav.count():
            growth_nav.first.click()
            page.wait_for_timeout(800)
        page.screenshot(path=str(OUT_DIR / f"{stamp}_01_growth.png"), full_page=True)

        page.get_by_text("经验卡片").first.wait_for(timeout=15000)
        empty = page.get_by_text("还没有经验卡").count()
        has_source = page.get_by_text("knowledge_learning").count()
        # card body may show Chinese summary; require section + not empty state
        body = page.locator("body").inner_text()
        report["ui"] = {
            "url": page.url,
            "empty_hint": empty > 0,
            "knowledge_learning_badge": has_source > 0,
            "has_经验卡片": "经验卡片" in body,
            "body_snip": body[body.find("经验卡片") : body.find("经验卡片") + 400] if "经验卡片" in body else body[:400],
        }
        page.screenshot(path=str(OUT_DIR / f"{stamp}_02_cards.png"), full_page=True)
        browser.close()

    report["ok"] = (
        report["ui"]["has_经验卡片"]
        and not report["ui"]["empty_hint"]
        and (report["ui"]["knowledge_learning_badge"] or "补知识" in report["ui"]["body_snip"])
    )
    out = OUT_DIR / f"{stamp}_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
