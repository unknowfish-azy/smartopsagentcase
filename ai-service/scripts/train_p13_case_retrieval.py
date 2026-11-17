"""P1-3 故障案例向量化 + 检索评测脚本。

数据源：agent_decision_loop（真实 MySQL 表）+ mock fallback
向量化：TinyBERT CLS token（复用 P1-2 backbone）
存储：faiss IndexFlatIP（内积 = cosine）
评测：Recall@1 / Recall@3 / Recall@5（已知故障查询能否召回历史同类案例）

用法：
    python scripts/train_p13_case_retrieval.py --mock
    python scripts/train_p13_case_retrieval.py --mock --top-k 5 --json ../data/lake/_eval/p13_retrieval.json
    python scripts/train_p13_case_retrieval.py --db        # 待实现：读真实 agent_decision_loop
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.retrieval_model import (  # noqa: E402
    EmbeddingService,
    FaissIndexStore,
)


# ---------------------------------------------------------------------------
# Mock 故障案例库（8 类，每类 3 条历史案例，含完整 symptom/analysis/outcome/lesson）
# ---------------------------------------------------------------------------

MOCK_CASES: list[dict[str, Any]] = [
    # --- OOM ---
    {
        "incident_key": "OOM-2026-10-01-001", "severity": "P0",
        "symptom": "java.lang.OutOfMemoryError: Java heap space on srv-api-01 pod api-deploy-7f9c killed",
        "analysis": "JVM heap 2GB full, traffic spike 3x expected, GC pause 5s+, worker queue overflow",
        "recommendation": "扩容 JVM heap to 4GB + autoscale pods",
        "decision": "scale_out + restart", "outcome": "resolved",
        "lesson": "OOM 伴随 GC pause > 1s 和 queue overflow 是扩容信号",
        "category": "oom",
    },
    {
        "incident_key": "OOM-2026-09-15-003", "severity": "P1",
        "symptom": "redis-server RSS=3.8GB on srv-cache-01, memory killer triggered",
        "analysis": "cache key explosion from missing TTL on session keys",
        "recommendation": "add TTL policy + evict old sessions",
        "decision": "cleanup_keys", "outcome": "resolved",
        "lesson": "Redis OOM 优先检查 key growth rate 而非 heap size",
        "category": "oom",
    },
    {
        "incident_key": "OOM-2026-08-20-012", "severity": "P1",
        "symptom": "python-worker process killed on srv-api-02, memory usage 95%",
        "analysis": "data frame not garbage collected after ETL, holding 1.2GB in memory",
        "recommendation": "refactor ETL to stream batches + explicit del",
        "decision": "code_fix", "outcome": "resolved",
        "lesson": "Python OOM 常是泄漏而非上限不够——查对象保留",
        "category": "oom",
    },
    # --- Timeout ---
    {
        "incident_key": "TIMEOUT-2026-10-05-001", "severity": "P0",
        "symptom": "upstream api-gateway 504 timeout calling backend service, p99=8000ms",
        "analysis": "db connection pool exhausted, slow query on users table full scan",
        "recommendation": "add index + increase pool size",
        "decision": "index_creation", "outcome": "resolved",
        "lesson": "504 timeout + connection pool exhaustion → 查慢查询优先",
        "category": "timeout",
    },
    {
        "incident_key": "TIMEOUT-2026-09-28-002", "severity": "P1",
        "symptom": "kubernetes readiness probe timeout on pod web-frontend, liveness OK",
        "analysis": "startup latency increased after new config map mount, cold start 45s",
        "recommendation": "reduce init container wait + tune startup probe",
        "decision": "config_change", "outcome": "resolved",
        "lesson": "readiness vs liveness timeout 差异指向启动慢而非服务挂",
        "category": "timeout",
    },
    {
        "incident_key": "TIMEOUT-2026-09-10-007", "severity": "P2",
        "symptom": "context deadline exceeded on rpc call between api and recommendation service",
        "analysis": "network jitter across AZ, retry storm amplifying",
        "recommendation": "add circuit breaker + cross-AZ latency budget",
        "decision": "add_circuit_breaker", "outcome": "mitigated",
        "lesson": "cross-AZ timeout + retry storm → 断路器 > 加超时",
        "category": "timeout",
    },
    # --- Disk Full ---
    {
        "incident_key": "DISK-2026-10-08-001", "severity": "P1",
        "symptom": "no space left on device /var/lib/docker on srv-web-01, docker ps fails",
        "analysis": "orphaned images + terminated container logs filling 92% disk",
        "recommendation": "docker system prune + log rotate to 7 days",
        "decision": "prune_docker", "outcome": "resolved",
        "lesson": "Docker disk 满 90% 先 prune 再看根因——比扩容快得多",
        "category": "disk_full",
    },
    {
        "incident_key": "DISK-2026-09-22-004", "severity": "P0",
        "symptom": "PostgreSQL WAL disk 100%, replication lag 30min, writes blocked",
        "analysis": "WAL archive stuck on network mount, local WAL not recycling",
        "recommendation": "promote standby + restart archive",
        "decision": "promote_standby", "outcome": "resolved",
        "lesson": "DB WAL disk full + replication lag → 先切主再修 archive",
        "category": "disk_full",
    },
    {
        "incident_key": "DISK-2026-08-30-009", "severity": "P2",
        "symptom": "inode table 99% full, df -i shows 0 free on /data partition",
        "analysis": "tiny temp files from log rotation script, 1M+ 4KB files",
        "recommendation": "find + rm old temp files, tune log rotation",
        "decision": "cleanup_inodes", "outcome": "resolved",
        "lesson": "inode 满不看 disk——查小文件爆炸",
        "category": "disk_full",
    },
    # --- Connection Refused ---
    {
        "incident_key": "CONN-2026-10-10-001", "severity": "P1",
        "symptom": "econnrefused dialing redis cache 10.0.4.15:6379, all clients fail",
        "analysis": "redis-server process exited, supervisor didn't restart",
        "recommendation": "restart redis + fix supervisor config",
        "decision": "restart_process", "outcome": "resolved",
        "lesson": "conn refused on known service → 进程挂了先查 supervisor/systemd",
        "category": "connection_refused",
    },
    {
        "incident_key": "CONN-2026-09-25-003", "severity": "P2",
        "symptom": "nginx upstream connection refused to backend 10.0.4.22:8080",
        "analysis": "backend health check failing, auto-scaler terminated pods",
        "recommendation": "restore backend instances",
        "decision": "scale_up", "outcome": "resolved",
        "lesson": "nginx conn refused + autoscale event → 被自动干掉了",
        "category": "connection_refused",
    },
    # --- Process Crash ---
    {
        "incident_key": "CRASH-2026-10-03-001", "severity": "P1",
        "symptom": "segmentation fault by nginx worker, core dumped at 0x7f1a",
        "analysis": "new Nginx 1.27 binary ABI incompatibility with old module",
        "recommendation": "rollback to 1.26 stable",
        "decision": "rollback", "outcome": "resolved",
        "lesson": "segfault after binary upgrade → rollback > debug",
        "category": "process_crash",
    },
    {
        "incident_key": "CRASH-2026-09-18-002", "severity": "P2",
        "symptom": "python-worker exit code -11, segfault in libssl.so",
        "analysis": "OpenSSL 3.0 incompatibility with cryptography 38",
        "recommendation": "pin cryptography to 41.x",
        "decision": "pin_dependency", "outcome": "resolved",
        "lesson": "Python segfault in native lib → 依赖版本不匹配",
        "category": "process_crash",
    },
    # --- Auth Error ---
    {
        "incident_key": "AUTH-2026-10-02-001", "severity": "P0",
        "symptom": "all clients 401 unauthorized, token validation broken after cert rotation",
        "analysis": "JWKS endpoint returning old cert, cache hit 100%",
        "recommendation": "flush JWKS cache",
        "decision": "flush_cache", "outcome": "resolved",
        "lesson": "全量 401 + 刚换证书 → JWKS cache 老了",
        "category": "auth_error",
    },
    {
        "incident_key": "AUTH-2026-09-20-002", "severity": "P1",
        "symptom": "403 forbidden on admin endpoints by role viewer, 5 devs blocked",
        "analysis": "RBAC role binding lost during terraform apply",
        "recommendation": "re-apply terraform role bindings",
        "decision": "terraform_apply", "outcome": "resolved",
        "lesson": "403 on admin after IaC change → role binding 丢了",
        "category": "auth_error",
    },
    # --- Network Error ---
    {
        "incident_key": "NET-2026-10-07-001", "severity": "P1",
        "symptom": "dns lookup srv-cache-01 failed nxdomain, 3 min downtime",
        "analysis": "CoreDNS pod crash, 2 of 3 replicas down",
        "recommendation": "scale CoreDNS + fix readiness probe",
        "decision": "scale_coredns", "outcome": "resolved",
        "lesson": "dns 全挂先看 CoreDNS replicas，不是上游",
        "category": "network_error",
    },
    {
        "incident_key": "NET-2026-09-14-003", "severity": "P2",
        "symptom": "connection reset by peer 10.0.4.12, 30% packet loss eth0",
        "analysis": "nic firmware bug on srv-api-01, resetting every 10min",
        "recommendation": "migrate workloads to healthy nodes",
        "decision": "migrate_pods", "outcome": "mitigated",
        "lesson": "reset + 周期性 packet loss → 查硬件/firmware",
        "category": "network_error",
    },
]


# ---------------------------------------------------------------------------
# 评测：Recall@k
# ---------------------------------------------------------------------------

def compute_recall_at_k(results_by_query: list[list[str]], categories: list[str], k: int) -> float:
    """对每个 query，top-k 结果里是否有同 category 的案例（简单但足够证明链路）。"""
    hits = 0
    for retrievers, cat in zip(results_by_query, categories):
        top_k = retrievers[:k]
        if cat in top_k:
            hits += 1
    return hits / len(results_by_query) if results_by_query else 0.0


def evaluate(queries: list[dict], index_store: FaissIndexStore, top_k: int = 5) -> dict[str, Any]:
    """对每条故障当 query，检索同类别案例——链路验证。"""
    emb = EmbeddingService()
    query_texts = [q["symptom"] for q in queries]
    q_vecs = emb.encode(query_texts)

    results_by_query: list[list[str]] = []
    for i in range(len(queries)):
        q_vec = q_vecs[i : i + 1]
        retrieved = index_store.search(q_vec, top_k=top_k)
        cats = [r["meta"].get("category", "") for r in retrieved]
        results_by_query.append(cats)

    report: dict[str, Any] = {
        "mode": emb._mode,
        "num_queries": len(queries),
        "num_indexed": len(index_store),
        "recall_at_1": round(compute_recall_at_k(results_by_query, [q["category"] for q in queries], 1), 4),
        "recall_at_3": round(compute_recall_at_k(results_by_query, [q["category"] for q in queries], 3), 4),
        "recall_at_5": round(compute_recall_at_k(results_by_query, [q["category"] for q in queries], 5), 4),
    }
    return report


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="用 mock agent_decision_loop 案例")
    parser.add_argument("--db", action="store_true", help="读真实 agent_decision_loop（待实现）")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--index-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "models" / "case_retrieval")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    # 1. 加载案例
    if args.mock:
        cases = MOCK_CASES
        print(f"loaded {len(cases)} mock cases")
    elif args.db:
        print("⚠️  真实 DB 读取待实现，当前请用 --mock")
        return 1
    else:
        print("需要 --mock 或 --db")
        return 1

    # 2. 向量化（用 symptom + analysis 拼接做 embedding）
    emb = EmbeddingService()
    emb_mode = emb.ensure_loaded()
    print(f"embedding mode={emb_mode}")

    texts = [c["symptom"] + " " + c["analysis"] for c in cases]
    vectors = emb.encode(texts)
    print(f"vectors shape={vectors.shape}")

    # 3. 建索引
    index_store = FaissIndexStore(dim=vectors.shape[1])
    meta_batch = [{"incident_key": c["incident_key"], "symptom": c["symptom"],
                   "analysis": c["analysis"], "outcome": c["outcome"],
                   "lesson": c["lesson"], "category": c["category"],
                   "severity": c["severity"], "recommendation": c["recommendation"]}
                  for c in cases]
    index_store.add(vectors, meta_batch)
    print(f"index built: {len(index_store)} cases, store_mode={index_store.vector_store_mode}")

    # 4. 评测
    report = evaluate(cases, index_store, top_k=args.top_k)
    print(f"\n评测: recall@1={report['recall_at_1']:.3f} recall@3={report['recall_at_3']:.3f} recall@5={report['recall_at_5']:.3f}")

    # 5. 保存
    args.index_dir.mkdir(parents=True, exist_ok=True)
    index_store.save(args.index_dir / "case_index.faiss")
    print(f"index → {args.index_dir / 'case_index.faiss'}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report → {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
