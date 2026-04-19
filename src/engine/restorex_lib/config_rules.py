from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from restorex_lib.fs_utils import read_text


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = read_text(path)
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        return {}
    except Exception:
        return {}


def load_json_required(path: Path) -> dict[str, Any]:
    """加载必须存在的配置文件，不存在或解析失败时直接报错。"""
    if not path.is_file():
        raise SystemExit(f"E_CONFIG: required spec file missing -> {path}")
    try:
        raw = read_text(path)
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        raise SystemExit(f"E_CONFIG: spec file is not a JSON object -> {path}")
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"E_CONFIG: failed to parse spec file {path}: {e}") from e


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge_dict(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class RuleConfig:
    forbidden_rename_tokens: set[str]
    generic_candidates: set[str]
    auto_rename_prefixes: tuple[str, ...]
    short_name_regex: str
    candidate_regex: str
    require_unique_mapping: bool
    require_high_confidence: bool
    allow_pair_semantic_high_unique_without_prefix: bool
    allow_pair_semantic_medium_brand_without_prefix: bool
    allow_pair_semantic_medium_prefix_two_char: bool
    allow_scope_medium_confidence: bool
    allow_pascal_short_service_rename: bool
    suspicious_short_len_max: int
    suspicious_replace_count_threshold: int
    block_suspicious_rename: bool
    global_apply_sources_allowlist: tuple[str, ...]
    chain_key_prefixes: tuple[str, ...]
    chain_skip_origin_labels: set[str]
    runtime_command_schemes: tuple[str, ...]
    chain_min_confidence: str
    chain_require_bridge_calls: bool
    chain_min_ui_refs: int
    profile_name: str


def load_rule_config(workspace: Path, profile_name: str = "strict") -> RuleConfig:
    """
    加载规则配置。
    - cache/remote/rename_rules.json 和 chain_rules.json 必须存在（首次运行时从服务器拉取）
    - cache/remote/profiles/<name>.json 可选，存在时覆盖对应字段
    - 不使用代码内置兜底值，所有默认值来自 cache/remote/ 文件
    """
    remote = workspace / "cache" / "remote"
    rename_obj = load_json_required(remote / "rename_rules.json")
    chain_obj = load_json_required(remote / "chain_rules.json")

    profile_obj = load_json_if_exists(remote / "profiles" / f"{profile_name}.json")
    if profile_obj:
        rename_obj = deep_merge_dict(rename_obj, profile_obj.get("rename_rules", {}))
        chain_obj = deep_merge_dict(chain_obj, profile_obj.get("chain_rules", {}))

    def _req_set(key: str, obj: dict[str, Any]) -> set[str]:
        v = obj.get(key)
        if not isinstance(v, list):
            raise SystemExit(f"E_CONFIG: rename_rules.json missing required list field: {key}")
        return {str(x) for x in v}

    def _req_tuple(key: str, obj: dict[str, Any]) -> tuple[str, ...]:
        v = obj.get(key)
        if not isinstance(v, list):
            raise SystemExit(f"E_CONFIG: spec file missing required list field: {key}")
        return tuple(str(x) for x in v)

    def _opt_set(key: str, obj: dict[str, Any], fallback: set[str]) -> set[str]:
        v = obj.get(key)
        if isinstance(v, list):
            return {str(x) for x in v}
        return fallback

    def _opt_tuple(key: str, obj: dict[str, Any], fallback: tuple[str, ...]) -> tuple[str, ...]:
        v = obj.get(key)
        if isinstance(v, list):
            return tuple(str(x) for x in v)
        return fallback

    constraints = rename_obj.get("apply_constraints", {}) if isinstance(rename_obj.get("apply_constraints"), dict) else {}
    suspicious_constraints = (
        rename_obj.get("suspicious_rename_constraints", {})
        if isinstance(rename_obj.get("suspicious_rename_constraints"), dict)
        else {}
    )
    chain_constraints = chain_obj.get("extract_constraints", {}) if isinstance(chain_obj.get("extract_constraints"), dict) else {}

    return RuleConfig(
        forbidden_rename_tokens=_req_set("forbidden_rename_tokens", rename_obj),
        generic_candidates=_req_set("generic_candidates", rename_obj),
        auto_rename_prefixes=_req_tuple("auto_rename_prefixes", rename_obj),
        short_name_regex=str(constraints.get("short_name_regex", r"^[a-z]{1,2}$")),
        candidate_regex=str(constraints.get("candidate_regex", r"^[A-Za-z_]\w{3,}$")),
        require_unique_mapping=bool(constraints.get("require_unique_mapping", True)),
        require_high_confidence=bool(constraints.get("require_high_confidence", True)),
        allow_pair_semantic_high_unique_without_prefix=bool(
            constraints.get("allow_pair_semantic_high_unique_without_prefix", False)
        ),
        allow_pair_semantic_medium_brand_without_prefix=bool(
            constraints.get("allow_pair_semantic_medium_brand_without_prefix", False)
        ),
        allow_pair_semantic_medium_prefix_two_char=bool(
            constraints.get("allow_pair_semantic_medium_prefix_two_char", False)
        ),
        allow_scope_medium_confidence=bool(
            constraints.get("allow_scope_medium_confidence", False)
        ),
        allow_pascal_short_service_rename=bool(
            constraints.get("allow_pascal_short_service_rename", False)
        ),
        suspicious_short_len_max=int(suspicious_constraints.get("short_len_max", 2)),
        suspicious_replace_count_threshold=int(suspicious_constraints.get("replace_count_threshold", 200)),
        block_suspicious_rename=bool(suspicious_constraints.get("block_in_apply", False)),
        global_apply_sources_allowlist=_req_tuple("global_apply_sources_allowlist", rename_obj),
        chain_key_prefixes=_req_tuple("bridge_call_key_prefixes", chain_obj),
        chain_skip_origin_labels=_req_set("skip_origin_labels_in_chain", chain_obj),
        runtime_command_schemes=_opt_tuple("runtime_command_schemes", chain_obj, ("plugin:", "tauri://")),
        chain_min_confidence=str(chain_constraints.get("min_confidence", "low")).lower(),
        chain_require_bridge_calls=bool(chain_constraints.get("require_bridge_calls", False)),
        chain_min_ui_refs=int(chain_constraints.get("min_ui_refs", 0)),
        profile_name=profile_name,
    )
