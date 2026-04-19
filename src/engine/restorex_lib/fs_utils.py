from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    import json

    return json.loads(read_text(path))


def write_json(path: Path, data: Any) -> None:
    import json

    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def find_matching_brace(text: str, open_brace_idx: int) -> int:
    if open_brace_idx < 0 or open_brace_idx >= len(text) or text[open_brace_idx] != "{":
        return -1
    depth = 0
    i = open_brace_idx
    in_str: str | None = None
    escaped = False
    in_line_comment = False
    in_block_comment = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in {"'", '"', "`"}:
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def infer_entity_line_range(text: str, start_offset: int, decl_end_offset: int) -> tuple[int, int]:
    open_idx = text.find("{", decl_end_offset)
    if open_idx >= 0:
        close_idx = find_matching_brace(text, open_idx)
        if close_idx >= 0:
            return (line_of_offset(text, start_offset), line_of_offset(text, close_idx))
    semicolon_idx = text.find(";", decl_end_offset)
    if semicolon_idx < 0:
        semicolon_idx = decl_end_offset
    return (line_of_offset(text, start_offset), line_of_offset(text, semicolon_idx))


def ensure_formatters_available(workspace: Path) -> None:
    tools_bin = workspace / ".tools" / "node_modules" / ".bin"
    path_env = os.environ.get("PATH", "")
    if tools_bin.is_dir() and str(tools_bin) not in path_env.split(":"):
        os.environ["PATH"] = f"{tools_bin}:{path_env}" if path_env else str(tools_bin)

    has_prettier = shutil.which("prettier") is not None
    has_beautify = shutil.which("js-beautify") is not None
    if has_prettier and has_beautify:
        return

    npm_bin = shutil.which("npm")
    if not npm_bin:
        return

    tools_root = workspace / ".tools"
    tools_root.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [npm_bin, "install", "--prefix", str(tools_root), "--silent", "prettier", "js-beautify"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return

    if tools_bin.is_dir():
        path_env = os.environ.get("PATH", "")
        if str(tools_bin) not in path_env.split(":"):
            os.environ["PATH"] = f"{tools_bin}:{path_env}" if path_env else str(tools_bin)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def collect_files(root: Path, exts: set[str] | None = None) -> list[Path]:
    files: list[Path] = []
    if exts is None:
        exts = {".html", ".js", ".css", ".svg"}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
    return files


def rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def collect_ui_seed_tokens(source_root: Path) -> set[str]:
    tokens: set[str] = set()
    html_files = collect_files(source_root, {".html"})
    for f in html_files:
        text = read_text(f)
        for m in re.finditer(r'id=["\']([A-Za-z0-9_\-]{3,64})["\']', text):
            tokens.add(m.group(1).strip().lower())
        for m in re.finditer(r'class=["\']([^"\']+)["\']', text):
            for part in re.split(r"\s+", m.group(1).strip()):
                p = part.strip().lower()
                if len(p) >= 3:
                    tokens.add(p)
        for m in re.finditer(r"[\u4e00-\u9fff]{2,20}", text):
            tokens.add(m.group(0))
        for m in re.finditer(r">([A-Za-z][A-Za-z0-9 _-]{2,40})<", text):
            raw = m.group(1).strip().lower()
            if raw and not raw.startswith("http"):
                tokens.add(raw)
    noise = {
        "div",
        "span",
        "html",
        "body",
        "head",
        "script",
        "style",
        "button",
        "input",
        "label",
        "title",
        "content",
        "app",
        "main",
    }
    return {t for t in tokens if t and t not in noise}


def score_ui_flow_signal(
    line: str,
    trigger: str,
    bridge_calls: list[str],
    ui_refs: list[str],
    ui_seed_tokens: set[str],
) -> tuple[int, list[str]]:
    score = 0
    hits: list[str] = []
    line_low = line.lower()

    if trigger == "ui_event":
        score += 3
    if ui_refs:
        score += min(3, len(ui_refs))
    if bridge_calls:
        score += 2

    ui_keywords = (
        "click",
        "change",
        "submit",
        "dialog",
        "modal",
        "drawer",
        "tab",
        "menu",
        "button",
        "open",
        "close",
        "show",
        "hide",
    )
    zh_keywords = ("打开", "关闭", "提交", "确认", "取消", "切换", "刷新", "设置", "窗口", "菜单")
    if any(k in line_low for k in ui_keywords) or any(k in line for k in zh_keywords):
        score += 1

    for token in ui_seed_tokens:
        if len(hits) >= 8:
            break
        if len(token) >= 3:
            if token in line_low:
                hits.append(token)
        elif token in line:
            hits.append(token)
    if hits:
        score += min(4, len(hits))
    return score, sorted(set(hits))
