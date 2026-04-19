#!/usr/bin/env python3
"""指纹包发布命令 - 将项目学习到的指纹发布到 Gitee 供跨项目复用。

指纹包是跨项目通用的知识库，通过分析多个项目的还原结果提取共性模式。
"""
from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any
from datetime import datetime

from restorex_lib.fs_utils import read_json, write_json


def _hash_fingerprint(pack_data: dict) -> str:
    """计算指纹包哈希，用于版本控制。"""
    content = json.dumps(pack_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def validate_fingerprint_pack(pack_path: Path) -> tuple[bool, list[str]]:
    """验证指纹包格式正确。"""
    issues = []
    
    try:
        data = read_json(pack_path)
    except Exception as e:
        return False, [f"Invalid JSON: {e}"]
    
    # 检查必需字段
    if "library_match_rules" not in data and "third_party_fingerprints" not in data:
        issues.append("Missing 'library_match_rules' or 'third_party_fingerprints'")
    
    if "version" not in data:
        issues.append("Missing 'version' field")
    
    # 检查数据结构
    if "third_party_fingerprints" in data:
        for i, fp in enumerate(data["third_party_fingerprints"]):
            if "library" not in fp:
                issues.append(f"Fingerprint {i}: missing 'library' field")
            if "match" not in fp:
                issues.append(f"Fingerprint {i}: missing 'match' field")
    
    return len(issues) == 0, issues


def _load_existing_fingerprint_ids(workspace: Path) -> set[str]:
    """加载已存在的指纹包 ID，避免重复创建。"""
    existing_ids = set()
    
    # 1. 检查远程指纹
    remote_dir = workspace / "cache" / "remote" / "fingerprint_packs"
    if remote_dir.is_dir():
        for fp in remote_dir.rglob("*.json"):
            existing_ids.add(fp.stem)
    
    # 2. 检查 spec 指纹
    spec_dir = workspace / "spec" / "fingerprint_packs"
    if spec_dir.is_dir():
        for fp in spec_dir.rglob("*.json"):
            existing_ids.add(fp.stem)
    
    # 3. 检查已学习的 AI 指纹
    ai_dir = workspace / "cache" / "ai_generated" / "fingerprints"
    if ai_dir.is_dir():
        for fp in ai_dir.glob("*.json"):
            existing_ids.add(fp.stem)
    
    return existing_ids


def extract_fingerprints_from_project(
    workspace: Path,
    run_id: str,
    min_confidence: float = 0.8,
    min_occurrence: int = 2
) -> dict[str, Any]:
    """从项目还原结果中提取通用指纹。
    
    提取条件：
    - 还原置信度 >= min_confidence
    - 在多个文件中出现（出现次数 >= min_occurrence）
    - 不是项目特定的业务逻辑
    - 不是已存在的通用指纹（去重）
    
    Returns:
        {pack_name: pack_data}
    """
    packs = {}
    
    # 获取已存在的指纹 ID，避免重复
    existing_ids = _load_existing_fingerprint_ids(workspace)
    if existing_ids:
        print(f"  Found {len(existing_ids)} existing fingerprint packs, will skip duplicates")
    
    # 1. 从 library_matches.json 提取第三方库指纹
    lib_matches_path = workspace / "output" / run_id / "analysis" / "library_matches.json"
    if lib_matches_path.is_file():
        lib_matches = read_json(lib_matches_path)
        for match in lib_matches.get("matches", []):
            if match.get("confidence", 0) >= min_confidence:
                lib_name = match.get("library", "unknown")
                pack_name = f"vendor_{lib_name.lower().replace(' ', '_')}"
                
                # 跳过已存在的指纹
                if pack_name in existing_ids:
                    print(f"  Skipping {pack_name}: already exists")
                    continue
                
                if pack_name not in packs:
                    packs[pack_name] = {
                        "version": "1.0",
                        "library_match_rules": {},
                        "third_party_fingerprints": [],
                        "signal_rules": [],
                        "extracted_from": [run_id],
                        "extracted_at": datetime.now().isoformat(),
                    }
                
                # 添加指纹规则
                fp = {
                    "library": lib_name,
                    "kind": match.get("kind", "vendor_library"),
                    "confidence": "high" if match["confidence"] >= 0.9 else "medium",
                    "match": match.get("match_pattern", {"path_contains": [lib_name.lower()]}),
                    "evidence": match.get("evidence_signals", []),
                }
                packs[pack_name]["third_party_fingerprints"].append(fp)
    
    # 2. 从 evidence_matrix.json 提取框架模式
    evidence_path = workspace / "output" / run_id / "analysis" / "evidence_matrix.json"
    if evidence_path.is_file():
        evidence = read_json(evidence_path)
        
        # 提取高频出现的命名模式
        symbol_patterns = {}
        for item in evidence.get("items", []):
            source = item.get("source", "")
            if "pinia" in source.lower():
                symbol_patterns.setdefault("state_pinia", []).append(item)
            elif "vuex" in source.lower():
                symbol_patterns.setdefault("state_vuex", []).append(item)
            elif "zustand" in source.lower():
                symbol_patterns.setdefault("state_zustand", []).append(item)
        
        # 为高频模式创建指纹包
        for pack_name, items in symbol_patterns.items():
            if len(items) >= min_occurrence:
                # 跳过已存在的指纹
                if pack_name in existing_ids:
                    print(f"  Skipping {pack_name}: already exists")
                    continue
                
                if pack_name not in packs:
                    packs[pack_name] = {
                        "version": "1.0",
                        "library_match_rules": {},
                        "third_party_fingerprints": [],
                        "signal_rules": [],
                        "extracted_from": [run_id],
                        "extracted_at": datetime.now().isoformat(),
                    }
                
                # 创建信号规则
                for item in items[:5]:  # 取前5个作为样本
                    signal = {
                        "signal": item.get("to", ""),
                        "match": {
                            "any": [
                                {"text_contains": [item.get("from", "")]},
                                {"text_contains": [item.get("to", "")]}
                            ]
                        },
                        "confidence": item.get("confidence", 0.8),
                    }
                    packs[pack_name]["signal_rules"].append(signal)
    
    return packs


def publish_fingerprints_to_gitee(
    workspace: Path,
    gitee_repo: str,
    branch: str = "main",
    category: str = "components",
    dry_run: bool = True
) -> tuple[bool, list[str]]:
    """发布指纹包到 Gitee。
    
    Args:
        workspace: RestoreX workspace
        gitee_repo: Gitee 仓库地址，如 "your-org/fingerprint-packs"
        branch: 目标分支
        category: 指纹包类别 (components/libraries/frameworks)
        dry_run: 是否仅预览，不实际推送
    
    Returns:
        (success, messages)
    """
    messages = []
    
    # 1. 收集要发布的指纹包
    source_dir = workspace / "cache" / "ai_generated" / "fingerprints"
    if not source_dir.is_dir():
        return False, [f"Source directory not found: {source_dir}"]
    
    packs_to_publish = []
    for pack_file in source_dir.glob("*.json"):
        ok, issues = validate_fingerprint_pack(pack_file)
        if ok:
            packs_to_publish.append(pack_file)
        else:
            messages.append(f"Skipped {pack_file.name}: {', '.join(issues)}")
    
    if not packs_to_publish:
        return False, ["No valid fingerprint packs to publish"] + messages
    
    messages.append(f"Found {len(packs_to_publish)} packs to publish")
    
    if dry_run:
        for pack in packs_to_publish:
            data = read_json(pack)
            messages.append(f"  [DRY-RUN] {pack.name}: {data.get('version', 'N/A')}")
        return True, messages
    
    # 2. 克隆或更新 Gitee 仓库
    temp_dir = workspace / ".workflow" / "temp_gitee"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    repo_dir = temp_dir / "fingerprint-packs"
    
    try:
        if repo_dir.is_dir():
            # 更新现有仓库
            subprocess.run(
                ["git", "-C", str(repo_dir), "pull", "origin", branch],
                check=True, capture_output=True
            )
        else:
            # 克隆仓库
            subprocess.run(
                ["git", "clone", f"https://gitee.com/{gitee_repo}.git", str(repo_dir)],
                check=True, capture_output=True
            )
        
        # 3. 复制指纹包到目标目录
        target_dir = repo_dir / "spec" / "fingerprint_packs" / category
        target_dir.mkdir(parents=True, exist_ok=True)
        
        for pack_file in packs_to_publish:
            target_file = target_dir / pack_file.name
            
            # 合并或覆盖
            if target_file.is_file():
                existing = read_json(target_file)
                new_data = read_json(pack_file)
                
                # 简单合并：取并集
                merged = _merge_fingerprint_packs(existing, new_data)
                write_json(target_file, merged)
                messages.append(f"  Merged: {pack_file.name}")
            else:
                import shutil
                shutil.copy2(pack_file, target_file)
                messages.append(f"  Added: {pack_file.name}")
        
        # 4. 提交并推送
        subprocess.run(
            ["git", "-C", str(repo_dir), "add", "."],
            check=True, capture_output=True
        )
        
        commit_msg = f"Update fingerprint packs from {workspace.name} at {datetime.now().isoformat()}"
        subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", commit_msg],
            check=True, capture_output=True
        )
        
        subprocess.run(
            ["git", "-C", str(repo_dir), "push", "origin", branch],
            check=True, capture_output=True
        )
        
        messages.append(f"Published to gitee.com/{gitee_repo} ({branch})")
        return True, messages
        
    except subprocess.CalledProcessError as e:
        return False, messages + [f"Git operation failed: {e}"]
    except Exception as e:
        return False, messages + [f"Publish failed: {e}"]


def _merge_fingerprint_packs(existing: dict, new: dict) -> dict:
    """合并两个指纹包，取并集。"""
    merged = {
        "version": existing.get("version", "1.0"),
        "merged_at": datetime.now().isoformat(),
    }
    
    # 合并 library_match_rules
    if "library_match_rules" in existing or "library_match_rules" in new:
        merged["library_match_rules"] = existing.get("library_match_rules", {})
        merged["library_match_rules"].update(new.get("library_match_rules", {}))
    
    # 合并 third_party_fingerprints（去重）
    if "third_party_fingerprints" in existing or "third_party_fingerprints" in new:
        existing_fps = {fp.get("library", ""): fp for fp in existing.get("third_party_fingerprints", [])}
        for fp in new.get("third_party_fingerprints", []):
            lib = fp.get("library", "")
            if lib not in existing_fps:
                existing_fps[lib] = fp
        merged["third_party_fingerprints"] = list(existing_fps.values())
    
    # 合并 signal_rules（去重）
    if "signal_rules" in existing or "signal_rules" in new:
        existing_signals = {s.get("signal", ""): s for s in existing.get("signal_rules", [])}
        for s in new.get("signal_rules", []):
            sig = s.get("signal", "")
            if sig not in existing_signals:
                existing_signals[sig] = s
        merged["signal_rules"] = list(existing_signals.values())
    
    return merged


# CLI 命令函数

def cmd_publish_fingerprints(
    workspace: Path,
    dry_run: bool = True,
    gitee_repo: str = "",
    branch: str = "main",
    category: str = "components"
) -> None:
    """发布指纹包 CLI 命令。"""
    print(f"Publishing fingerprints from {workspace}")
    print(f"  Mode: {'dry-run' if dry_run else 'live'}")
    
    if not gitee_repo:
        # 从配置读取
        config_path = workspace / "cache" / "project" / "fingerprint_publish.yaml"
        if config_path.is_file():
            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f)
            gitee_repo = config.get("publish", {}).get("repo", "")
            branch = config.get("publish", {}).get("branch", "main")
    
    if not gitee_repo:
        print("Error: Gitee repo not specified and not found in config")
        return
    
    success, messages = publish_fingerprints_to_gitee(
        workspace, gitee_repo, branch, category, dry_run
    )
    
    for msg in messages:
        print(f"  {msg}")
    
    if success:
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Publish {'successful' if success else 'failed'}")
    
    return success


def cmd_extract_fingerprints(
    workspace: Path,
    run_id: str,
    output_dir: str = "",
    min_confidence: float = 0.8
) -> None:
    """从项目提取指纹 CLI 命令。"""
    print(f"Extracting fingerprints from run {run_id}")
    
    packs = extract_fingerprints_from_project(
        workspace, run_id, min_confidence=min_confidence
    )
    
    if not packs:
        print("No fingerprints extracted (insufficient confidence or patterns)")
        return
    
    # 确定输出目录
    if output_dir:
        target_dir = Path(output_dir)
    else:
        target_dir = workspace / "cache" / "ai_generated" / "fingerprints"
    
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存指纹包
    for pack_name, pack_data in packs.items():
        pack_file = target_dir / f"{pack_name}.json"
        pack_data["_meta"] = {
            "extracted_from": run_id,
            "extracted_at": datetime.now().isoformat(),
            "hash": _hash_fingerprint(pack_data),
        }
        write_json(pack_file, pack_data)
        print(f"  Extracted: {pack_name} -> {pack_file}")
    
    print(f"\nTotal: {len(packs)} fingerprint packs")
    return len(packs)
