#!/usr/bin/env python3
"""
上线前自检：P0 自动化 + 前端构建 + 环境变量 + 可选健康检查。

用法:
  cd evo-mcp
  PYTHONPATH=src python3 scripts/production_readiness_check.py
  PYTHONPATH=src python3 scripts/production_readiness_check.py --check-health
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSION_SECRET = "evo-session-secret-change-in-production"


def run_m1() -> tuple[bool, str]:
    cmd = [sys.executable, str(ROOT / "scripts" / "m1_ops_check.py")]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-3:]
    detail = " | ".join(tail) if tail else f"exit={proc.returncode}"
    return proc.returncode == 0, detail


def check_dist() -> tuple[bool, str]:
    index = ROOT / "admin-ui" / "dist" / "index.html"
    if not index.is_file():
        return False, "缺少 admin-ui/dist/index.html，请运行: cd admin-ui && npm run build"
    assets = ROOT / "admin-ui" / "dist" / "assets"
    count = len(list(assets.glob("*.js"))) if assets.is_dir() else 0
    return True, f"dist 就绪，JS chunk {count} 个"


def check_env() -> tuple[bool, str]:
    env_path = ROOT / ".env"
    issues: list[str] = []
    if not env_path.is_file():
        issues.append(".env 不存在（请 cp .env.example .env）")
    else:
        text = env_path.read_text(encoding="utf-8", errors="ignore")
        for key in ("DB_PASSWORD", "GITEE_TOKEN"):
            if f"{key}=" in text and f"{key}=your_" in text:
                issues.append(f"{key} 仍为占位符")
        session = os.getenv("SESSION_SECRET") or ""
        if not session:
            for line in text.splitlines():
                if line.startswith("SESSION_SECRET="):
                    session = line.split("=", 1)[1].strip()
                    break
        if not session or session == DEFAULT_SESSION_SECRET:
            issues.append(
                "SESSION_SECRET 未设置或仍为默认值；生成: "
                "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\" "
                "后写入 .env"
            )
        elif len(session) < 24:
            issues.append("SESSION_SECRET 过短（建议 ≥24 字符）")
    if issues:
        return False, "; ".join(issues)
    return True, "环境变量基本就绪"


def check_health(base_url: str) -> tuple[bool, str]:
    try:
        with urlopen(f"{base_url.rstrip('/')}/health", timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        return False, f"无法访问 {base_url}/health: {exc}"
    status = payload.get("status")
    warnings = payload.get("warnings") or []
    checks = payload.get("checks") or {}
    if status != "ok":
        return False, f"health={status}, warnings={warnings}"
    if not checks.get("spa_static"):
        return False, "health 通过但 spa_static=false"
    return True, f"health ok, checks={checks}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evo 上线前自检")
    parser.add_argument("--check-health", action="store_true", help="额外请求运行中服务的 /health")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Admin API 地址")
    args = parser.parse_args()

    items: list[tuple[str, bool, str]] = []
    ok, detail = run_m1()
    items.append(("M1 自动化 (P0)", ok, detail))

    ok, detail = check_dist()
    items.append(("前端生产构建", ok, detail))

    ok, detail = check_env()
    items.append(("环境变量", ok, detail))

    if args.check_health:
        ok, detail = check_health(args.base_url)
        items.append(("运行中健康检查", ok, detail))

    passed = sum(1 for _, ok, _ in items if ok)
    total = len(items)
    print("=" * 60)
    print("Evo 上线前自检")
    print("=" * 60)
    for name, ok, detail in items:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}")
        print(f"       {detail}")
    print("-" * 60)
    print(f"合计: {passed}/{total} 通过")
    if passed == total:
        print("✅ 可进入上线部署（仍需配置 HTTPS 与强 SESSION_SECRET）")
        return 0
    print("❌ 请先修复 FAIL 项后再上线")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
