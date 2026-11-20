"""公开视觉训练数据的白名单下载与许可证登记。

为什么是"白名单"而不是爬虫：仓库 LICENSE 只覆盖代码，不覆盖图片与标注；
GitHub 批量抓取也受可接受使用政策限制。因此本脚本**只下载白名单里显式列出的
URL**，每条必须有许可证字段，否则拒绝。

    # 查看清单（含许可证状态）
    python scripts/fetch_public_vision_data.py --list

    # 只探测可达性，不下载
    python scripts/fetch_public_vision_data.py --probe

    # 下载白名单内的 https 条目（默认拒绝未核验/受限许可证）
    python scripts/fetch_public_vision_data.py --fetch all
    python scripts/fetch_public_vision_data.py --fetch openimages_v7_train_bbox_annotations

    # 手动获取的数据集（D-Fire / Roboflow / Kaggle）登记进许可证清单
    python scripts/fetch_public_vision_data.py --register D:/data/dfire.zip \
        --dataset D-Fire --license CC-BY-4.0 --license-url https://example/license \
        --class-map '{"fire": "fire_or_smoke", "smoke": "fire_or_smoke"}'

    # 校验本地文件没被替换/损坏
    python scripts/fetch_public_vision_data.py --verify

产物（默认 ai-service/data/vision/public/，已被 .gitignore 忽略）：
* SOURCES.jsonl —— 每条已获取文件的 url / license / sha256 / 获取时间，训练报告引用它；
* SOURCES.md    —— 同一份清单的人类可读版，答辩/评审可直接看。

三条硬约束：
1. 只允许 https，且拒绝重定向到 http 的响应；
2. 没有许可证字段、或许可证不在 allowlist 内，默认拒绝下载；
3. 不做任意 URL 抓取、不解压、不递归爬站。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

USER_AGENT = "SmartOpsAgent-vision-data-fetcher/1.0"
SCHEMA_VERSION = "smartops.vision_sources.v1"

DEFAULT_WHITELIST = Path(__file__).with_name("public_vision_sources.json")
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "vision" / "public"

# 只有这些许可证默认放行；CC-BY-SA 与 research-only 都需要显式 --allow-restricted
ALLOWED_LICENSES = {
    "CC0-1.0",
    "CC-BY-4.0",
    "CC-BY-3.0",
    "MIT",
    "Apache-2.0",
    "PDDL-1.0",
    "public-domain",
}

KINDS = {"images", "annotations", "dataset"}
DELIVERIES = {"http", "manual"}
ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


class WhitelistError(RuntimeError):
    """清单本身不合法（缺许可证 / url 非 https / id 重复）。"""


class FetchError(RuntimeError):
    """下载失败或触犯策略（超限、跳转非 https、许可证受限）。"""


# ---------------------------------------------------------------------------
# 清单
# ---------------------------------------------------------------------------


def load_whitelist(path: Path | str = DEFAULT_WHITELIST) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        raise WhitelistError(f"白名单不存在：{target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise WhitelistError("白名单里没有 sources")

    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for entry in sources:
        validate_entry(entry)
        if entry["id"] in seen:
            raise WhitelistError(f"id 重复：{entry['id']}")
        seen.add(entry["id"])
        entries.append(entry)
    return entries


def validate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise WhitelistError("条目必须是对象")

    required = ("id", "dataset", "kind", "delivery", "license", "license_url")
    missing = [key for key in required if not str(entry.get(key) or "").strip()]
    if missing:
        raise WhitelistError(f"{entry.get('id', '<no-id>')} 缺少字段：{', '.join(missing)}")

    if not ID_PATTERN.fullmatch(str(entry["id"])):
        raise WhitelistError(f"id 只能是小写字母/数字/下划线：{entry['id']}")
    if entry["kind"] not in KINDS:
        raise WhitelistError(f"{entry['id']} 的 kind 非法：{entry['kind']}")
    if entry["delivery"] not in DELIVERIES:
        raise WhitelistError(f"{entry['id']} 的 delivery 非法：{entry['delivery']}")
    if not isinstance(entry.get("class_map") or {}, dict):
        raise WhitelistError(f"{entry['id']} 的 class_map 必须是对象")

    if entry["delivery"] == "http":
        url = str(entry.get("url") or "")
        if not url.startswith("https://"):
            raise WhitelistError(f"{entry['id']} 的 url 必须是 https://（实际：{url or '<空>'}）")
        if not str(entry.get("filename") or "").strip():
            raise WhitelistError(f"{entry['id']} 缺少 filename")
    return entry


def license_allowed(license_id: str) -> bool:
    return str(license_id).strip() in ALLOWED_LICENSES


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    url: str,
    destination: Path,
    *,
    timeout: float = 60.0,
    max_bytes: int = 4 * 1024**3,
    opener: Any = None,
    chunk_size: int = 1 << 20,
) -> tuple[str, int]:
    """流式下载到 `<name>.part` 再改名；返回 (sha256, 字节数)。"""
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")

    digest = hashlib.sha256()
    total = 0
    try:
        with opener(request, timeout=timeout) as response:
            final_url = str(response.geturl())
            if not final_url.startswith("https://"):
                raise FetchError(f"重定向到非 https 地址：{final_url}")
            with partial.open("wb") as handle:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise FetchError(f"文件超过 max_bytes 上限（{max_bytes}）")
                    digest.update(chunk)
                    handle.write(chunk)
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return digest.hexdigest(), total


def fetch_entry(
    entry: dict[str, Any],
    out_dir: Path | str = DEFAULT_OUT,
    *,
    timeout: float = 60.0,
    max_bytes: int = 4 * 1024**3,
    allow_unverified: bool = False,
    allow_restricted: bool = False,
    opener: Any = None,
) -> dict[str, Any]:
    validate_entry(entry)
    out = Path(out_dir)

    if entry["delivery"] != "http":
        raise FetchError(f"{entry['id']} 是人工获取条目，请下载后用 --register 登记")
    if not license_allowed(entry["license"]) and not allow_restricted:
        raise FetchError(
            f"{entry['id']} 的许可证 {entry['license']} 不在 allowlist 内；"
            "人工核验后加 --allow-restricted 才能下载"
        )
    if not entry.get("verified") and not allow_unverified:
        raise FetchError(f"{entry['id']} 标记为未核验；先 --probe 确认，再加 --allow-unverified")

    destination = out / entry["id"] / entry["filename"]
    sha256, size = download(
        entry["url"],
        destination,
        timeout=timeout,
        max_bytes=max_bytes,
        opener=opener,
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": entry["id"],
        "dataset": entry["dataset"],
        "kind": entry["kind"],
        "source": "whitelist",
        "url": entry["url"],
        "license": entry["license"],
        "license_url": entry["license_url"],
        "class_map": entry.get("class_map") or {},
        "path": destination.relative_to(out).as_posix(),
        "sha256": sha256,
        "bytes": size,
        "fetched_at": _now(),
    }
    upsert_record(record, out)
    render_markdown(out)
    return record


# ---------------------------------------------------------------------------
# 手动登记与校验
# ---------------------------------------------------------------------------


def register_file(
    file_path: Path | str,
    *,
    dataset: str,
    license_id: str,
    license_url: str,
    class_map: dict[str, str] | None = None,
    out_dir: Path | str = DEFAULT_OUT,
    allow_restricted: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """登记一个手工获取的数据集（Roboflow / Kaggle / D-Fire 等）。不复制文件。"""
    source = Path(file_path)
    if not source.is_file():
        raise FetchError(f"文件不存在：{source}")
    if not license_allowed(license_id) and not allow_restricted:
        raise FetchError(
            f"许可证 {license_id} 不在 allowlist 内；核验后加 --allow-restricted 才能登记"
        )

    out = Path(out_dir)
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": f"{_slug(dataset)}_{_slug(source.stem)}",
        "dataset": dataset,
        "kind": "dataset",
        "source": "manual",
        "url": None,
        "license": license_id,
        "license_url": license_url,
        "class_map": class_map or {},
        "path": str(source.resolve()),
        "sha256": sha256_file(source),
        "bytes": source.stat().st_size,
        "fetched_at": _now(),
        "notes": notes,
    }
    upsert_record(record, out)
    render_markdown(out)
    return record


def load_records(out_dir: Path | str = DEFAULT_OUT) -> list[dict[str, Any]]:
    path = Path(out_dir) / "SOURCES.jsonl"
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"{path} 第 {lineno} 行不是合法 JSON：{error}") from error
    return records


def upsert_record(record: dict[str, Any], out_dir: Path | str = DEFAULT_OUT) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = [item for item in load_records(out) if item.get("id") != record["id"]]
    records.append(record)
    records.sort(key=lambda item: str(item.get("id")))
    path = out / "SOURCES.jsonl"
    path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )


def verify_records(out_dir: Path | str = DEFAULT_OUT) -> list[dict[str, Any]]:
    out = Path(out_dir)
    reports: list[dict[str, Any]] = []
    for record in load_records(out):
        path = Path(record["path"])
        if not path.is_absolute():
            path = out / path
        if not path.is_file():
            reports.append({"id": record.get("id"), "path": str(path), "status": "MISSING"})
            continue
        actual = sha256_file(path)
        status = "OK" if actual == record.get("sha256") else "CHANGED"
        reports.append({
            "id": record.get("id"),
            "path": str(path),
            "status": status,
            "expected": record.get("sha256"),
            "actual": actual,
        })
    return reports


def render_markdown(out_dir: Path | str = DEFAULT_OUT) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = load_records(out)
    lines = [
        "# 视觉训练数据来源与许可证清单",
        "",
        "> 本文件由 `scripts/fetch_public_vision_data.py` 自动生成，请勿手改。",
        "> 记录文件：`SOURCES.jsonl`。训练报告须引用本清单。",
        "",
    ]
    if not records:
        lines.append("（暂无已获取数据）")
    else:
        lines.extend([
            "| 数据集 | 文件 | 许可证 | 大小 | SHA-256 | 获取时间 |",
            "|---|---|---|---|---|---|",
        ])
        for record in records:
            digest = str(record.get("sha256") or "")
            size = int(record.get("bytes") or 0)
            lines.append(
                "| {dataset} | {name} | {license} | {size} | `{digest}` | {at} |".format(
                    dataset=record.get("dataset", ""),
                    name=Path(str(record.get("path"))).name,
                    license=record.get("license", ""),
                    size=_human_size(size),
                    digest=digest[:12] + ("…" if len(digest) > 12 else ""),
                    at=record.get("fetched_at", ""),
                )
            )
        lines.extend([
            "",
            "许可证全文见各行 `license_url`（记录在 SOURCES.jsonl）。",
        ])
    text = "\n".join(lines) + "\n"
    (out / "SOURCES.md").write_text(text, encoding="utf-8")
    return str(out / "SOURCES.md")


# ---------------------------------------------------------------------------
# 探测
# ---------------------------------------------------------------------------


def probe(entry: dict[str, Any], *, timeout: float = 15.0, opener: Any = None) -> dict[str, Any]:
    """HEAD 探测可达性；不下载、不写清单。"""
    opener = opener or urllib.request.urlopen
    validate_entry(entry)
    if entry["delivery"] != "http":
        return {"id": entry["id"], "status": "MANUAL", "detail": "人工获取条目，跳过探测"}

    request = urllib.request.Request(entry["url"], method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=timeout) as response:
            size = response.headers.get("Content-Length")
            return {
                "id": entry["id"],
                "status": "OK",
                "http_status": getattr(response, "status", None),
                "content_length": int(size) if size and size.isdigit() else None,
                "final_url": str(response.geturl()),
            }
    except Exception as error:  # 探测失败不抛，交给调用方汇总
        return {"id": entry["id"], "status": "FAILED", "detail": str(error)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return cleaned or "item"


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


def _print_table(entries: Iterable[dict[str, Any]]) -> None:
    print(f"{'id':46} {'delivery':9} {'license':14} {'核验':4} dataset")
    for entry in entries:
        print(
            f"{entry['id']:46} {entry['delivery']:9} {entry['license']:14} "
            f"{'是' if entry.get('verified') else '否':4} {entry['dataset']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="公开视觉数据白名单下载与许可证登记")
    parser.add_argument("--whitelist", default=str(DEFAULT_WHITELIST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-bytes", type=int, default=4 * 1024**3)
    parser.add_argument("--allow-unverified", action="store_true", help="允许下载未探测过的条目")
    parser.add_argument("--allow-restricted", action="store_true", help="允许受限/研究用途许可证")
    parser.add_argument("--list", action="store_true", help="列出白名单")
    parser.add_argument("--probe", action="store_true", help="HEAD 探测 URL 可达性")
    parser.add_argument("--fetch", nargs="+", metavar="ID", help="下载指定 id 或 all")
    parser.add_argument("--verify", action="store_true", help="校验已下载文件的 sha256")
    parser.add_argument("--render", action="store_true", help="从 SOURCES.jsonl 重生成 SOURCES.md")
    parser.add_argument("--register", metavar="PATH", help="登记手工获取的数据文件")
    parser.add_argument("--dataset", default="", help="--register 用的数据集名")
    parser.add_argument("--license", dest="license_id", default="", help="--register 用的 SPDX 许可证")
    parser.add_argument("--license-url", default="", help="--register 用的许可证地址")
    parser.add_argument("--class-map", default="{}", help="--register 用的类别映射 JSON")
    parser.add_argument("--notes", default="", help="--register 备注")
    args = parser.parse_args(argv)

    try:
        entries = load_whitelist(args.whitelist)
    except (WhitelistError, json.JSONDecodeError) as error:
        print(f"[whitelist] {error}", file=sys.stderr)
        return 2

    if args.list:
        _print_table(entries)
        return 0

    if args.probe:
        failures = 0
        for entry in entries:
            result = probe(entry, timeout=min(args.timeout, 15.0))
            print(json.dumps(result, ensure_ascii=False))
            if result["status"] == "FAILED":
                failures += 1
        return 1 if failures else 0

    if args.fetch:
        by_id = {entry["id"]: entry for entry in entries}
        ids = list(by_id) if "all" in args.fetch else args.fetch
        unknown = [item for item in ids if item not in by_id]
        if unknown:
            print(f"[fetch] 不在白名单内：{', '.join(unknown)}", file=sys.stderr)
            return 2
        failures = 0
        for source_id in ids:
            entry = by_id[source_id]
            if entry["delivery"] == "manual":
                print(f"[fetch] 跳过 {source_id}：人工获取条目，请用 --register")
                continue
            try:
                record = fetch_entry(
                    entry,
                    args.out,
                    timeout=args.timeout,
                    max_bytes=args.max_bytes,
                    allow_unverified=args.allow_unverified,
                    allow_restricted=args.allow_restricted,
                )
                print(f"[fetch] {source_id} -> {record['path']} ({_human_size(record['bytes'])})")
            except (FetchError, WhitelistError, OSError) as error:
                failures += 1
                print(f"[fetch] {source_id} 失败：{error}", file=sys.stderr)
        return 1 if failures else 0

    if args.register:
        if not (args.dataset and args.license_id and args.license_url):
            print("[register] 需要 --dataset --license --license-url", file=sys.stderr)
            return 2
        try:
            class_map = json.loads(args.class_map)
        except json.JSONDecodeError as error:
            print(f"[register] --class-map 不是合法 JSON：{error}", file=sys.stderr)
            return 2
        try:
            record = register_file(
                args.register,
                dataset=args.dataset,
                license_id=args.license_id,
                license_url=args.license_url,
                class_map=class_map,
                out_dir=args.out,
                allow_restricted=args.allow_restricted,
                notes=args.notes,
            )
        except (FetchError, OSError) as error:
            print(f"[register] 失败：{error}", file=sys.stderr)
            return 1
        print(f"[register] {record['id']} sha256={record['sha256']}")
        return 0

    if args.verify:
        reports = verify_records(args.out)
        for report in reports:
            print(json.dumps(report, ensure_ascii=False))
        problems = [report for report in reports if report["status"] != "OK"]
        print(f"[verify] {len(reports)} 条记录，{len(problems)} 条异常")
        return 1 if problems else 0

    if args.render:
        print(f"[render] {render_markdown(args.out)}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
