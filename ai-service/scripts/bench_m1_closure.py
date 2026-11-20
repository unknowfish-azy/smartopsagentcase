# -*- coding: utf-8 -*-
"""M1 最小闭环可复现 demo：≥20 个仿真故障场景跑通并一键重算指标。

覆盖链路：
    指标 → nn.anomaly → nn.rootcause → nn.log_classify → nn.retrieve
         → ReAct 决策 → IncidentClosure（反思 + 长期记忆 + nn.learn_from_incident 写回）

证据来源为**确定性离线回放**（与 ai-service 同构的响应 fixture）：
它验证的是闭环管线与指标口径，结果完全可复现；指标数值不代表真实模型精度。
接真实服务时，把 ScenarioReplayHttp 换成 httpx POST 即可，其余代码与口径不变。

指标口径（与实施路线图 M1 验收门一致）：
  SR        处置成功率（最终动作 == 场景期望动作）
  MTTR      平均恢复时间（场景内固定时钟，确定性）
  A@1/A@3   根因命中率（nn.rootcause 候选对照真值）
  MRR       平均倒数排名
  F1 / FPR  异常检测事件级对照（fixture 检出 vs 真值标签）
  Calls     平均工具调用次数；Invalid% 重复/无效调用占比
  Halluc%   最终结论是否引用了缺失证据（规则判定）
  Token     单次故障 Prompt 字符数 / 4 估算

用法：
    python ai-service/scripts/bench_m1_closure.py
    python ai-service/scripts/bench_m1_closure.py --scenarios 30
输出：
    reports/m1_closure_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.executor.models import ExecutionContext  # noqa: E402
from agent.memory.long_term import LongTermMemory  # noqa: E402
from agent.planner.closure import IncidentClosure  # noqa: E402
from agent.planner.react_agent import build_react_planner  # noqa: E402
from agent.sdk.model import ModelProvider, ModelResponse  # noqa: E402
from agent.tools.builtin.nn_perception import build_nn_perception_tools  # noqa: E402
from agent.tools.registry import ToolRegistry  # noqa: E402

OUT_PATH = ROOT / "reports" / "m1_closure_results.json"

CATEGORIES = [
    "oom", "timeout", "disk_full", "connection_refused",
    "process_crash", "auth_error", "network_error",
]
ACTIONS = {
    "oom": "scale_out",
    "timeout": "restart",
    "disk_full": "manual_cleanup",
    "connection_refused": "restart",
    "process_crash": "restart",
    "auth_error": "config_change",
    "network_error": "rollback",
}
METRICS = {
    "oom": "memory",
    "timeout": "latency",
    "disk_full": "disk_usage",
    "connection_refused": "network_rx",
    "process_crash": "cpu",
    "auth_error": "http_401",
    "network_error": "packet_loss",
}
SEGMENT = 48


def _series(seed: int, anomaly_start: int) -> list[float]:
    """确定性合成指标序列：基线 + 轻度周期 + 故障段尖峰。"""

    values = []
    for index in range(SEGMENT):
        baseline = 40 + 4 * math.sin((index + seed % 7) / 6)
        values.append(round(baseline, 3))
    for offset in range(6):
        values[anomaly_start + offset] = round(88 + seed % 5, 3)
    return values


def build_scenarios(count: int = 24) -> list[dict[str, Any]]:
    """确定性构造仿真故障场景（真值标签 + fixture 证据）。"""

    scenarios: list[dict[str, Any]] = []
    for index in range(count):
        category = CATEGORIES[index % len(CATEGORIES)]
        seed = 1000 + index
        true_rank = 1 if index % 4 != 3 else min(2 + (index % 3), 4)  # 1/4 场景 Top1 排错
        root_id = f"alert-{category}-{index}"

        # 异常真值：在测试段中部注入 6 个异常点
        start = 18 + (index % 5)
        labels = [0] * SEGMENT
        for offset in range(6):
            labels[start + offset] = 1
        # 检测器命中：真值全覆盖 + 每 3 个场景 2 个误报点
        hits = set(range(start, start + 6))
        if index % 3 == 0:
            hits.update({2, 3})

        candidates = [
            {
                "rank": rank,
                "alert_id": root_id if rank == true_rank else f"alert-noise-{rank}",
                "score": round(0.92 - 0.11 * (rank - 1), 2),
            }
            for rank in range(1, 5)
        ]

        scenarios.append(
            {
                "id": f"scene-{index + 1:02d}",
                "seed": seed,
                "goal": f"排查 {category} 故障（{METRICS[category]} 指标异常）",
                "category": category,
                "metric": METRICS[category],
                "values": _series(seed, start),
                "root_cause": root_id,
                "true_rank": true_rank,
                "candidates": candidates,
                "labels": labels,
                "detector_hits": sorted(hits),
                "expected_action": ACTIONS[category],
                "mttr_seconds": 40 + 8 * true_rank + (25 if true_rank > 1 else 0),
                "rootcause_available": index % 7 != 6,  # 每 7 个场景模拟一次根因服务不可用
                "logs": [
                    {"text": f"{category} symptom on {METRICS[category]}"},
                    {"text": "heartbeat ok"},
                ],
                "prior_cases": [
                    {
                        "incident_key": f"case-{category}-{index}",
                        "category": category,
                        "outcome": "resolved",
                        "score": 0.8,
                    }
                ],
            }
        )
    return scenarios


class ScenarioReplayHttp:
    """离线回放：按场景 fixture 返回与 ai-service 同构的响应。"""

    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, payload))
        s = self.scenario
        if url.endswith("/api/nn/anomaly"):
            return {
                "ok": True,
                "model_status": "ok",
                "results": [
                    {
                        "metric": s["metric"],
                        "peak_score": 0.91,
                        "span_count": 1,
                        "points": [{"index": i} for i in s["detector_hits"]],
                    }
                ],
            }
        if url.endswith("/api/nn/rootcause"):
            if not s["rootcause_available"]:
                return {"ok": False, "model_status": "unavailable", "error": "replay: service down"}
            return {"ok": True, "model_status": "ok", "candidates": s["candidates"]}
        if url.endswith("/api/nn/log-classify"):
            return {
                "ok": True,
                "num_total": len(s["logs"]),
                "num_kept": 1,
                "label_distribution": {s["category"]: 1, "noise": 1},
            }
        if url.endswith("/api/nn/retrieve"):
            return {"ok": True, "results": s["prior_cases"]}
        if url.endswith("/api/nn/learn-from-incident"):
            return {"ok": True, "mode": "learned", "index_size": 1}
        return {"ok": True}


class PolicyProvider(ModelProvider):
    """确定性的 ReAct 策略：固定顺序取证，最后基于场景 fixture 给结论。

    固定顺序保证每次运行的轨迹与 token 成本完全一致，指标可重算。
    """

    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return "m1-policy"

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        self.prompts.append(prompt)
        content = self._response_for_step(len(self.prompts), self.scenario)
        return ModelResponse(content=content, model="m1-policy", provider="scripted", metadata={})

    @staticmethod
    def _response_for_step(step: int, s: dict[str, Any]) -> str:
        if step == 1:
            payload = {"values": s["values"], "metric_name": s["metric"]}
            return f"Thought: 先确认指标异常\nAction: nn.anomaly\nAction Input: {json.dumps(payload)}"
        if step == 2:
            payload = {"nodes": [{"alert_id": s["root_cause"], "severity": "P1"}]}
            return f"Thought: 定位根因候选\nAction: nn.rootcause\nAction Input: {json.dumps(payload)}"
        if step == 3:
            payload = {"logs": [{"text": log["text"]} for log in s["logs"]]}
            return (
                "Thought: 分类日志降噪\nAction: nn.log_classify\n"
                f"Action Input: {json.dumps(payload)}"
            )
        if step == 4:
            return (
                "Thought: 检索历史处置\nAction: nn.retrieve\n"
                f"Action Input: {json.dumps({'query': s['goal']})}"
            )
        if not s["rootcause_available"]:
            return "Final Answer: 根因证据缺失，无法确认根因；建议先人工核查，不执行变更。"
        top1 = s["candidates"][0]["alert_id"]
        action = s["expected_action"] if s["true_rank"] == 1 else "wait_and_observe"
        return (
            f"Final Answer: 根因是 {top1}（候选第 {s['true_rank']} 位）；"
            f"建议处置动作：{action}。"
        )


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------


def detection_confusion(scenario: dict[str, Any]) -> tuple[int, int, int]:
    """返回 (TP, FP, FN)。"""

    hits = set(scenario["detector_hits"])
    anomalies = {i for i, label in enumerate(scenario["labels"]) if label == 1}
    return len(hits & anomalies), len(hits - anomalies), len(anomalies - hits)


def rank_of_truth(scenario: dict[str, Any]) -> int:
    truth = scenario["root_cause"]
    for candidate in scenario["candidates"]:
        if candidate["alert_id"] == truth:
            return int(candidate["rank"])
    return len(scenario["candidates"]) + 1


def final_action(scenario: dict[str, Any], answer: str) -> str:
    if not scenario["rootcause_available"]:
        return "wait_and_observe"
    expected = scenario["expected_action"] if scenario["true_rank"] == 1 else "wait_and_observe"
    return expected if expected in answer else "unknown"


def is_hallucination(scenario: dict[str, Any], answer: str, evidence: dict[str, Any]) -> bool:
    """规则判定：根因证据缺失却给出确定根因，视为幻觉。"""

    missing = set(evidence.get("missing") or [])
    if "nn.rootcause" in missing and "缺失" not in answer:
        return True
    if "nn.rootcause" not in missing and scenario["true_rank"] > 1:
        top1 = scenario["candidates"][0]["alert_id"]
        if top1 in answer and "候选第" not in answer:
            return True
    return False


# ---------------------------------------------------------------------------
# 单场景执行
# ---------------------------------------------------------------------------


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    http = ScenarioReplayHttp(scenario)
    tools = build_nn_perception_tools(
        http_post=http, tiers=("perception", "writeback")
    )
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)

    provider = PolicyProvider(scenario)
    planner = build_react_planner(
        provider=provider,
        tool_registry=registry,
        perception_http_post=http,
        perception_tiers=("perception", "writeback"),
        max_iterations=8,
    )
    context = ExecutionContext(f"m1-{scenario['id']}", f"user-{scenario['id']}")
    result = planner.run(scenario["goal"], context)

    action_taken = final_action(scenario, result.final_answer)
    success = action_taken == scenario["expected_action"]  # ground truth 对照

    memory = LongTermMemory()
    closure = IncidentClosure(memory, executor=planner.executor, tool_registry=registry)
    record = closure.close(
        scenario["goal"],
        result,
        context,
        category=scenario["category"],
        severity="P1",
        success=success,
        action_taken=action_taken,
        duration_minutes=math.ceil(scenario["mttr_seconds"] / 60),
    )

    stats = result.metadata.get("stats", {})
    prompt_chars = sum(len(prompt) for prompt in provider.prompts)
    return {
        "scenario": scenario["id"],
        "category": scenario["category"],
        "status": result.status,
        "outcome": record.outcome,
        "success": final_action(scenario, result.final_answer) == scenario["expected_action"],
        "mttr_seconds": scenario["mttr_seconds"],
        "truth_rank": rank_of_truth(scenario),
        "confusion": detection_confusion(scenario),
        "calls": int(stats.get("tool_calls", 0)),
        "duplicates": int(stats.get("duplicate_calls", 0)),
        "hallucination": is_hallucination(scenario, result.final_answer, record.evidence),
        "tokens": round(prompt_chars / 4),
        "evidence_missing": record.evidence.get("missing", []),
        "writeback_ok": bool((record.metrics.get("writeback") or {}).get("ok")),
        "final_answer": result.final_answer,
    }


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    tp = sum(row["confusion"][0] for row in rows)
    fp = sum(row["confusion"][1] for row in rows)
    fn = sum(row["confusion"][2] for row in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    negative_total = total * (SEGMENT - 6)  # 每个场景 6 个真异常点
    ranks = [row["truth_rank"] for row in rows]
    calls = sum(row["calls"] for row in rows)
    duplicates = sum(row["duplicates"] for row in rows)
    return {
        "scenarios": total,
        "SR": round(sum(1 for row in rows if row["success"]) / total, 4),
        "MTTR_seconds": round(sum(row["mttr_seconds"] for row in rows) / total, 1),
        "A@1": round(sum(1 for rank in ranks if rank == 1) / total, 4),
        "A@3": round(sum(1 for rank in ranks if rank <= 3) / total, 4),
        "MRR": round(sum(1.0 / rank for rank in ranks) / total, 4),
        "F1": round(f1, 4),
        "FPR": round(fp / negative_total, 4) if negative_total else 0.0,
        "Calls": round(calls / total, 2),
        "Invalid%": round(duplicates / calls * 100, 2) if calls else 0.0,
        "Halluc%": round(sum(1 for row in rows if row["hallucination"]) / total * 100, 2),
        "Cost_tokens": round(sum(row["tokens"] for row in rows) / total, 1),
        "writeback_ok%": round(sum(1 for row in rows if row["writeback_ok"]) / total * 100, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 最小闭环可复现 demo")
    parser.add_argument("--scenarios", type=int, default=24, help="场景数（默认 24，>=20）")
    args = parser.parse_args()
    if args.scenarios < 20:
        parser.error("M1 验收要求至少 20 个场景")

    scenarios = build_scenarios(args.scenarios)
    rows = [run_scenario(scenario) for scenario in scenarios]
    summary = summarize(rows)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"mode": "replay", "summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"模式：离线回放（确定性）  场景数：{summary['scenarios']}")
    print("-" * 76)
    for row in rows:
        flags = []
        if row["hallucination"]:
            flags.append("HALLUC")
        if row["duplicates"]:
            flags.append(f"dup={row['duplicates']}")
        if not row["writeback_ok"]:
            flags.append("wb-fail")
        print(
            f"{row['scenario']:<9} {row['category']:<18} status={row['status']:<12} "
            f"SR={'Y' if row['success'] else 'N'} rank={row['truth_rank']} "
            f"calls={row['calls']} tok={row['tokens']:<5} {' '.join(flags)}"
        )
    print("-" * 76)
    for key, value in summary.items():
        print(f"{key:<14} {value}")
    print(f"\n明细已写入：{OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
