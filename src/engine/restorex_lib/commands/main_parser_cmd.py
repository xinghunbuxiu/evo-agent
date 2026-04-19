from __future__ import annotations

import argparse

COMMAND_CHOICES = [
    "init-run",
    "normalize",
    "infer-build-origin",
    "scan-structure",
    "build-portrait",
    "build-file-portraits",
    "build-class-portraits",
    "build-method-portraits",
    "build-constant-portraits",
    "build-js-semantic-profile",
    "build-script-plan",
    "build-feedback",
    "analyze-obfuscation",
    "build-library-match",
    "extract-chains",
    "build-evidence",
    "bootstrap-source-rules",
    "decompile-bundle-structure",
    "extract-source-modules",
    "build-source-graph",
    "build-reconstructed-project",
    "build-source-project",
    "restore-v1",
    "apply-scope-renames",
    "verify",
    "verify-source-project",
    "diagnose-pipeline",
    "finalize",
    "runtime-evidence-stub",
    "collect-runtime-evidence",
    "ingest-runtime-evidence",
    "compare-profiles",
    "compare-runs",
    "status",
    "all",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RestoreX: 通用 JS 逆向还原流水线")
    parser.add_argument("--workspace", required=True, help="restore_workbench 目录")
    parser.add_argument("--run-id", default="", help="指定 run id，不填则自动生成")
    parser.add_argument("--rule-profile", default="strict", help="规则档位: strict|balanced|aggressive")
    parser.add_argument("--profiles", default="strict,balanced,aggressive", help="compare-profiles 使用，逗号分隔")
    parser.add_argument("--compare-run-ids", default="", help="compare-runs 使用，逗号分隔 run_id")
    parser.add_argument("--emit-raw-runtime", action="store_true", help="生成 restore_v1/raw_runtime（默认不生成）")
    parser.add_argument("--auto-runtime-evidence", action="store_true", help="all 流程中自动采集并注入 runtime 证据")
    parser.add_argument(
        "--runtime-prefer-direct",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="采集 runtime 证据时优先 direct 命令证据（默认 true）",
    )
    parser.add_argument("command", choices=COMMAND_CHOICES)
    parser.add_argument("--runtime-evidence", default="", help="运行时证据 JSON 文件路径（用于 ingest-runtime-evidence）")
    parser.add_argument("--log-glob", default="", help="collect-runtime-evidence 使用，日志 glob（绝对路径）")
    parser.add_argument("--collect-limit", type=int, default=3000, help="collect-runtime-evidence 采集上限")
    return parser
