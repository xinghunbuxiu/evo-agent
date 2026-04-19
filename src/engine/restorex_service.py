#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RestoreX Service
把 restorex_cli 封装成 HTTP 服务，减少人工命令操作。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def run_cli(workspace: Path, command: str, rule_profile: str, emit_raw_runtime: bool, run_id: str = "") -> dict:
    cli = workspace / "plugin" / "restorex_cli.py"
    if not cli.is_file():
        raise RuntimeError(f"restorex_cli.py not found: {cli}")

    cmd = ["python3", str(cli), "--workspace", str(workspace), "--rule-profile", rule_profile]
    if run_id:
        cmd += ["--run-id", run_id]
    if emit_raw_runtime:
        cmd += ["--emit-raw-runtime"]
    cmd += [command]

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed_ms = int((time.time() - started) * 1000)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    result = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout": out,
        "stderr": err,
        "command": command,
        "rule_profile": rule_profile,
    }
    for line in out.splitlines():
        if line.startswith("run_id="):
            result["run_id"] = line.split("=", 1)[1].strip()
        elif line.startswith("output="):
            result["output"] = line.split("=", 1)[1].strip()
        elif line.startswith("compare_output="):
            result["compare_output"] = line.split("=", 1)[1].strip()
    return result


def load_json_if_exists(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_compare_and_pick_profile(workspace: Path, profiles: str = "strict,balanced,aggressive") -> dict:
    cli = workspace / "plugin" / "restorex_cli.py"
    cmd = ["python3", str(cli), "--workspace", str(workspace), "--profiles", profiles, "compare-profiles"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    compare_output = ""
    for line in out.splitlines():
        if line.startswith("compare_output="):
            compare_output = line.split("=", 1)[1].strip()
            break
    if proc.returncode != 0 or not compare_output:
        return {
            "ok": False,
            "returncode": proc.returncode,
            "stdout": out,
            "stderr": err,
            "error": "compare_profiles_failed",
        }
    cmp_json = Path(compare_output) / "profile_compare.json"
    cmp_obj = load_json_if_exists(cmp_json)
    rec_profile = str(cmp_obj.get("recommended_profile", "")).strip() or "balanced"
    rec_run_id = str(cmp_obj.get("recommended_run_id", "")).strip()
    return {
        "ok": True,
        "compare_output": compare_output,
        "recommended_profile": rec_profile,
        "recommended_run_id": rec_run_id,
        "compare": cmp_obj,
    }


def write_runtime_evidence_file(workspace: Path, payload: dict) -> Path:
    runtime_dir = workspace / "output" / "_runtime_evidence_inbox"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    name = f"runtime_evidence_{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    path = runtime_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class RestoreHandler(BaseHTTPRequestHandler):
    workspace: Path

    def _write_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or "0")
        if n <= 0:
            return {}
        body = self.rfile.read(n).decode("utf-8", errors="replace")
        if not body.strip():
            return {}
        return json.loads(body)

    def do_GET(self) -> None:  # noqa: N802
        p = urlparse(self.path)
        if p.path == "/health":
            self._write_json(200, {"ok": True, "service": "restorex", "workspace": str(self.workspace)})
            return

        if p.path == "/latest":
            output = self.workspace / "output"
            runs = sorted([x for x in output.glob("run_*") if x.is_dir()], key=lambda x: x.name)
            if not runs:
                self._write_json(200, {"ok": True, "latest": None})
                return
            run_dir = runs[-1]
            verify = load_json_if_exists(run_dir / "reports" / "verify_report.json")
            summary = load_json_if_exists(run_dir / "reports" / "final_summary.json")
            self._write_json(
                200,
                {
                    "ok": True,
                    "latest": run_dir.name,
                    "run_dir": str(run_dir),
                    "verify_ok": bool(verify.get("ok", False)) if verify else None,
                    "summary": summary,
                },
            )
            return

        if p.path == "/recommend":
            rec = run_compare_and_pick_profile(self.workspace)
            self._write_json(200 if rec.get("ok", False) else 500, rec)
            return

        self._write_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        p = urlparse(self.path)
        if p.path not in ("/restore", "/restore-auto"):
            self._write_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            body = self._read_json()
            emit_raw_runtime = bool(body.get("emit_raw_runtime", False))
            t0 = time.time()

            runtime_evidence = body.get("runtime_evidence")
            runtime_evidence_file = str(body.get("runtime_evidence_file", "")).strip()
            runtime_log_glob = str(body.get("runtime_log_glob", "")).strip()
            auto_collect_runtime_evidence = bool(body.get("auto_collect_runtime_evidence", True))

            payload: dict = {}
            if p.path == "/restore-auto":
                profiles = str(body.get("profiles", "strict,balanced,aggressive")).strip() or "strict,balanced,aggressive"
                rec = run_compare_and_pick_profile(self.workspace, profiles=profiles)
                if not rec.get("ok", False):
                    self._write_json(500, {"ok": False, "stage": "recommend", "recommendation": rec})
                    return
                rule_profile = str(rec.get("recommended_profile", "balanced"))
                result = run_cli(self.workspace, "all", rule_profile, emit_raw_runtime, run_id="")
                payload = {
                    "ok": result.get("ok", False),
                    "mode": "auto",
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "selected_profile": rule_profile,
                    "recommendation": rec,
                    "cli": result,
                }
            else:
                command = str(body.get("command", "all")).strip() or "all"
                rule_profile = str(body.get("rule_profile", "strict")).strip() or "strict"
                run_id = str(body.get("run_id", "")).strip()
                result = run_cli(self.workspace, command, rule_profile, emit_raw_runtime, run_id)
                payload = {"ok": result.get("ok", False), "mode": "direct", "elapsed_ms": int((time.time() - t0) * 1000), "cli": result}

            rid = result.get("run_id", "")
            out = result.get("output", "")
            if rid and out:
                run_dir = Path(out)
                # 可选：注入 runtime evidence 后，按同一 run 重新收尾，避免人工继续敲命令。
                should_collect = p.path == "/restore-auto" and auto_collect_runtime_evidence and runtime_evidence is None and not runtime_evidence_file
                if should_collect:
                    cli = self.workspace / "plugin" / "restorex_cli.py"
                    collect_cmd = [
                        "python3",
                        str(cli),
                        "--workspace",
                        str(self.workspace),
                        "--rule-profile",
                        "strict",
                        "--run-id",
                        rid,
                        "collect-runtime-evidence",
                    ]
                    if runtime_log_glob:
                        collect_cmd += ["--log-glob", runtime_log_glob]
                    cproc = subprocess.run(collect_cmd, capture_output=True, text=True)
                    collected_file = ""
                    for line in (cproc.stdout or "").splitlines():
                        if line.startswith("runtime_evidence="):
                            collected_file = line.split("=", 1)[1].strip()
                            break
                    if collected_file:
                        runtime_evidence_file = collected_file
                    payload["runtime_evidence_auto_collect"] = {
                        "ok": cproc.returncode == 0,
                        "returncode": cproc.returncode,
                        "stdout": (cproc.stdout or "").strip(),
                        "stderr": (cproc.stderr or "").strip(),
                        "runtime_evidence_file": collected_file,
                    }

                if runtime_evidence is not None or runtime_evidence_file:
                    if runtime_evidence is not None:
                        evidence_path = write_runtime_evidence_file(self.workspace, {"items": runtime_evidence if isinstance(runtime_evidence, list) else []})
                    else:
                        evidence_path = Path(runtime_evidence_file)
                    ingest = {
                        "ok": False,
                        "error": "runtime_evidence_file_not_found",
                        "runtime_evidence_file": str(evidence_path),
                    }
                    if evidence_path.is_file():
                        cli = self.workspace / "plugin" / "restorex_cli.py"
                        ingest_cmd = [
                            "python3",
                            str(cli),
                            "--workspace",
                            str(self.workspace),
                            "--rule-profile",
                            "strict",
                            "--run-id",
                            rid,
                            "ingest-runtime-evidence",
                            "--runtime-evidence",
                            str(evidence_path),
                        ]
                        proc = subprocess.run(ingest_cmd, capture_output=True, text=True)
                        ingest = {
                            "ok": proc.returncode == 0,
                            "returncode": proc.returncode,
                            "stdout": (proc.stdout or "").strip(),
                            "stderr": (proc.stderr or "").strip(),
                            "runtime_evidence_file": str(evidence_path),
                        }
                    restore = run_cli(self.workspace, "restore-v1", "strict", emit_raw_runtime, run_id=rid)
                    rebuild = run_cli(self.workspace, "build-reconstructed-project", "strict", False, run_id=rid)
                    verify = run_cli(self.workspace, "verify", "strict", False, run_id=rid)
                    finalize = run_cli(self.workspace, "finalize", "strict", False, run_id=rid)
                    payload["runtime_evidence_pipeline"] = {
                        "ingest": ingest,
                        "restore_v1": restore,
                        "build_reconstructed_project": rebuild,
                        "verify": verify,
                        "finalize": finalize,
                    }

                payload["artifacts"] = {
                    "run_id": rid,
                    "run_dir": out,
                    "verify_report": str(run_dir / "reports" / "verify_report.json"),
                    "final_summary": str(run_dir / "reports" / "final_summary.json"),
                    "readable_entry": str(run_dir / "restore_v1" / "readable" / "pages" / "index.html"),
                    "reconstructed_app": str(run_dir / "reconstructed_project" / "src" / "App.vue"),
                }
                payload["verify"] = load_json_if_exists(run_dir / "reports" / "verify_report.json")
                payload["summary"] = load_json_if_exists(run_dir / "reports" / "final_summary.json")

            self._write_json(200 if payload["ok"] else 500, payload)
        except Exception as e:  # noqa: BLE001
            self._write_json(500, {"ok": False, "error": str(e)})

    def log_message(self, fmt: str, *args) -> None:
        # 服务日志保持简洁，避免刷屏。
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="RestoreX HTTP Service")
    parser.add_argument("--workspace", required=True, help="restore_workbench 绝对路径")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18700)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        raise SystemExit(f"E_RUNTIME: workspace not found -> {workspace}")

    RestoreHandler.workspace = workspace
    server = ThreadingHTTPServer((args.host, args.port), RestoreHandler)
    print(f"restorex_service started: http://{args.host}:{args.port}")
    print(f"workspace={workspace}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
