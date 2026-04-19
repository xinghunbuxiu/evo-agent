from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import collect_files, read_text, rel, sha256_file, write_json, write_text
from restorex_lib.run_context import ensure_baseline_exists, run_paths


def try_external_format(ext: str, text: str, rel_path: str) -> tuple[str, str]:
    parser = ""
    if ext == ".js":
        parser = "babel"
    elif ext == ".css":
        parser = "css"
    elif ext == ".html":
        parser = "html"
    if not parser:
        return text, "none"

    prettier_bin = shutil.which("prettier")
    if prettier_bin:
        try:
            proc = subprocess.run(
                [prettier_bin, "--parser", parser, "--stdin-filepath", rel_path],
                input=text,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout, "prettier"
        except Exception:
            pass

    beautify_bin = shutil.which("js-beautify")
    if beautify_bin and ext == ".js":
        try:
            proc = subprocess.run(
                [beautify_bin, "--type", "js", "--stdin"],
                input=text,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout, "js-beautify"
        except Exception:
            pass

    return text, "none"


def normalize_code_text(ext: str, text: str) -> str:
    src = text.replace("\r\n", "\n").replace("\r", "\n")
    if ext in {".js", ".css"}:
        lines = src.split("\n")
        out_lines: list[str] = []
        for line in lines:
            if len(line) > 220:
                line = line.replace(";", ";\n")
                line = line.replace("{", "{\n")
                line = line.replace("}", "}\n")
                line = line.replace("),", "),\n")
                line = re.sub(r",([A-Za-z_$][\w$]*:)", r",\n\1", line)
            out_lines.append(line)
        src = "\n".join(out_lines)
        src = re.sub(r"\n{3,}", "\n\n", src)
    if ext == ".html":
        src = re.sub(r">\s+<", ">\n<", src)
        src = re.sub(r"\n{3,}", "\n\n", src)
    return src.strip() + "\n"


def safe_symbol_replace(text: str, short: str, candidate: str) -> tuple[str, int]:
    pattern = re.compile(rf"\b{re.escape(short)}\b")
    # 预先标记 import 语句的行范围，这些行里的符号名是外部模块导出名，不应被替换
    import_line_ranges: set[int] = set()
    for im in re.finditer(r"^import\s+\{[^}]*\}\s+from\s+['\"][^'\"]+['\"]", text, re.MULTILINE):
        start_line = text.count("\n", 0, im.start())
        end_line = text.count("\n", 0, im.end())
        for ln in range(start_line, end_line + 1):
            import_line_ranges.add(ln)
    out_parts: list[str] = []
    last = 0
    replaced = 0
    for m in pattern.finditer(text):
        s, e = m.span()
        prev_char = text[s - 1] if s > 0 else ""
        next_slice = text[e : e + 6]
        # 避免改写正则转义序列（例如 \b、\d），防止把 regex token 误替换成业务名。
        if prev_char == "\\":
            continue
        if len(short) == 1 and prev_char == "/" and next_slice.startswith(".test"):
            continue
        # 跳过 import 语句里的符号名（外部模块导出名，不是本文件定义的符号）
        cur_line = text.count("\n", 0, s)
        if cur_line in import_line_ranges:
            continue
        out_parts.append(text[last:s])
        out_parts.append(candidate)
        last = e
        replaced += 1
    if replaced == 0:
        return text, 0
    out_parts.append(text[last:])
    return "".join(out_parts), replaced


def apply_scoped_symbol_replace(
    text: str,
    short: str,
    candidate: str,
    line_start: int,
    line_end: int,
) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return text, 0
    s = max(1, int(line_start))
    e = max(s, int(line_end))
    if s > len(lines):
        return text, 0
    e = min(e, len(lines))
    segment = "".join(lines[s - 1 : e])
    new_seg, n = safe_symbol_replace(segment, short, candidate)
    if n <= 0:
        return text, 0
    replacement_lines = new_seg.splitlines(keepends=True)
    if not replacement_lines:
        replacement_lines = [new_seg]
    lines[s - 1 : e] = replacement_lines
    return "".join(lines), n


def safe_call_symbol_replace(text: str, short: str, candidate: str) -> tuple[str, int]:
    pattern = re.compile(rf"\b{re.escape(short)}\b(?=\s*\()")
    out_parts: list[str] = []
    last = 0
    replaced = 0
    for m in pattern.finditer(text):
        s, e = m.span()
        prev_char = text[s - 1] if s > 0 else ""
        next_slice = text[e : e + 6]
        # 调用位替换同样要避开正则转义 token。
        if prev_char == "\\":
            continue
        if len(short) == 1 and prev_char == "/" and next_slice.startswith(".test"):
            continue
        out_parts.append(text[last:s])
        out_parts.append(candidate)
        last = e
        replaced += 1
    if replaced == 0:
        return text, 0
    out_parts.append(text[last:])
    return "".join(out_parts), replaced


def apply_scoped_call_symbol_replace(
    text: str,
    short: str,
    candidate: str,
    line_start: int,
    line_end: int,
) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return text, 0
    s = max(1, int(line_start))
    e = max(s, int(line_end))
    if s > len(lines):
        return text, 0
    e = min(e, len(lines))
    segment = "".join(lines[s - 1 : e])
    new_seg, n = safe_call_symbol_replace(segment, short, candidate)
    if n <= 0:
        return text, 0
    replacement_lines = new_seg.splitlines(keepends=True)
    if not replacement_lines:
        replacement_lines = [new_seg]
    lines[s - 1 : e] = replacement_lines
    return "".join(lines), n


def _to_camel_parts(s: str) -> list[str]:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", s) if p]
    return [p.lower() for p in parts if p]


def bridge_token_to_candidate(token: str, auto_prefixes: tuple[str, ...]) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    if "|" in raw:
        raw = raw.split("|", 1)[1]
    raw = raw.replace(":", "_").replace("-", "_")
    parts = _to_camel_parts(raw)
    if not parts:
        return ""
    first = parts[0]
    tail = "".join(p[:1].upper() + p[1:] for p in parts[1:])
    base = first + tail
    if not first.startswith(auto_prefixes):
        base = "handle" + first[:1].upper() + first[1:] + tail
    if not re.fullmatch(r"[A-Za-z_]\w{2,}", base):
        return ""
    return base


def cmd_normalize(workspace: Path, run_id: str) -> None:
    paths = run_paths(workspace, run_id)
    _, raw_snapshot = ensure_baseline_exists(paths)
    normalized = paths.baseline / "normalized_working_copy"
    if normalized.exists():
        shutil.rmtree(normalized)
    shutil.copytree(raw_snapshot, normalized)

    format_map: list[dict[str, Any]] = []
    for f in collect_files(normalized):
        rel_path = rel(f, normalized)
        ext = f.suffix.lower()
        raw_text = read_text(f)
        external_text, formatter = try_external_format(ext, raw_text, rel_path)
        normalized_text = normalize_code_text(ext, external_text)
        if normalized_text != raw_text:
            write_text(f, normalized_text)
        format_map.append(
            {
                "path": rel_path,
                "ext": ext,
                "formatter": formatter,
                "raw_sha256": sha256_file(raw_snapshot / rel_path),
                "normalized_sha256": sha256_file(f),
                "line_count_raw": raw_text.count("\n") + 1,
                "line_count_normalized": normalized_text.count("\n"),
                "offset_mapping_strategy": "coarse_by_hash_and_line_count",
            }
        )
    write_json(paths.baseline / "format_map.json", {"run_id": run_id, "count": len(format_map), "items": format_map})
