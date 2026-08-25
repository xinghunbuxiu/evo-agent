#!/usr/bin/env python3
"""用租户已配置的 DeepSeek（非 mock）跑补知识写回经验卡探测。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["EVO_M1_LIVE_MODEL"] = "1"
os.environ.pop("EVO_MODEL_PROVIDER_MOCK", None)


def main() -> int:
    from admin.m1_knowledge_learning_probe_runtime import run_knowledge_learning_probe

    probe = run_knowledge_learning_probe(ROOT, tenant_id="default")
    # never dump api keys
    print(json.dumps(probe, ensure_ascii=False, indent=2))
    return 0 if probe.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
