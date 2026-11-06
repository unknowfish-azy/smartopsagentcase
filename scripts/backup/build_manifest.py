#!/usr/bin/env python3
"""OPS-13：生成可复核的备份清单（smartops-backup/v1）。

只计算事实：文件/目录的 sha256、字节数与条目数，不读取、不打印任何凭据内容。
清单由后端 BackupService 导入，隔离恢复演练时用同一算法核对恢复副本。

用法示例：
    python scripts/backup/build_manifest.py \
      --set prod-core --output backup/manifest.json \
      --component DATABASE=backup/smartops.sql.gz \
      --component ATTACHMENTS=backup/uploads \
      --component KNOWLEDGE_MANIFEST=backup/knowledge.json \
      --component AUDIT=backup/audit \
      --component KEYS=backup/keys

目录的摘要 = 按相对路径排序后的 "relpath:sha256" 行拼接再取 sha256，可在恢复副本上复算。
缺少必需组件时默认退出码 2；确需部分备份时加 --allow-partial，后端会把集合标记为不完整。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

SCHEMA = "smartops-backup/v1"
REQUIRED_COMPONENTS = ("DATABASE", "ATTACHMENTS", "KNOWLEDGE_MANIFEST", "AUDIT", "KEYS")


def sha256_stream(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return sha256_stream(iter(lambda: handle.read(1024 * 1024), b""))


def digest_directory(root: Path) -> Tuple[str, int, int]:
    entries: List[str] = []
    total_bytes = 0
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(root).as_posix()
        entries.append(f"{relative}:{sha256_file(item)}")
        total_bytes += item.stat().st_size
    aggregate = sha256_stream(["\n".join(entries).encode("utf-8")])
    return aggregate, total_bytes, len(entries)


def digest_path(path: Path) -> Tuple[str, int, int]:
    if path.is_dir():
        return digest_directory(path)
    if path.is_file():
        return sha256_file(path), path.stat().st_size, 1
    raise ValueError(f"组件路径不存在或不是文件/目录: {path}")


def parse_components(values: Iterable[str]) -> Dict[str, Path]:
    components: Dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--component 需要 NAME=PATH 形式: {value}")
        name, raw_path = value.split("=", 1)
        component = name.strip().upper()
        if component not in REQUIRED_COMPONENTS:
            raise ValueError(f"未知组件 {component}，允许: {', '.join(REQUIRED_COMPONENTS)}")
        if component in components:
            raise ValueError(f"组件重复: {component}")
        path = Path(raw_path.strip())
        if not path.exists():
            raise ValueError(f"组件路径不存在: {path}")
        components[component] = path
    return components


def parse_captured_at(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"captured-at 不是 ISO-8601 时间: {value}") from error
    if parsed.tzinfo is None:
        raise ValueError("captured-at 必须带时区（例如 Z 或 +08:00）")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_manifest(set_name: str, captured_at: str, components: Dict[str, Path]) -> dict:
    artifacts = []
    seen_ids = set()
    for component in REQUIRED_COMPONENTS:
        path = components.get(component)
        if path is None:
            continue
        sha256, size, count = digest_path(path)
        artifact_id = path.name
        if not artifact_id:
            artifact_id = component.lower()
        if artifact_id in seen_ids:
            raise ValueError(f"制品 ID 冲突: {artifact_id}（请为不同组件使用不同文件名）")
        seen_ids.add(artifact_id)
        artifacts.append({
            "artifactId": artifact_id,
            "component": component,
            "sourceUri": os.fspath(path),
            "sha256": sha256,
            "bytes": size,
            "itemCount": count,
        })
    return {
        "schema": SCHEMA,
        "set": set_name,
        "capturedAt": captured_at,
        "artifacts": artifacts,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 smartops-backup/v1 备份清单")
    parser.add_argument("--set", dest="set_name", required=True, help="恢复集合名称")
    parser.add_argument("--output", required=True, help="清单输出路径")
    parser.add_argument("--captured-at", default=None, help="采集时间（ISO-8601，默认当前 UTC）")
    parser.add_argument("--component", action="append", default=[], help="NAME=PATH，可重复")
    parser.add_argument("--allow-partial", action="store_true", help="允许缺少必需组件")
    args = parser.parse_args(argv)

    try:
        captured_at = parse_captured_at(args.captured_at)
        components = parse_components(args.component)
        missing = [name for name in REQUIRED_COMPONENTS if name not in components]
        if missing and not args.allow_partial:
            raise ValueError(f"缺少必需组件: {', '.join(missing)}（如确需部分备份请加 --allow-partial）")
        if not components:
            raise ValueError("至少需要一个 --component")
        manifest = build_manifest(args.set_name.strip(), captured_at, components)
    except ValueError as error:
        print(f"错误: {error}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for artifact in manifest["artifacts"]:
        print(f"{artifact['component']}: {artifact['artifactId']} "
              f"{artifact['bytes']} bytes / {artifact['itemCount']} items "
              f"sha256={artifact['sha256'][:12]}…", file=sys.stderr)
    print(f"清单已写入 {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
