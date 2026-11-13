"""M03：端到端对话时延评测（SSE 首字节 + 流式完成），真实 Ollama 模型。

链路：POST ai-service /api/chat/stream（RAG 检索 + Prompt 组装 + LLM 生成）。
run token 由本脚本按 `v1.<b64(payload)>.<b64(hmac)>` 用仓库 `.env` 里的共享密钥本地签发，
算法与 Java 边缘 `RunTokenService` 一致；因此口径**不含**登录/边缘签发开销，报告中必须注明。

用法：
    python scripts/eval_chat_latency.py --requests 1 --output <csv> --metrics-json <json>
    python scripts/eval_chat_latency.py --requests 20 --output <csv> --metrics-json <json>
    python scripts/eval_chat_latency.py --requests 30 --output <csv> --metrics-json <json> \
      --save-answers reports/t1-20261113/m05/answers.jsonl   # M05：采集 30 条盲评样本正文
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import hmac
import json
import os
import statistics
import time
import uuid
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"

# 固定输入集：覆盖 7 类运维场景的中性提问，不含任何"预期答案"标注。
PROMPTS = [
    "CPU 使用率持续偏高时，排查的第一步是什么？",
    "Linux 下如何查看哪个进程占用了最多内存？",
    "磁盘空间不足时，应该先检查哪些目录？",
    "如何判断一台机器是否发生了 OOM？",
    "Nginx 返回 502 通常有哪些原因？",
    "容器频繁重启应该看哪些日志？",
    "Redis 响应变慢可以从哪几个方面排查？",
    "MySQL 慢查询如何定位？",
    "网络不通时，ping 和 telnet 分别能说明什么？",
    "如何查看某个端口被哪个进程监听？",
    "系统负载 load average 高但 CPU 不高，可能是什么原因？",
    "如何确认一个定时任务是否真的执行了？",
    "Kubernetes Pod 一直处于 Pending 状态怎么排查？",
    "文件句柄耗尽会有哪些表现？",
    "如何查看最近的系统重启记录？",
    "日志里出现大量超时错误，应该先确认什么？",
    "如何安全地清理 Docker 未使用的镜像？",
    "进程存在但服务不响应，下一步查什么？",
    "如何比较两次配置变更的差异？",
    "什么情况下应该立即回滚而不是继续修复？",
    # M05 追加 10 题（21-30），覆盖审计/审批/巡检/诊断/记忆等场景
    "审计日志里怎么查一个用户最近的操作记录？",
    "插件 manifest 里的 approval_required 字段有什么作用？",
    "Redis 里哪些键可能包含敏感信息，巡检时要注意什么？",
    "MySQL 出现慢查询时，应该先看哪些指标？",
    "Docker 容器频繁重启，排查思路是什么？",
    "Agent 的工具调用审批被驳回后，运行记录里会留下什么？",
    "会话过期或异地登录时，系统会怎么处理？",
    "怎么确认一次诊断运行真的执行了工具而不是只给了结论？",
    "主机磁盘分区快满了，按什么顺序排查？",
    "知识库检索结果为空时，应该怎么调整查询？",
]


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("SMARTOPS_CHAT_RUN_TOKEN_SECRET", "CHAT_RUN_TOKEN_SECRET", "LLM_PROVIDER", "LLM_MODEL"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def mint_run_token(secret: str, subject: str = "6") -> str:
    payload = {"sub": subject, "run": f"m03-{uuid.uuid4().hex[:16]}", "exp": int(time.time()) + 300}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(secret.encode(), f"v1.{encoded}".encode(), hashlib.sha256).digest()
    return f"v1.{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


TOKEN_EVENTS = ("token", "answer", "content", "delta", "message")


def run_once(url: str, token: str, message: str, timeout: int) -> dict:
    started = time.perf_counter()
    row = {"message": message, "status": "ok", "first_event_ms": None, "first_token_ms": None,
           "total_ms": None, "first_event": None, "chars": 0, "error": None}
    event_first: dict[str, float] = {}
    event_counts: dict[str, int] = {}
    current_event = "message"
    answer_parts: list[str] = []
    try:
        with requests.post(
            url,
            json={"message": message, "use_rag": True, "top_k": 5},
            headers={"X-Run-Token": token},
            stream=True,
            timeout=(10, timeout),
        ) as response:
            if response.status_code != 200:
                row.update(status="http_error", error=f"HTTP {response.status_code}: {response.text[:160]}",
                           total_ms=round((time.perf_counter() - started) * 1000, 1))
                return row
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                elapsed = round((time.perf_counter() - started) * 1000, 1)
                if row["first_event_ms"] is None:
                    row["first_event_ms"] = elapsed
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                    if row["first_event"] is None:
                        row["first_event"] = current_event
                # 每个事件类型的首次出现都记录，避免把框架 run 事件误当模型首 token
                event_first.setdefault(current_event, elapsed)
                event_counts[current_event] = event_counts.get(current_event, 0) + 1
                if line.startswith("data:"):
                    row["chars"] += len(line) - 5
                    if current_event in TOKEN_EVENTS:
                        payload = line[5:].strip()
                        try:
                            data = json.loads(payload)
                        except ValueError:
                            data = payload
                        if isinstance(data, dict):
                            answer_parts.append(str(data.get("content") or data.get("delta") or data.get("text") or ""))
                        else:
                            answer_parts.append(str(data))
            row["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
    except requests.RequestException as exc:
        row.update(status="exception", error=f"{type(exc).__name__}: {exc}"[:200],
                   total_ms=round((time.perf_counter() - started) * 1000, 1))
    for name in TOKEN_EVENTS:
        if name in event_first:
            row["first_token_ms"] = event_first[name]
            break
    row["events"] = json.dumps({"first_ms": event_first, "counts": event_counts}, ensure_ascii=False)
    row["answer"] = "".join(answer_parts)
    return row


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--url", default="http://127.0.0.1:8001/api/chat/stream")
    parser.add_argument("--timeout", type=int, default=240, help="单次请求读取超时（秒）")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics-json", type=Path, required=True)
    parser.add_argument("--save-answers", type=Path, default=None,
                        help="M05：把每题回答正文写入 JSONL（sample_id/question/answer/模型/时延/状态）")
    args = parser.parse_args()

    env = load_env()
    secret = env.get("SMARTOPS_CHAT_RUN_TOKEN_SECRET") or env.get("CHAT_RUN_TOKEN_SECRET")
    if not secret:
        raise SystemExit(".env 缺少 CHAT_RUN_TOKEN_SECRET，无法签发 run token")

    rows = []
    for index in range(args.requests):
        message = PROMPTS[index % len(PROMPTS)]
        row = run_once(args.url, mint_run_token(secret), message, args.timeout)
        row["index"] = index + 1
        rows.append(row)
        print(f"[{index + 1}/{args.requests}] {row['status']} first_event={row['first_event_ms']}ms "
              f"first_token={row['first_token_ms']}ms total={row['total_ms']}ms {row['error'] or ''}")

    ok = [r for r in rows if r["status"] == "ok"]
    firsts = [r["first_event_ms"] for r in ok if r["first_event_ms"] is not None]
    tokens = [r["first_token_ms"] for r in ok if r["first_token_ms"] is not None]
    totals = [r["total_ms"] for r in ok]
    metrics = {
        "n_requested": args.requests,
        "n_ok": len(ok),
        "n_failed": args.requests - len(ok),
        "endpoint": args.url,
        "llm_provider": env.get("LLM_PROVIDER", "unknown"),
        "llm_model": env.get("LLM_MODEL", "unknown"),
        "first_event_ms": {"p50": percentile(firsts, 0.5), "p95": percentile(firsts, 0.95),
                           "mean": round(statistics.fmean(firsts), 1) if firsts else None,
                           "note": "首个 SSE 事件（框架 run 事件），不是模型输出"},
        "first_token_ms": {"p50": percentile(tokens, 0.5), "p95": percentile(tokens, 0.95),
                           "mean": round(statistics.fmean(tokens), 1) if tokens else None,
                           "n_with_token_event": len(tokens)},
        "total_ms": {"p50": percentile(totals, 0.5), "p95": percentile(totals, 0.95),
                     "mean": round(statistics.fmean(totals), 1) if totals else None},
        "caveat": "run token 本地签发，口径不含 Java 边缘/登录开销；本机 CPU 推理，非生产 GPU 环境",
        "failures": [{"index": r["index"], "error": r["error"]} for r in rows if r["status"] != "ok"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["index", "message", "status", "first_event_ms", "first_token_ms", "total_ms", "first_event", "chars", "events", "error"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    args.metrics_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.save_answers:
        args.save_answers.parent.mkdir(parents=True, exist_ok=True)
        collected_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with args.save_answers.open("w", encoding="utf-8") as handle:
            for row in rows:
                record = {
                    "sample_id": f"S{row['index']:02d}",
                    "question": row["message"],
                    "answer": row["answer"],
                    "answer_chars": len(row["answer"]),
                    "status": row["status"],
                    "llm_provider": env.get("LLM_PROVIDER", "unknown"),
                    "llm_model": env.get("LLM_MODEL", "unknown"),
                    "collected_at": collected_at,
                    "first_token_ms": row["first_token_ms"],
                    "total_ms": row["total_ms"],
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        empty = [r["index"] for r in rows if not r["answer"].strip()]
        print(f"answers_saved={len(rows)} path={args.save_answers} empty_answer_indexes={empty}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
