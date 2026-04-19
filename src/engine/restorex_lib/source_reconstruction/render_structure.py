from __future__ import annotations

import re
from typing import Any


def _unique_preserve(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if token and token not in items:
            items.append(token)
    return items


def _meaningful_literals(text: str, limit: int = 40) -> list[str]:
    items: list[str] = []
    for literal in re.findall(r'"([^"\n]{2,64})"', text):
        token = literal.strip()
        if not token:
            continue
        if token.startswith("./") or token.startswith("../"):
            continue
        if token.endswith((".js", ".css")) or "assets/" in token:
            continue
        if token in {"visible", "close", "default", "update:visible"}:
            continue
        if re.fullmatch(r"[a-z0-9-]{6,}", token):
            continue
        if token not in items:
            items.append(token)
        if len(items) >= limit:
            break
    return items


def _extract_class_text_pairs(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    pattern = re.compile(r'\{\s*class:\s*"([^"]+)"\s*\}\s*,\s*"([^"]+)"', re.S)
    for class_name, literal in pattern.findall(text):
        items.append({"class_name": class_name.strip(), "text": literal.strip()})
    ternary_pattern = re.compile(
        r'class:\s*"([^"]+)"[\s\S]{0,220}?\?\s*"([^"]+)"\s*:\s*"([^"]+)"',
        re.S,
    )
    for class_name, a, b in ternary_pattern.findall(text):
        for literal in (a, b):
            items.append({"class_name": class_name.strip(), "text": literal.strip()})
    return items


def _extract_inputs(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    pattern = re.compile(
        r'o\(\s*"input"\s*,\s*\{([\s\S]*?)\}\s*,\s*null',
        re.S,
    )
    for block in pattern.findall(text):
        placeholder_match = re.search(r'placeholder:\s*"([^"]+)"', block)
        class_match = re.search(r'class:\s*"([^"]+)"', block)
        type_match = re.search(r'type:\s*"([^"]+)"', block)
        items.append(
            {
                "placeholder": placeholder_match.group(1).strip() if placeholder_match else "",
                "class_name": class_match.group(1).strip() if class_match else "",
                "input_type": type_match.group(1).strip() if type_match else "text",
            }
        )
    return items


def _extract_buttons(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ternary_map: dict[str, list[str]] = {}
    for a, b in re.findall(r'B\([^?]+\?\s*"([^"]+)"\s*:\s*"([^"]+)"\)', text):
        ternary_map["*"] = _unique_preserve(ternary_map.get("*", []) + [a, b])
    pattern = re.compile(r'o\(\s*"button"\s*,\s*\{([\s\S]*?)\}\s*,\s*([\s\S]{1,120}?)\s*,\s*\d+', re.S)
    for props_block, label_block in pattern.findall(text):
        class_match = re.search(r'class:\s*"([^"]+)"', props_block)
        labels = re.findall(r'"([^"]+)"', label_block)
        label_values = _unique_preserve(labels + ternary_map.get("*", []))
        items.append(
            {
                "class_name": class_match.group(1).strip() if class_match else "",
                "labels": label_values,
            }
        )
    return items


def _extract_message_literals(text: str) -> list[str]:
    items: list[str] = []
    for value in re.findall(r"\.\s*(?:warning|error|success|info)\(\s*\"([^\"]+)\"", text):
        token = str(value).strip()
        if token and token not in items:
            items.append(token)
    return items


def _extract_ternary_literals(text: str) -> list[str]:
    items: list[str] = []
    for a, b in re.findall(r'\?\s*"([^"]+)"\s*:\s*"([^"]+)"', text):
        for value in (a, b):
            token = str(value).strip()
            if token and token not in items:
                items.append(token)
    return items


def _class_to_label(class_name: str) -> str:
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", class_name) if token]
    ignored = {"is", "has", "with", "data", "ui", "codex", "restorex"}
    filtered = [token for token in tokens if token.lower() not in ignored]
    if not filtered:
        filtered = tokens[-2:] if len(tokens) >= 2 else tokens
    return " ".join(token[:1].upper() + token[1:] for token in filtered[-2:]).strip()


def _infer_field_label(placeholder: str, hint: str, class_name: str) -> str:
    corpus = " ".join([placeholder, hint, class_name]).lower()
    if any(token in corpus for token in ("password", "密码")):
        return "Password"
    if any(token in corpus for token in ("token", "card", "卡密")):
        return "Token"
    if any(token in corpus for token in ("proxy", "http://", "https://", "socks")):
        return "Proxy Address"
    if any(token in corpus for token in ("address", "地址")):
        return "Address"
    if any(token in corpus for token in ("port", "端口")):
        return "Port"
    if any(token in corpus for token in ("account", "账号", "email", "mail")):
        return "Account"
    return _class_to_label(class_name) or "Field"


def _find_title(text_pairs: list[dict[str, str]], fallback_title: str) -> str:
    for item in text_pairs:
        class_name = item["class_name"].lower()
        if "title" in class_name:
            return item["text"]
    return fallback_title


def _find_subtitle(text_pairs: list[dict[str, str]], hints: list[str]) -> str:
    for item in text_pairs:
        class_name = item["class_name"].lower()
        if "subtitle" in class_name or "desc" in class_name or "hint" in class_name:
            return item["text"]
    return hints[0] if hints else ""


def analyze_component_structure(
    *,
    name: str,
    source_file: str,
    text: str,
    fallback_title: str,
    class_refs: list[str],
) -> dict[str, Any] | None:
    text_pairs = _extract_class_text_pairs(text)
    inputs = _extract_inputs(text)
    buttons = _extract_buttons(text)
    message_literals = _extract_message_literals(text)
    ternary_literals = _extract_ternary_literals(text)
    literals = _meaningful_literals(text)
    form_hints = _unique_preserve(
        [item["text"] for item in text_pairs if "hint" in item["class_name"].lower()]
    )
    title = _find_title(text_pairs, fallback_title)
    subtitle = _find_subtitle(text_pairs, form_hints)
    primary_actions = _unique_preserve(
        [label for button in buttons for label in button.get("labels", []) if "..." not in label]
    )
    transient_actions = _unique_preserve(
        [label for button in buttons for label in button.get("labels", []) if "..." in label]
    )
    field_specs: list[dict[str, str]] = []
    for idx, item in enumerate(inputs[:4]):
        hint = form_hints[idx] if idx < len(form_hints) else ""
        field_specs.append(
            {
                "label": _infer_field_label(item.get("placeholder", ""), hint, item.get("class_name", "")),
                "placeholder": item.get("placeholder", ""),
                "hint": hint,
                "input_type": item.get("input_type", "text"),
            }
        )
    empty_logs_text = ""
    for item in text_pairs:
        lowered = item["class_name"].lower()
        if "log-empty" in lowered or lowered.endswith("empty"):
            empty_logs_text = item["text"]
            break
    section_labels = _unique_preserve(
        _class_to_label(item["class_name"])
        for item in text_pairs
        if any(token in item["class_name"].lower() for token in ("header", "logs", "tags", "form", "buttons"))
    )
    blocked = {title, subtitle, *primary_actions, *transient_actions, *[x["placeholder"] for x in field_specs], *form_hints}
    status_messages = _unique_preserve(
        [
            token
            for token in (message_literals + ternary_literals + literals)
            if token and token not in blocked and len(token) <= 48
        ]
    )[:8]
    if not (field_specs or primary_actions or status_messages or empty_logs_text or section_labels):
        return None
    return {
        "template_kind": "generic_dialog_sfc",
        "model": {
            "type": "structured_component",
            "title": title,
            "source_file": source_file,
            "subtitle": subtitle,
            "section_labels": [label for label in section_labels if label and label != title][:6],
            "action_labels": primary_actions[:6],
            "class_refs": class_refs[:10],
            "editor_names": [],
            "editor_descriptions": {},
            "form_fields": [item["label"] for item in field_specs],
            "field_specs": field_specs,
            "form_section_title": "Form",
            "status_messages": status_messages,
            "primary_actions": primary_actions[:6],
            "input_placeholders": [item["placeholder"] for item in field_specs if item.get("placeholder")],
            "form_hints": form_hints[:6],
            "button_texts": _unique_preserve(primary_actions + transient_actions),
            "empty_logs_text": empty_logs_text,
            "status_section_title": "Status",
            "log_section_title": "Logs",
            "plan_labels": [],
            "price_points": [],
        },
    }
