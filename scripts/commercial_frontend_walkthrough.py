#!/usr/bin/env python3
"""
商用线上身份：从 0 操作前端管理台，逐步记录问题（非 M1 探测脚本）。

输出：
  test_output/commercial_frontend_qa/<stamp>/report.md
  同目录截图

用法:
  cd evo-os
  .venv/bin/python scripts/commercial_frontend_walkthrough.py
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
OUT = ROOT / "test_output" / "commercial_frontend_qa"


def main() -> int:
    from playwright.sync_api import sync_playwright

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUT / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    issues: list[dict] = []
    steps: list[str] = []
    username = f"biz_{stamp[-6:]}"
    password = "BizPass2026!"

    def shot(page, name: str) -> None:
        page.screenshot(path=str(run_dir / f"{name}.png"), full_page=True)

    def note(step: str, ok: bool, detail: str = "", severity: str = "info") -> None:
        steps.append(f"{'OK' if ok else 'ISSUE'} · {step}: {detail}".strip())
        if not ok:
            issues.append({"step": step, "detail": detail, "severity": severity})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(25000)

        # 1) 打开登录页（未登录商用入口）
        page.goto(f"{BASE}/login", wait_until="networkidle")
        shot(page, "01_login")
        body = page.inner_text("body")
        if "🧬" in body or "DNA" in body:
            note("登录页品牌", False, "仍出现 DNA/emoji 品牌装饰", "high")
        else:
            note("登录页品牌", True, "无 DNA emoji")
        if "经营控制台" not in body and "Evo" not in body:
            note("登录页文案", False, "未看到经营控制台/Evo", "medium")
        else:
            note("登录页文案", True, "可见 Evo / 经营控制台")
        for bad in ("智脑 · 双环", "Mission 续跑", "消费环入口"):
            if bad in body:
                note("登录页 AI 味", False, f"残留文案: {bad}", "medium")

        # 2) 注册
        page.goto(f"{BASE}/register", wait_until="networkidle")
        page.get_by_placeholder("请输入用户名").fill(username)
        page.get_by_placeholder("请输入密码").fill(password)
        page.locator("form button[type='submit']").click()
        page.wait_for_timeout(1200)
        shot(page, "02_register")
        reg_text = page.inner_text("body")
        if "已存在" in reg_text:
            note("注册", False, f"用户名冲突: {username}", "high")
        else:
            note("注册", True, f"账号 {username}")

        # 3) 登录进入总览
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.get_by_placeholder("请输入用户名").fill(username)
        page.get_by_placeholder("请输入密码").fill(password)
        page.locator("form button[type='submit']").click()
        try:
            page.wait_for_url("**/dashboard**", timeout=20000)
            note("登录进总览", True, page.url)
        except Exception as exc:
            shot(page, "03_login_fail")
            note("登录进总览", False, str(exc), "high")
            browser.close()
            _write_report(run_dir, username, steps, issues)
            return 1

        page.wait_for_timeout(1500)
        shot(page, "03_dashboard")
        dash = page.inner_text("body")
        if "经营看板" not in dash and "公司总览" not in dash:
            note("总览标题", False, "未见经营看板/公司总览", "medium")
        else:
            note("总览标题", True, "经营向标题可见")
        for bad in ("商业智脑 · 双环总览", "🧬", "消费环 · 接单漏斗", "供给环 · 员工成长", "端到端主路径（商业）", "消费环 · 接入"):
            if bad in dash:
                note("总览 AI 味", False, f"残留: {bad}", "medium")
        if "m1_evolution" in dash.lower() or "M1 Evolution" in dash or "M1 Knowledge" in dash:
            note("租户脏数据", False, "新账号总览出现 M1 探针成员，商用环境未隔离", "high")
        else:
            note("租户脏数据", True, "总览未见 M1 探针成员")

        # 4) 工种配置
        page.goto(f"{BASE}/organization/parent/workspace?section=worktypes", wait_until="networkidle")
        page.wait_for_timeout(1200)
        shot(page, "04_worktypes")
        wt = page.inner_text("body")
        if "工种" not in wt:
            note("工种页", False, "页面未出现工种相关文案", "high")
        else:
            note("工种页", True, "已打开工种配置")
        # 尝试添加/启用：找常见按钮
        add_btn = page.get_by_role("button", name=re.compile(r"添加|新建|启用"))
        if add_btn.count() == 0:
            note("工种操作入口", False, "未见添加/新建/启用按钮（需人工确认是否空态设计）", "medium")
        else:
            note("工种操作入口", True, f"找到 {add_btn.count()} 个相关按钮")

        # 5) 育成师
        page.goto(
            f"{BASE}/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary",
            wait_until="networkidle",
        )
        page.wait_for_timeout(1500)
        shot(page, "05_trainer")
        tr = page.inner_text("body")
        if "育成" not in tr and "画像" not in tr and "建档" not in tr:
            note("育成页", False, "未见育成/画像/建档文案", "high")
        else:
            note("育成页", True, "育成工作台可打开")

        # 6) 接单台 — 正确填写必填标题后创建
        page.goto(f"{BASE}/organization/intake?section=create", wait_until="networkidle")
        page.wait_for_timeout(1200)
        shot(page, "06_intake")
        intake = page.inner_text("body")
        for bad in ("消费环 · 接单台", "创建并智脑分析", "智脑路由候选", "消费环 · 接入"):
            if bad in intake:
                note("接单 AI 味", False, f"残留: {bad}", "medium")
        title_ok = ("接单" in intake) or ("商业接单" in intake)
        note("接单页", title_ok, "接单台已打开" if title_ok else "接单文案缺失", "high" if not title_ok else "info")

        try:
            page.locator("input").filter(has=page.locator("xpath=ancestor::label[contains(., '任务标题')]")).first.fill(
                f"商用验收任务-{stamp}"
            )
        except Exception:
            # fallback: first visible text input in create section
            page.locator("section input").first.fill(f"商用验收任务-{stamp}")
        try:
            page.locator("textarea").first.fill("需要内容运营写一篇可发布草稿并交付，验收标准：可预览的正文文件。")
        except Exception:
            pass
        page.get_by_role("button", name=re.compile(r"创建并分析")).click()
        page.wait_for_timeout(2500)
        shot(page, "07_intake_after_create")
        after = page.inner_text("body")
        if "商用验收任务" in after or "已完成初析" in after or "分析" in after:
            # stay/list should show something
            if "育成" in after and "复盘沟通" in after and "商用验收任务" not in after:
                note("创建接单", False, "点击后跳到育成复盘页，接单可能未创建成功", "high")
            else:
                note("创建接单", True, "页面保留接单相关结果")
        else:
            note("创建接单", False, "创建后未见任务标题或成功提示", "high")
        # 再进漏斗确认是否落库
        page.goto(f"{BASE}/organization/intake", wait_until="networkidle")
        page.wait_for_timeout(1000)
        shot(page, "07b_intake_list")
        listed = page.inner_text("body")
        if "商用验收任务" in listed:
            note("接单落库", True, "漏斗/列表可见新建接单")
        else:
            note("接单落库", False, "列表未见新建接单标题", "high")

        # 7) 财务
        page.goto(f"{BASE}/organization/finance", wait_until="networkidle")
        page.wait_for_timeout(1000)
        shot(page, "08_finance")
        fin = page.inner_text("body")
        note("财务页", "财务" in fin or "收支" in fin or "营收" in fin, "财务页可打开" if ("财务" in fin or "收支" in fin) else "财务文案缺失")

        browser.close()

    _write_report(run_dir, username, steps, issues)
    print(json.dumps({"run_dir": str(run_dir), "issues": len(issues), "username": username}, ensure_ascii=False, indent=2))
    return 0 if not any(i.get("severity") == "high" for i in issues) else 2


def _write_report(run_dir: Path, username: str, steps: list[str], issues: list[dict]) -> None:
    lines = [
        "# 商用前端验收记录（从 0 操作）",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 环境：http://127.0.0.1:8000 （EVO_ENV=production）",
        f"- 账号：`{username}`（本轮注册）",
        f"- 截图目录：`{run_dir}`",
        "",
        "## 步骤",
        "",
    ]
    for s in steps:
        lines.append(f"- {s}")
    lines += ["", "## 问题清单", ""]
    if not issues:
        lines.append("- （本轮未记录问题）")
    else:
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. **[{issue.get('severity')}]** {issue.get('step')}: {issue.get('detail')}")
    lines += [
        "",
        "## 下一步",
        "",
        "1. 按问题清单修复 View/流程",
        "2. 重新生产构建并部署",
        "3. 再用新账号从 0 复测本路径",
        "",
    ]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    # also mirror latest
    latest = OUT / "LATEST_REPORT.md"
    latest.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
