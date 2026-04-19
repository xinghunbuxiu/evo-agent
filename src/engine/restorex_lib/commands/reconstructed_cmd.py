from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import read_text, write_json, write_text
from restorex_lib.run_context import run_paths
from restorex_lib.config_rules import load_json_if_exists


def normalize_component_name(file_name: str) -> str:
    base = Path(file_name).stem
    base = re.sub(r"-[A-Za-z0-9_-]{6,}$", "", base)
    parts = re.split(r"[^A-Za-z0-9]+", base)
    parts = [p for p in parts if p]
    if not parts:
        return "RecoveredChunk"
    name = "".join(p[:1].upper() + p[1:] for p in parts)
    if not name[0].isalpha():
        name = f"Recovered{name}"
    return name


DEFAULT_RECONSTRUCT_RULES: dict[str, Any] = {
    "target_rules": [
        {
            "match_any": ["dialog", "modal", "drawer", "view", "page"],
            "target_dir": "views/recovered",
            "suffix": ".js",
        },
        {
            "match_any": ["service", "api", "store", "repository", "client"],
            "target_dir": "services/recovered",
            "suffix": "Service.js",
        },
    ],
    "default_target": {
        "target_dir": "modules/recovered",
        "suffix": ".js",
    },
    "runtime_page_rules": [],
    "default_runtime_page": "pages/index.html",
    "project_shell": {
        "mount_mode": "direct_bundle_entry",
        "generate_workspace_view": False,
    },
}


def _load_reconstruct_rules(workspace: Path) -> dict[str, Any]:
    rule_obj = load_json_if_exists(workspace / "cache" / "remote" / "reconstruct_rules.json")
    merged = dict(DEFAULT_RECONSTRUCT_RULES)
    for k in ("target_rules", "default_target", "runtime_page_rules", "default_runtime_page", "project_shell"):
        if k in rule_obj:
            merged[k] = rule_obj[k]
    return merged


def classify_recovered_target(file_path: str, rules: dict[str, Any]) -> tuple[str, str]:
    low = file_path.lower()
    comp = normalize_component_name(file_path)
    target_rules = rules.get("target_rules", []) if isinstance(rules.get("target_rules", []), list) else []
    for rule in target_rules:
        if not isinstance(rule, dict):
            continue
        terms = [str(x).lower() for x in rule.get("match_any", []) if str(x).strip()]
        if terms and not any(t in low for t in terms):
            continue
        target_dir = str(rule.get("target_dir", "")).strip() or "modules/recovered"
        suffix = str(rule.get("suffix", "")).strip() or ".js"
        return (target_dir, f"{comp}{suffix}")
    default_target = rules.get("default_target", {}) if isinstance(rules.get("default_target", {}), dict) else {}
    target_dir = str(default_target.get("target_dir", "")).strip() or "modules/recovered"
    suffix = str(default_target.get("suffix", "")).strip() or ".js"
    return (target_dir, f"{comp}{suffix}")


def resolve_runtime_entry(file_path: str, rules: dict[str, Any], bundle_root: str) -> str:
    low = file_path.lower()
    page_rules = rules.get("runtime_page_rules", []) if isinstance(rules.get("runtime_page_rules", []), list) else []
    for rule in page_rules:
        if not isinstance(rule, dict):
            continue
        terms = [str(x).lower() for x in rule.get("match_any", []) if str(x).strip()]
        if terms and not any(t in low for t in terms):
            continue
        page = str(rule.get("page", "")).strip()
        if page:
            return f"{bundle_root}/{page.lstrip('./')}"
    default_page = str(rules.get("default_runtime_page", "pages/index.html")).strip() or "pages/index.html"
    return f"{bundle_root}/{default_page.lstrip('./')}"


def extract_index_entry_assets(readable_root: Path) -> tuple[list[str], list[str]]:
    index_html = readable_root / "pages" / "index.html"
    if not index_html.is_file():
        return ([], [])
    text = read_text(index_html)
    css_assets = re.findall(r'<link[^>]+href="([^"]+\.css)"', text)
    js_assets = re.findall(r'<script[^>]+src="([^"]+\.js)"', text)
    # 统一转成 assets 相对路径（输入页面一般是 ./assets/*）
    def to_rel_asset(p: str) -> str:
        s = p.strip().replace("\\", "/")
        if s.startswith("./"):
            s = s[2:]
        if s.startswith("/"):
            s = s[1:]
        if "assets/" in s:
            return s[s.index("assets/") :]
        return s

    css = [to_rel_asset(x) for x in css_assets if x.strip()]
    js = [to_rel_asset(x) for x in js_assets if x.strip()]
    return (css, js)


def cmd_build_reconstructed_project(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    readable = paths.restore_v1 / "readable"
    if not readable.is_dir():
        raise SystemExit("E_RUNTIME: run restore-v1 first")

    portrait_path = paths.analysis / "code_portrait.json"
    origin_path = paths.analysis / "build_origin_report.json"
    queue_path = paths.analysis / "restore_priority_queue.json"
    rename_plan_path = paths.analysis / "rename_plan_focus.json"
    mapping_path = paths.analysis / "mapping_index.json"
    reconstruct_rules = _load_reconstruct_rules(workspace)
    portrait = json.loads(read_text(portrait_path)) if portrait_path.is_file() else {}
    origin = json.loads(read_text(origin_path)) if origin_path.is_file() else {"items": []}
    queue_obj = json.loads(read_text(queue_path)) if queue_path.is_file() else {"items": []}
    rename_obj = json.loads(read_text(rename_plan_path)) if rename_plan_path.is_file() else {"items": []}
    mapping_obj = json.loads(read_text(mapping_path)) if mapping_path.is_file() else {"applied_renames": []}
    batch_file_map: dict[str, set[int]] = {}
    for n in (1, 2, 3):
        bp = paths.analysis / f"entity_restore_batch_{n}.json"
        if not bp.is_file():
            continue
        try:
            bobj = json.loads(read_text(bp))
        except Exception:
            continue
        for it in bobj.get("items", []):
            f = str(it.get("file", "")).strip()
            if not f:
                continue
            batch_file_map.setdefault(f, set()).add(n)
    frameworks = portrait.get("build_profile", {}).get("frameworks", []) if isinstance(portrait, dict) else []
    is_vue_like = any(str(f.get("name", "")).startswith("vue-like") for f in frameworks if isinstance(f, dict))

    proj = paths.base / "reconstructed_project"
    if proj.exists():
        shutil.rmtree(proj)
    (proj / "src" / "restored" / "bundle").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "views" / "recovered").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "services" / "recovered").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "modules" / "recovered").mkdir(parents=True, exist_ok=True)
    (proj / "src" / "meta").mkdir(parents=True, exist_ok=True)
    # 不再把运行面复制到 public/legacy；统一转存到项目源码目录。
    shutil.copytree(readable, proj / "src" / "restored" / "bundle", dirs_exist_ok=True)

    package_json = {
        "name": f"restorex-reconstructed-{run_id}",
        "private": True,
        "version": "0.0.1",
        "type": "module",
        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
        "dependencies": {"vue": "^3.5.0"},
        "devDependencies": {"typescript": "^5.9.0", "vite": "^7.0.0", "@vitejs/plugin-vue": "^6.0.0"},
    }
    write_json(proj / "package.json", package_json)
    write_text(
        proj / "tsconfig.json",
        """{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "types": ["vite/client"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"]
}
""",
    )
    write_text(
        proj / "vite.config.ts",
        """import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
});
""",
    )
    write_text(
        proj / "index.html",
        """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Reconstructed Project</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
""",
    )
    write_text(
        proj / "src" / "main.ts",
        """// 自动还原入口：直接执行还原包中的真实入口资源（由 index.html 提取）
"""
    )

    bundle_root = "src/restored/bundle"
    app_files = [
        i.get("file", "")
        for i in origin.get("items", [])
        if i.get("origin_label") == "app_business" and str(i.get("file", "")).endswith(".js")
    ]
    generated_components: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    recovered_modules: list[dict[str, Any]] = []
    for file_path in sorted({str(x) for x in app_files if x}):
        comp = normalize_component_name(file_path)
        file_queue = [x for x in queue_obj.get("items", []) if str(x.get("file", "")) == file_path]
        file_queue.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
        queue_top = file_queue[:6]
        bridge_calls: list[str] = []
        for q in queue_top:
            for b in q.get("bridge_calls", []):
                s = str(b).strip()
                if s and s not in bridge_calls:
                    bridge_calls.append(s)
        rename_candidates = [
            {
                "symbol": str(x.get("symbol", "")),
                "candidate": str(x.get("candidate", "")),
                "confidence": str(x.get("confidence", "")),
                "source": str(x.get("source", "")),
                "apply": bool(x.get("apply", False)),
            }
            for x in rename_obj.get("items", [])
            if str(x.get("file", "")) == file_path
        ][:16]
        logic_snippets: list[dict[str, Any]] = []
        readable_src = readable / file_path
        if readable_src.is_file():
            try:
                readable_text = read_text(readable_src)
                src_lines = readable_text.splitlines()
            except Exception:
                readable_text = ""
                src_lines = []
        else:
            readable_text = ""
            src_lines = []
        for q in queue_top[:4]:
            line_no = int(q.get("line_min", 0) or 0)
            ent_name = str(q.get("entity_name", ""))
            if ent_name == "__module__" and src_lines:
                found_line = 0
                for bc in q.get("bridge_calls", []):
                    token = str(bc).strip()
                    if not token:
                        continue
                    for idx, l in enumerate(src_lines, start=1):
                        if token in l:
                            found_line = idx
                            break
                    if found_line > 0:
                        break
                if found_line > 0:
                    line_no = found_line
            if line_no <= 0 or not src_lines:
                continue
            start = max(1, line_no - 4)
            end = min(len(src_lines), line_no + 8)
            frag = []
            for ln in range(start, end + 1):
                frag.append(f"{ln:04d}: {src_lines[ln - 1]}")
            logic_snippets.append(
                {
                    "source_file": file_path,
                    "entity_name": str(q.get("entity_name", "__unknown__")),
                    "line": line_no,
                    "start_line": start,
                    "end_line": end,
                    "location": f"{file_path}:{start}-{end}",
                    "snippet": "\n".join(frag),
                }
            )
        priority = str(queue_top[0].get("restore_priority", "high")) if queue_top else "high"
        chain_count = sum(int(x.get("chain_count", 0)) for x in queue_top) if queue_top else 0
        high_conf_count = sum(int(x.get("high_conf_count", 0)) for x in queue_top) if queue_top else 0
        batch_tags = sorted(batch_file_map.get(file_path, set()))
        applied_for_file = [x for x in mapping_obj.get("applied_renames", []) if str(x.get("file", "")) == file_path]
        entity_applied_for_file = [x for x in applied_for_file if str(x.get("source", "")) == "entity_chain_infer"]

        runtime_src = resolve_runtime_entry(file_path, reconstruct_rules, bundle_root)

        # 保留证据元信息，不再写“说明型占位组件”。
        evidence_records.append(
            {
                "component": comp,
                "source": file_path,
                "priority": priority,
                "runtime_src": runtime_src,
                "chain_count": chain_count,
                "high_conf_count": high_conf_count,
                "bridge_calls": bridge_calls,
                "rename_candidates": rename_candidates,
                "logic_snippets": logic_snippets,
                "batch_tags": batch_tags,
                "applied_rename_count": len(applied_for_file),
                "entity_applied_count": len(entity_applied_for_file),
            }
        )
        generated_components.append(
            {
                "component": comp,
                "source": file_path,
                "priority": priority,
                "runtime_src": runtime_src,
                "chain_count": chain_count,
                "high_conf_count": high_conf_count,
                "batch_tags": batch_tags,
                "bridge_count": len(bridge_calls),
                "rename_candidate_count": len(rename_candidates),
                "applied_rename_count": len(applied_for_file),
                "entity_applied_count": len(entity_applied_for_file),
            }
        )
        target_dir_rel, target_file = classify_recovered_target(file_path, reconstruct_rules)
        target_abs = proj / "src" / target_dir_rel / target_file
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "/**",
            f" * 还原候选源码（自动生成）",
            f" * 来源文件: {file_path}",
            f" * run_id: {run_id}",
            " * 说明: 该文件来自 readable 业务层产物，作为后续 SFC/服务拆分的真实输入基线。",
            " */",
            "",
        ]
        write_text(target_abs, "\n".join(header) + readable_text + ("\n" if readable_text and not readable_text.endswith("\n") else ""))
        recovered_modules.append(
            {
                "source_file": file_path,
                "target_file": f"src/{target_dir_rel}/{target_file}",
                "priority": priority,
                "chain_count": chain_count,
                "high_conf_count": high_conf_count,
                "bridge_count": len(bridge_calls),
                "rename_candidate_count": len(rename_candidates),
            }
        )

    entry_css_assets, entry_js_assets = extract_index_entry_assets(readable)
    main_ts_lines = [
        "// 自动还原入口：直接执行还原包中的真实入口资源（由 index.html 提取）",
        "// 注意：这里优先保真，不对业务逻辑做二次改写。",
    ]
    for css in entry_css_assets:
        main_ts_lines.append(f'import "./restored/bundle/{css}";')
    for js in entry_js_assets:
        main_ts_lines.append(f'import "./restored/bundle/{js}";')
    if not entry_css_assets and not entry_js_assets:
        main_ts_lines.append('console.warn("[restorex] no entry assets detected from pages/index.html");')
    write_text(proj / "src" / "main.ts", "\n".join(main_ts_lines) + "\n")

    write_json(
        proj / "src" / "meta" / "chunk-map.json",
        {
            "run_id": run_id,
            "is_vue_like": is_vue_like,
            "rules_source": "spec/reconstruct_rules.json",
            "generated_components": generated_components,
            "recovered_modules": recovered_modules,
            "restored_bundle_root": bundle_root,
            "entry_css_assets": entry_css_assets,
            "entry_js_assets": entry_js_assets,
        },
    )
    write_json(
        proj / "src" / "meta" / "recovered_evidence.json",
        {
            "run_id": run_id,
            "generated_at": dt.datetime.now().isoformat(),
            "records": evidence_records,
        },
    )
    write_text(
        proj / "README_RECONSTRUCTION_CN.md",
        f"""# Reconstructed Project

- run_id: `{run_id}`
- framework: `{'vue-like' if is_vue_like else 'web-like'}`
- 输入包转存目录: `{bundle_root}`
- 自动还原组件数量: `{len(generated_components)}`
- 规则来源: `spec/reconstruct_rules.json`

## 使用
```bash
npm install
npm run dev
```

## 说明
- 当前默认是“保真入口优先”模式：`src/main.ts` 直接加载输入包入口资源。
- 原始输入副本在 `src/restored/bundle`，后续应逐模块替换为真实 `src/components|views|services`。
- 证据数据统一在 `src/meta/recovered_evidence.json`。
- 该工程用于还原验证，不代表已经完成真实 SFC 全量还原。
""",
    )

    raw_proj = paths.base / "reconstructed_project_raw"
    if raw_proj.exists():
        shutil.rmtree(raw_proj)
    shutil.copytree(proj, raw_proj)
