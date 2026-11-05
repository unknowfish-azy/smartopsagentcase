"""Evaluate the existing hybrid retriever against the Linux JSONL draft set.

The evaluator deliberately uses the repository's HashEmbedding, BM25Retriever,
and HybridRetriever without tuning their weights or search parameters.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@dataclass(frozen=True)
class Sample:
    sample_id: str
    source_file: str
    row_number: int
    instruction: str
    response: str
    record: dict[str, Any]


def extract_samples(data_dir: str | Path) -> list[Sample]:
    """Load every JSONL row in deterministic filename/row order."""
    root = Path(data_dir)
    paths = sorted(root.glob("*.jsonl"))
    if len(paths) != 7:
        raise ValueError(f"expected 7 Linux JSONL files in {root}, found {len(paths)}")
    samples: list[Sample] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for row_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON in {path}:{row_number}: {exc}") from exc
                instruction = str(record.get("instruction", "")).strip()
                response = str(record.get("response", "")).strip()
                if not instruction or not response:
                    raise ValueError(f"missing instruction/response in {path}:{row_number}")
                sample_id = f"{path.stem}:{row_number}"
                samples.append(Sample(sample_id, path.name, row_number, instruction, response, record))
    if len(samples) != 14:
        raise ValueError(f"expected 14 Linux samples, found {len(samples)}")
    return samples


def _field_variants(record: dict[str, Any]) -> list[str]:
    for key in ("variants", "question_variants"):
        value = record.get(key)
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
    return []


_SCENARIO_VARIANTS: dict[str, tuple[str, str, str]] = {
    "如何统计带空格文件名的日志大小？": (
        "值班时需要汇总 logs 目录中带空格文件名的 .log 占用，怎样避免文件名被拆开？",
        "批量统计日志大小时遇到空格路径，如何保留每个文件的边界并核对总量？",
        "我要做一次只读磁盘盘点，带空格的日志文件应使用什么安全的遍历方式？",
    ),
    "Java 服务出现 Too many open files，直接调高 nofile 吗？": (
        "Java 服务告警 Too many open files 时，先收集哪些进程句柄证据再决定是否调 nofile？",
        "线上 Java 进程疑似 FD 泄漏，怎样区分单进程 EMFILE 和系统 ENFILE？",
        "调整 Java 服务打开文件上限前，如何评估容量、审批和回滚验证？",
    ),
    "crond 是 active，但 cron 任务没有结果，如何排查？": (
        "crond 显示运行中但定时任务没有产物，值班排查应先核对哪些条件？",
        "cron 作业看似触发却没有业务结果，如何检查环境变量、权限和退出码？",
        "排查无输出的 cron 任务时，怎样把调度触发与业务完成证据分开验证？",
    ),
    "每 5 分钟执行一次备份，但单次平均需要 20 分钟，风险是什么？": (
        "备份每 5 分钟启动一次而单次跑 20 分钟，如何判断是否会重叠和堆积？",
        "定时备份耗时远超间隔时，应该检查并发、锁、I/O 压力和恢复完整性哪些方面？",
        "评估高频备份任务的运行风险，怎样验证最终只保留一个实例并可恢复？",
    ),
    "把 ens33 的 IP 改掉，直接 nmcli modify 可以吗？": (
        "远程主机要修改 ens33 地址，怎样先确认连接 profile、路由和 SSH 回滚通道？",
        "准备给生产网卡换 IP 时，变更前应采集哪些 IPAM、DNS 和冲突证据？",
        "nmcli 修改网络配置可能中断当前会话，如何设计预览、审批和第二会话验证？",
    ),
    "nginx active，网页打不开，是否关防火墙？": (
        "nginx 状态是 active 但页面不可达，值班时如何区分监听、路由和安全组问题？",
        "网页打不开时，怎样从本机端口、Host/SNI、firewalld zone 和 SELinux 逐层取证？",
        "遇到 nginx active 的访问故障，如何验证业务恢复而不是直接停防火墙？",
    ),
    "httpd 启动 address already in use，可以 kill -9 吗？": (
        "httpd 报 address already in use，处理前如何确认占用端口的 PID 和服务归属？",
        "端口冲突导致 httpd 启动失败时，怎样优先选择配置修复或优雅停止？",
        "有人建议对端口占用进程 kill -9，值班应补齐哪些影响评估和验证证据？",
    ),
    "克隆完成可以直接连接生产网络吗？": (
        "虚拟机克隆完成后准备入生产，接入前应隔离核对哪些主机身份和网络基线？",
        "新克隆主机可能与原机产生 machine-id 或 MAC 冲突，怎样完成上线前验收？",
        "模板克隆后要连生产网，如何区分 required 基线、计划差异与真实漂移？",
    ),
    "chronyd active，仓库失败，服务器 READY 吗？": (
        "chronyd 显示 active 但软件仓库失败，怎样判断新服务器还处于 PARTIALLY_READY？",
        "服务器初始化时如何用 chronyc tracking、sources 和仓库可用性验证时间与软件源？",
        "看到 chronyd 进程运行并不代表时钟同步，放行服务器前还应检查哪些必需项？",
    ),
    "Spider 看到 ERR_CONNECTION_REFUSED 就能确认 nginx 挂了吗？": (
        "Spider 只观察到 ERR_CONNECTION_REFUSED，怎样补充 TCP、端口和进程证据再判断 nginx？",
        "浏览器拒绝连接可能来自无监听、代理或目标错误，排障时如何区分这些情况？",
        "自动化探针报告 connection refused 时，为什么不能直接重启 nginx，后续证据怎么取？",
    ),
    "nginx启动了吗？": (
        "需要确认 nginx 是否启动，如何结合 systemd 状态、配置校验、监听和真实请求判断？",
        "检查 nginx 启动情况时，哪些 systemctl、journalctl 和 nginx -t 证据应该一起采集？",
        "看到 nginx 进程存在后，怎样继续验证依赖、端口和业务响应而不是直接重启？",
    ),
    "如何保存正常输出和错误输出？": (
        "部署命令需要同时留存 stdout 和 stderr，POSIX shell 下怎样追加日志并保留退出状态？",
        "给审核过的命令做运行记录时，如何选择 2>&1、tee 和追加模式避免掩盖前段失败？",
        "保存命令输出到日志目录前，应怎样处理敏感字段、磁盘容量和 shell 差异？",
    ),
    "df 显示磁盘 100%，但 du 统计正常，如何排查？": (
        "df 已满但 du 看起来正常，值班排障应如何检查挂载遮蔽、inode 和 deleted-open 文件？",
        "文件系统空间耗尽而目录统计偏低时，怎样结合 df -x、lsof +L1 和证据保留定位？",
        "排查 df/du 不一致时，如何在回收空间前评估优雅重载、重启和业务影响？",
    ),
    "新增磁盘后扩容 LVM，并保证重启后挂载，应该怎样规划？": (
        "新增磁盘准备扩容 LVM，怎样按 PV、VG、LV、文件系统和挂载点逐层建立基线？",
        "要保证扩容后的挂载在重启后仍存在，fstab 应如何使用 UUID 并通过 mount -a 验证？",
        "执行 pvcreate、lvextend 和文件系统扩容前，应该准备哪些备份、审批和回滚检查？",
    ),
}


def build_variants(sample: Sample) -> list[tuple[str, str]]:
    """Return five queries with truthful provenance; no human review is implied."""
    queries: list[tuple[str, str]] = [(sample.instruction, "dataset:canonical")]
    scenario_variants = _SCENARIO_VARIANTS.get(sample.instruction, ())
    queries.extend((query, f"generated:scenario-{index}") for index, query in enumerate(scenario_variants, 1))
    queries.extend((query, "dataset:data-variant") for query in _field_variants(sample.record))
    generated = [
        (f"请排查：{sample.instruction}", "generated:operator-rephrase"),
        (f"{sample.instruction}的诊断步骤是什么？", "generated:steps"),
    ]
    queries.extend(generated)
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for query, provenance in queries:
        if query not in seen:
            deduped.append((query, provenance))
            seen.add(query)
        if len(deduped) == 5:
            break
    return deduped


def compute_metrics(top_ids: Iterable[list[str]], expected_ids: Iterable[str]) -> dict[str, float]:
    rankings = list(top_ids)
    expected = list(expected_ids)
    if len(rankings) != len(expected):
        raise ValueError("rankings and expected_ids must have equal length")
    if not rankings:
        return {"recall_at_3": 0.0, "mrr": 0.0}
    hits = [expected_id in ranking[:3] for ranking, expected_id in zip(rankings, expected)]
    reciprocal: list[float] = []
    for ranking, expected_id in zip(rankings, expected):
        try:
            reciprocal.append(1.0 / (ranking.index(expected_id) + 1))
        except ValueError:
            reciprocal.append(0.0)
    return {"recall_at_3": sum(hits) / len(hits), "mrr": sum(reciprocal) / len(reciprocal)}


def evaluate(data_dir: str | Path, output_csv: str | Path, *, include_variants=False) -> dict[str, float]:
    try:
        from knowledge.embedding.hash_embedding import HashEmbedding
        from knowledge.ingestion.chunker import TextChunker
        from knowledge.retrieval.bm25 import BM25Retriever
        from knowledge.retrieval.hybrid import HybridRetriever
        from knowledge.retrieval.vector_store import InMemoryVectorStore
    except ImportError as exc:
        raise RuntimeError("retrieval evaluation requires repository Python dependencies: " + str(exc)) from exc

    samples = extract_samples(data_dir)
    chunker = TextChunker()
    embedding = HashEmbedding()
    chunks = []
    for sample in samples:
        chunk = chunker.split(sample.sample_id, sample.response, source=sample.source_file)[0]
        chunks.append(chunk)
    store = InMemoryVectorStore()
    vectors = embedding.encode([chunk.content for chunk in chunks])
    for chunk, vector in zip(chunks, vectors):
        store.add(chunk, vector)
    retriever = HybridRetriever(store, BM25Retriever(chunks))

    rows: list[dict[str, Any]] = []
    rankings: list[list[str]] = []
    expected: list[str] = []
    for sample, chunk in zip(samples, chunks):
        variants = build_variants(sample) if include_variants else [(sample.instruction, 'dataset:canonical')]
        for variant_index, (query, provenance) in enumerate(variants, 1):
            results = retriever.search(query, embedding.encode([query])[0], top_k=3)
            top_ids = [result.document_id for result in results]
            rankings.append(top_ids)
            expected.append(sample.sample_id)
            rank = top_ids.index(sample.sample_id) + 1 if sample.sample_id in top_ids else ""
            rows.append({
                "sample_id": sample.sample_id,
                "source_file": sample.source_file,
                "variant_index": variant_index,
                "variant_source": provenance,
                "query": query,
                "expected_document_id": sample.sample_id,
                "hit_at_3": bool(rank),
                "rank": rank,
                "top3_document_ids": "|".join(top_ids),
            })

    metrics = compute_metrics(rankings, expected)
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="SmartOps-Dataset/Linux")
    parser.add_argument("--output", default="06-工程整改/eval_retrieval.csv")
    parser.add_argument('--include-variants', action='store_true', help='include unreviewed AI rewrites as a supplementary synthetic set')
    args = parser.parse_args(argv)
    try:
        samples = extract_samples(args.data_dir)
        metrics = evaluate(args.data_dir, args.output, include_variants=args.include_variants)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    query_count = len(samples) * (5 if args.include_variants else 1)
    print(f"n={query_count} 有效独立样本≈{len(samples)} samples={len(samples)}")
    print(f"Recall@3={metrics['recall_at_3']:.4f} MRR={metrics['mrr']:.4f}")
    if args.include_variants:
        print(f"口径：{len(samples)} 条原始问法 + {len(samples) * 4} 条 AI 生成改写；有效独立样本约{len(samples)}。")
    else:
        print(f"口径：仅 {len(samples)} 条原始问法。")
    print("仅验证链路，不代表泛化性能；独立人工改写尚未提供。")
    print(f"明细已写入：{Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
