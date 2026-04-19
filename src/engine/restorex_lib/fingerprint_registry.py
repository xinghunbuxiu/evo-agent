from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from restorex_lib.config_rules import deep_merge_dict
from restorex_lib.fs_utils import read_text


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(read_text(path))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _merge_registry_pack(merged: dict[str, Any], pack_obj: dict[str, Any]) -> dict[str, Any]:
    out = dict(merged)
    rules = pack_obj.get("library_match_rules", {})
    if isinstance(rules, dict):
        out["library_match_rules"] = deep_merge_dict(dict(out.get("library_match_rules", {})), rules)

    for key in ("third_party_fingerprints", "signal_rules", "framework_rules"):
        arr = pack_obj.get(key, [])
        if isinstance(arr, list):
            out.setdefault(key, [])
            out[key] = list(out[key]) + arr
    return out


def _dedupe_list_items(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for item in items:
        try:
            k = json.dumps(item, ensure_ascii=False, sort_keys=True)
        except Exception:
            k = str(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out


def _get_fingerprint_registry_path(workspace: Path) -> Path:
    """获取指纹注册表路径
    
    优先级：
    1. cache/remote/fingerprint_registry.json（远程同步，最新）
    2. spec/fingerprint_registry.json（项目本地）
    """
    remote_path = workspace / "cache" / "remote" / "fingerprint_registry.json"
    if remote_path.is_file():
        return remote_path
    return workspace / "spec" / "fingerprint_registry.json"


def _load_pack_paths_by_registry(workspace: Path) -> list[Path]:
    registry_path = _get_fingerprint_registry_path(workspace)
    if not registry_path.is_file():
        return []
    reg = _load_json(registry_path)
    packs = reg.get("packs", [])
    if not isinstance(packs, list):
        return []

    records: list[tuple[int, str, Path]] = []
    for item in packs:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled", True)):
            continue
        raw_path = str(item.get("path", "")).strip()
        if not raw_path:
            continue
        p = Path(raw_path)
        if not p.is_absolute():
            p = (workspace / p).resolve()
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        priority = int(item.get("priority", 100) or 100)
        item_id = str(item.get("id", p.stem))
        records.append((priority, item_id, p))
    records.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in records]


def load_fingerprint_registry(workspace: Path) -> dict[str, Any]:
    """
    加载"指纹规则总站"（插件化 pack）：
    - 来源1：cache/remote/fingerprint_packs/（远程同步）
    - 来源2：spec/fingerprint_packs/（项目本地）
    - 来源3：cache/ai_generated/fingerprints/（本项目学习）
    - 合并策略：按 priority 排序后 deep-merge
    """
    merged: dict[str, Any] = {
        "library_match_rules": {},
        "third_party_fingerprints": [],
        "signal_rules": [],
        "framework_rules": [],
    }
    
    # 收集所有指纹包路径
    pack_paths: list[Path] = []
    
    # 1. 从注册表加载（cache/remote/ 或 spec/）
    pack_paths.extend(_load_pack_paths_by_registry(workspace))
    
    # 2. 如果注册表为空，递归加载 cache/remote/fingerprint_packs/
    if not pack_paths:
        remote_packs = workspace / "cache" / "remote" / "fingerprint_packs"
        if remote_packs.is_dir():
            pack_paths.extend(sorted(
                remote_packs.rglob("*.json"),
                key=lambda p: str(p.relative_to(remote_packs))
            ))
    
    # 3. 加载 spec/fingerprint_packs/（项目本地）
    spec_packs = workspace / "spec" / "fingerprint_packs"
    if spec_packs.is_dir():
        pack_paths.extend(sorted(
            spec_packs.rglob("*.json"),
            key=lambda p: str(p.relative_to(spec_packs))
        ))
    
    # 4. 加载本项目学习的指纹（cache/ai_generated/fingerprints/）
    ai_fingerprints = workspace / "cache" / "ai_generated" / "fingerprints"
    if ai_fingerprints.is_dir():
        pack_paths.extend(sorted(ai_fingerprints.glob("*.json")))
    
    if not pack_paths:
        return merged

    for pack_path in pack_paths:
        pack_obj = _load_json(pack_path)
        if not pack_obj:
            continue
        merged = _merge_registry_pack(merged, pack_obj)

    # 规整结构：保证字段类型稳定，避免坏配置击穿主流程。
    for key in ("third_party_fingerprints", "signal_rules", "framework_rules"):
        if not isinstance(merged.get(key, []), list):
            merged[key] = []
        else:
            merged[key] = _dedupe_list_items(list(merged[key]))
    if not isinstance(merged.get("library_match_rules", {}), dict):
        merged["library_match_rules"] = {}
    return merged
