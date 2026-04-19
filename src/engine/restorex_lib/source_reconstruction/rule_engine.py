from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from restorex_lib.fs_utils import read_text


def _normalize_feedback_template(text: str) -> str:
    return text.replace("${e}", "{editor}")


def _unique_preserve(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        token = str(value).strip()
        if token and token not in out:
            out.append(token)
    return out


def _subtract(values: list[str], blocked: list[str]) -> list[str]:
    blocked_set = {str(x).strip() for x in blocked if str(x).strip()}
    return [value for value in values if value not in blocked_set]


def _render_proxy_form_fields(form_fields: list[str], placeholders: list[str], hints: list[str]) -> str:
    items = []
    effective = form_fields[:3] or ["代理地址"]
    for idx, label in enumerate(effective):
        placeholder = placeholders[idx] if idx < len(placeholders) else label
        items.append(
            f"""      <label class="restorex-form-field">
        <span>{label}</span>
        <input type="text" placeholder="{placeholder}" />
      </label>"""
        )
    hint_markup = "\n".join(f'      <p class="restorex-form-hint">{hint}</p>' for hint in hints[:2])
    return "\n".join(items) + (f"\n{hint_markup}" if hint_markup else "")


def _render_field_specs(field_specs: list[dict[str, Any]], fallback_fields: list[str], placeholders: list[str], hints: list[str]) -> str:
    items = []
    if field_specs:
        for spec in field_specs[:3]:
            label = str(spec.get("label", "")).strip() or "字段"
            placeholder = str(spec.get("placeholder", "")).strip() or label
            input_type = str(spec.get("input_type", "")).strip() or "text"
            hint = str(spec.get("hint", "")).strip()
            block = f"""      <label class="restorex-form-field">
        <span>{label}</span>
        <input type="{input_type}" placeholder="{placeholder}" />
      </label>"""
            if hint:
                block += f'\n      <p class="restorex-form-hint">{hint}</p>'
            items.append(block)
        return "\n".join(items)
    return _render_proxy_form_fields(fallback_fields, placeholders, hints)


def _render_auth_form_fields(form_fields: list[str], placeholders: list[str]) -> str:
    items = []
    effective = form_fields[:3] or ["账号"]
    for idx, label in enumerate(effective):
        input_type = "password" if "密码" in label or "卡密" in label else "text"
        placeholder = placeholders[idx] if idx < len(placeholders) else label
        items.append(
            f"""      <label class="restorex-form-field">
        <span>{label}</span>
        <input type="{input_type}" placeholder="{placeholder}" />
      </label>"""
        )
    return "\n".join(items)


def _render_generic_dialog_component(
    *,
    name: str,
    title: str,
    props: list[str],
    emits: list[str],
    source_file: str,
    component_model: dict[str, Any],
    render_component_props_interface: Callable[[list[str]], str],
    render_component_emits_array: Callable[[list[str]], str],
) -> str:
    title = str(component_model.get("title", "")).strip() or title
    dialog_role = str(component_model.get("dialog_role", "generic")).strip() or "generic"
    emit_array = render_component_emits_array(emits)
    emit_visibility_sync = '  emit("update:visible", false);\n' if "update:visible" in emits else ""
    section_labels = _unique_preserve([str(x).strip() for x in component_model.get("section_labels", []) if str(x).strip()])
    action_labels = _unique_preserve([str(x).strip() for x in component_model.get("action_labels", []) if str(x).strip()])
    class_refs = [str(x).strip() for x in component_model.get("class_refs", []) if str(x).strip()]
    editor_names = [str(x).strip() for x in component_model.get("editor_names", []) if str(x).strip()]
    plan_labels = [str(x).strip() for x in component_model.get("plan_labels", []) if str(x).strip()]
    price_points = [str(x).strip() for x in component_model.get("price_points", []) if str(x).strip()]
    form_fields = _unique_preserve([str(x).strip() for x in component_model.get("form_fields", []) if str(x).strip()])
    field_specs = [dict(x) for x in component_model.get("field_specs", []) if isinstance(x, dict)]
    status_messages = _unique_preserve([str(x).strip() for x in component_model.get("status_messages", []) if str(x).strip()])
    primary_actions = _unique_preserve([str(x).strip() for x in component_model.get("primary_actions", []) if str(x).strip()])
    input_placeholders = _unique_preserve([str(x).strip() for x in component_model.get("input_placeholders", []) if str(x).strip()])
    form_hints = _unique_preserve([str(x).strip() for x in component_model.get("form_hints", []) if str(x).strip()])
    empty_logs_text = str(component_model.get("empty_logs_text", "")).strip()
    status_section_title = str(component_model.get("status_section_title", "")).strip() or "Status Messages"
    log_section_title = str(component_model.get("log_section_title", "")).strip() or "Logs"
    subtitle = str(component_model.get("subtitle", "")).strip() or "Auto-generated structured dialog from RestoreX analysis."
    section_labels = _subtract(section_labels, [title])
    status_messages = _subtract(status_messages, form_fields)
    if primary_actions:
        action_labels = _subtract(primary_actions, form_fields)
    else:
        action_labels = _subtract(action_labels, form_fields + status_messages)
    section_blocks = "\n".join(
        f'      <article class="restorex-block"><h3>{label}</h3><p>Recovered from source structure.</p></article>'
        for label in section_labels[:6]
    )
    section_markup = ""
    if section_blocks:
        section_markup = f"""
    <section class="restorex-grid">
{section_blocks}
    </section>"""
    action_buttons = "\n".join(
        f'      <button class="restorex-action" @click="emitClose()">{label}</button>'
        for label in action_labels[:6]
    ) or '      <button class="restorex-action" @click="emitClose()">Close</button>'
    editor_chips = "\n".join(f"      <li>{label}</li>" for label in editor_names[:8])
    plan_chips = "\n".join(f"      <li>{label}</li>" for label in plan_labels[:8])
    price_tags = "\n".join(f"      <code>{label}</code>" for label in price_points[:8])
    field_chips = "\n".join(f"      <li>{label}</li>" for label in form_fields[:8])
    status_chips = "\n".join(f"      <li>{label}</li>" for label in status_messages[:8])
    class_tags = "\n".join(f"      <code>{tag}</code>" for tag in class_refs[:10])
    form_markup = ""
    if dialog_role == "proxy":
        form_markup = f"""
    <section v-if="{str(bool(field_specs or form_fields or form_hints)).lower()}" class="restorex-panel">
      <h3>Proxy Form</h3>
      <div class="restorex-form">
{_render_field_specs(field_specs, form_fields, input_placeholders, form_hints)}
      </div>
    </section>"""
    elif dialog_role == "auth":
        form_markup = f"""
    <section v-if="{str(bool(field_specs or form_fields)).lower()}" class="restorex-panel">
      <h3>Account Form</h3>
      <div class="restorex-form">
{_render_auth_form_fields(form_fields, input_placeholders)}
      </div>
    </section>"""
    else:
        form_markup = f"""
    <section v-if="{str(bool(form_fields)).lower()}" class="restorex-panel">
      <h3>Fields</h3>
      <ul class="restorex-list">
{field_chips or '      <li>No recovered fields</li>'}
      </ul>
    </section>"""
    return f"""<script setup lang="ts">
interface {name}Props {{
{render_component_props_interface(props)}
}}

const props = withDefaults(defineProps<{name}Props>(), {{
  visible: false,
}});

const emit = defineEmits([{emit_array}]);

function emitClose() {{
{emit_visibility_sync}  emit("close");
}}
</script>

<template>
  <section v-if="props.visible" class="restorex-dialog-shell restorex-structured-dialog">
    <header class="restorex-dialog-header">
      <div>
        <h2>{title}</h2>
        <p class="restorex-note">{subtitle}</p>
      </div>
      <button class="restorex-close" @click="emitClose">x</button>
    </header>
    <p class="restorex-source">Source: {source_file}</p>
{section_markup}
    <section v-if="{str(bool(editor_names)).lower()}" class="restorex-panel">
      <h3>Editors</h3>
      <ul class="restorex-list">
{editor_chips or '      <li>No editor hints</li>'}
      </ul>
    </section>
    <section v-if="{str(bool(plan_labels or price_points)).lower()}" class="restorex-panel">
      <h3>Plans</h3>
      <ul class="restorex-list">
{plan_chips or '      <li>No plan labels detected</li>'}
      </ul>
      <div class="restorex-tags">
{price_tags or '      <code>no-price-points</code>'}
      </div>
    </section>
{form_markup}
    <section v-if="{str(bool(status_messages)).lower()}" class="restorex-panel">
      <h3>{status_section_title}</h3>
      <ul class="restorex-list">
{status_chips or '      <li>No status messages detected</li>'}
      </ul>
    </section>
    <section v-if="{str(bool(empty_logs_text)).lower()}" class="restorex-panel">
      <h3>{log_section_title}</h3>
      <p class="restorex-note">{empty_logs_text}</p>
    </section>
    <section class="restorex-panel">
      <h3>Class References</h3>
      <div class="restorex-tags">
{class_tags or '      <code>no-class-refs</code>'}
      </div>
    </section>
    <div class="restorex-actions">
{action_buttons}
    </div>
  </section>
</template>
"""


def build_component_model_from_rules(
    *,
    name: str,
    source_text: str,
    main_text: str,
    rules: dict[str, Any],
) -> dict[str, Any]:
    component_rules = dict(rules.get("special_component_rules", {})).get(name)
    if not isinstance(component_rules, dict):
        return {}
    model = dict(component_rules.get("model", {}))
    model["template_kind"] = str(component_rules.get("template_kind", "")).strip()
    model["template_path"] = str(component_rules.get("template_path", "")).strip()
    extract_rules = dict(component_rules.get("extract", {}))
    if not extract_rules:
        return model

    desc_block_pattern = str(extract_rules.get("editor_descriptions_block_regex", "")).strip()
    desc_item_pattern = str(extract_rules.get("editor_description_item_regex", "")).strip()
    if desc_block_pattern and desc_item_pattern:
        descriptions: dict[str, str] = {}
        match = re.search(desc_block_pattern, source_text)
        if match:
            block = match.group(1)
            for editor, desc in re.findall(desc_item_pattern, block):
                descriptions[editor] = " ".join(line.strip() for line in desc.splitlines() if line.strip())
        model["editor_descriptions"] = descriptions

    for feature_key, marker in dict(model.get("feature_markers", {})).items():
        model[feature_key] = bool(marker and marker in source_text)

    section_labels = [label for label in list(model.get("section_labels", [])) if isinstance(label, str) and label in source_text]
    if section_labels:
        model["section_labels"] = section_labels
    action_labels = [label for label in list(model.get("action_labels", [])) if isinstance(label, str) and label in source_text]
    if action_labels:
        model["action_labels"] = action_labels

    tutorial_urls: dict[str, str] = {}
    url_block_pattern = str(extract_rules.get("tutorial_urls_block_regex", "")).strip()
    url_item_pattern = str(extract_rules.get("tutorial_urls_item_regex", "")).strip()
    if main_text and url_block_pattern and url_item_pattern:
        match = re.search(url_block_pattern, main_text)
        if match:
            for editor, url in re.findall(url_item_pattern, match.group(1)):
                tutorial_urls[editor] = url
    model["tutorial_urls"] = tutorial_urls

    feedback_patterns = dict(extract_rules.get("feedback_patterns", {}))
    feedback_model: dict[str, Any] = {}
    for key, pattern in feedback_patterns.items():
        match = re.search(str(pattern), main_text)
        if not match:
            continue
        groups = [_normalize_feedback_template(g.strip()) for g in match.groups() if g is not None]
        feedback_model[key] = groups
    if "codex_confirm_uninstall" in feedback_model:
        feedback_model["codex_confirm_uninstall_content"] = list(model.get("codex_confirm_uninstall_content", []))
    model["feedback_model"] = feedback_model
    return model


def render_component_from_rules(
    *,
    workspace: Path,
    name: str,
    title: str,
    props: list[str],
    emits: list[str],
    source_file: str,
    component_model: dict[str, Any],
    render_component_props_interface: Callable[[list[str]], str],
    render_component_emits_array: Callable[[list[str]], str],
) -> str:
    template_kind = str(component_model.get("template_kind", "")).strip()
    template_path = str(component_model.get("template_path", "")).strip()
    if template_kind == "generic_dialog_sfc":
        return _render_generic_dialog_component(
            name=name,
            title=title,
            props=props,
            emits=emits,
            source_file=source_file,
            component_model=component_model,
            render_component_props_interface=render_component_props_interface,
            render_component_emits_array=render_component_emits_array,
        )
    if template_kind != "project_template" or not template_path:
        return ""
    template_file = workspace / template_path
    if not template_file.is_file():
        return ""
    emit_visibility_sync = '  emit("update:visible", false);\n' if "update:visible" in emits else ""
    replacements = {
        "{{NAME}}": name,
        "{{TITLE}}": title,
        "{{SOURCE_FILE}}": source_file,
        "{{PROP_INTERFACE}}": render_component_props_interface(props),
        "{{EMIT_ARRAY}}": render_component_emits_array(emits),
        "{{EMIT_VISIBILITY_SYNC}}": emit_visibility_sync,
        "{{EDITOR_DESC_LITERAL}}": json.dumps(dict(component_model.get("editor_descriptions", {})), ensure_ascii=False, indent=2),
        "{{TUTORIAL_URLS_LITERAL}}": json.dumps(dict(component_model.get("tutorial_urls", {})), ensure_ascii=False, indent=2),
        "{{FEEDBACK_MODEL_LITERAL}}": json.dumps(dict(component_model.get("feedback_model", {})), ensure_ascii=False, indent=2),
    }
    text = read_text(template_file)
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def render_store_from_rules(
    *,
    workspace: Path,
    store_id: str,
    replacements: dict[str, str],
    rules: dict[str, Any],
) -> str:
    store_rules = dict(rules.get("special_store_rules", {})).get(store_id)
    if not isinstance(store_rules, dict):
        return ""
    template_kind = str(store_rules.get("template_kind", "")).strip()
    template_path = str(store_rules.get("template_path", "")).strip()
    if template_kind != "project_template" or not template_path:
        return ""
    template_file = workspace / template_path
    if not template_file.is_file():
        return ""
    text = read_text(template_file)
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def render_composable_from_rules(
    *,
    workspace: Path,
    composable_id: str,
    replacements: dict[str, str],
    rules: dict[str, Any],
) -> str:
    composable_rules = dict(rules.get("special_composable_rules", {})).get(composable_id)
    if not isinstance(composable_rules, dict):
        return ""
    template_kind = str(composable_rules.get("template_kind", "")).strip()
    template_path = str(composable_rules.get("template_path", "")).strip()
    if template_kind != "project_template" or not template_path:
        return ""
    template_file = workspace / template_path
    if not template_file.is_file():
        return ""
    text = read_text(template_file)
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text
