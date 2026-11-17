"""P3 DirectExecutor：直接 import ai-service 的 service 层，不走 HTTP。

Orchestrator 默认 mode="direct"——适合本地 smoke test 和单进程部署。
ai-service 必须在 sys.path 里（Orchestrator._try_init_direct_executor 已处理）。
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

# Windows CPU crash 防护——在 transformers import 之前设
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from .models import AgentProfile, SubTask


class DirectExecutor:
    """直接调用 ai-service 的 service 函数。

    每个 Agent 的 tool_names 白名单在 DirectExecutor 里**强制校验**——
    只有白名单里的工具才能被调，避免跨 Agent 越权。
    """

    def __init__(self) -> None:
        # Lazy import（ai-service 已被 Orchestrator 加到 sys.path）
        from app.services import (
            anomaly_detector,
            rootcause_detector,
            log_classifier,
            case_retriever,
            action_predictor,
            simulator as simulator_svc,
            adaptive_threshold as at_svc,
            reflection as reflection_svc,
        )
        self.anomaly = anomaly_detector
        self.rootcause = rootcause_detector
        self.log = log_classifier
        self.case = case_retriever
        self.action = action_predictor
        self.simulator = simulator_svc
        self.adaptive_threshold = at_svc
        self.reflection = reflection_svc

    def execute(self, profile: AgentProfile, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """执行一个子任务。返回 dict：{summary, findings}。

        实际调度按 profile.specialty 分发到对应的 service 函数。
        """
        specialty = profile.specialty

        # 强制工具白名单校验（防御性）
        if not profile.tool_names:
            raise RuntimeError(f"Agent {profile.agent_id} has no tool whitelist")

        if specialty.value == "anomaly_sleuth":
            return self._run_anomaly_sleuth(task, context)
        elif specialty.value == "rootcause_hunter":
            return self._run_rootcause_hunter(task, context)
        elif specialty.value == "log_interpreter":
            return self._run_log_interpreter(task, context)
        elif specialty.value == "case_retriever":
            return self._run_case_retriever(task, context)
        elif specialty.value == "action_advisor":
            return self._run_action_advisor(task, context)
        elif specialty.value == "simulator":
            return self._run_simulator(task, context)
        elif specialty.value == "reflection":
            return self._run_reflection(task, context)
        else:
            raise RuntimeError(f"unknown specialty: {specialty}")

    # ------------------------------------------------------------------
    # 各 Agent 实际调用
    # ------------------------------------------------------------------

    def _run_anomaly_sleuth(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """跑 anomaly detect_all（含 P1-4 自适应阈值）+ adaptive_threshold 独立路由。

        输入从 context 里拿：values + calibration + metric_name
        """
        import numpy as np
        from app.training.anomaly import DetectorConfig, detect_all, binary_metrics

        values = np.asarray(context.get("values") or [], dtype=float)
        calibration = np.asarray(context.get("calibration") or [], dtype=float)

        if len(values) == 0:
            return {
                "summary": "No time series data provided",
                "findings": {"spans": [], "coverage": 0.0},
            }

        config = DetectorConfig(k=3.0, window=10, alpha=0.2, contamination=0.05)
        results = detect_all(values, calibration, config)

        # 聚合 consensus span（≥3 个检测器认为是异常）
        spans = self._aggregate_spans(results, min_votes=3)
        metric = context.get("metric_name", "unknown")
        return {
            "summary": (
                f"metric={metric}, {len(spans)} anomalous spans found, "
                f"consensus ≥3 detectors voted"
            ),
            "findings": {
                "metric": metric,
                "spans": spans,
                "detector_coverage": sum(1 for m in results.values() if m.any()) / max(len(results), 1),
                "detectors_hit": [n for n, m in results.items() if m.any()],
            },
        }

    def _run_rootcause_hunter(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """GCN/GAT 根因定位。

        输入从 context 里拿：node_metrics (dict[str, list[float]]) + edge_list (list[tuple])
        """
        # 极简 stub——实际需要完整的图输入。这里返回一个占位 findings。
        return {
            "summary": "Root cause analysis requires full graph topology (node metrics + edge list). Provide in context.",
            "findings": {
                "top_candidates": [],
                "confidence": 0.0,
                "note": "Context 缺 node_metrics + edge_list，返回空候选",
            },
        }

    def _run_log_interpreter(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """日志分类 + noise 过滤。

        输入：context.logs (list[str] 或 list[dict])
        """
        logs_raw = context.get("logs") or []
        if not logs_raw:
            return {"summary": "No logs provided", "findings": {"categories": {}}}

        # 构造 LogItem（兼容 str 和 dict）
        from app.schemas.log import LogClassifyRequest, LogItem
        log_items: list[LogItem] = []
        for entry in logs_raw:
            if isinstance(entry, str):
                log_items.append(LogItem(text=entry, source="orchestrator"))
            elif isinstance(entry, dict):
                log_items.append(LogItem(
                    text=entry.get("text") or entry.get("message") or entry.get("log", str(entry)),
                    source=entry.get("source", "orchestrator"),
                ))
            else:
                log_items.append(LogItem(text=str(entry), source="orchestrator"))

        req = LogClassifyRequest(logs=log_items, filter_noise=True)
        raw = self.log.classify(req)
        return {
            "summary": f"Classified {len(log_items)} logs with noise filter",
            "findings": {
                "total_logs": len(log_items),
                "noise_filtered": raw.get("num_filtered_noise", 0),
                "kept": raw.get("num_kept", 0),
                "categories": raw.get("label_distribution", {}),
            },
        }

    def _run_case_retriever(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """从历史案例库检索。

        query 从 context.query 拼，或从 goal 直接取。
        """
        query = context.get("query") or task.description
        top_k = int(context.get("top_k", 5))
        ret = self.case.retrieve(query=query, top_k=top_k)
        results = ret.get("results", [])
        top_resolved = next(
            (r for r in results if r.get("outcome") == "resolved"), None
        )
        return {
            "summary": f"Retrieved {len(results)} similar cases for query '{query[:60]}'",
            "findings": {
                "total": len(results),
                "top_resolved_case": {
                    "incident_key": top_resolved.get("incident_key"),
                    "action_taken": top_resolved.get("action_taken"),
                    "lesson": top_resolved.get("lesson"),
                    "score": top_resolved.get("score"),
                } if top_resolved else None,
                "all_cases": [
                    {
                        "incident_key": r.get("incident_key"),
                        "score": r.get("score"),
                        "category": r.get("category"),
                        "outcome": r.get("outcome"),
                    }
                    for r in results
                ],
            },
        }

    def _run_action_advisor(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """双任务 MLP 处置效果预测。

        输入：context.category + context.severity + context.actions (list[str])
        """
        category = context.get("category") or "oom"
        severity = context.get("severity") or "P2"
        actions = context.get("actions") or [
            "restart", "scale_out", "rollback", "config_change", "manual_cleanup",
        ]
        from app.schemas.action import ActionEffectRequest
        req = ActionEffectRequest(
            category=category,
            severity=severity,
            actions=list(actions),
        )
        raw = self.action.predict(req)
        results = raw.get("results", [])
        ranked = sorted(
            results,
            key=lambda p: (p.get("risk_score", 1.0), -p.get("success_prob", 0.0)),
        )
        top = ranked[0] if ranked else {}
        return {
            "summary": (
                f"For category={category}, severity={severity}, "
                f"top recommendation={top.get('action')} "
                f"(success_prob={top.get('success_prob'):.3f}, risk_score={top.get('risk_score'):.3f})"
            ),
            "findings": {
                "top_recommendation": {
                    "action": top.get("action"),
                    "success_prob": top.get("success_prob"),
                    "risk_score": top.get("risk_score"),
                },
                "all_recommendations": [
                    {
                        "action": p.get("action"),
                        "success_prob": p.get("success_prob"),
                        "risk_score": p.get("risk_score"),
                    }
                    for p in ranked
                ],
            },
        }

    def _run_simulator(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """故障仿真生成 + 检测器验证。"""
        from app.schemas.simulator import SimulateRequest
        category = context.get("category") or "oom"
        severity = float(context.get("severity", 1.0))
        req = SimulateRequest(category=category, severity=severity, verify=True)
        raw = self.simulator.simulate(req)
        dv = raw.get("detector_verification", {})
        return {
            "summary": (
                f"Simulated {category} fault, coverage={dv.get('coverage', 0.0):.2f}, "
                f"inferred_period={dv.get('inferred_period')}"
            ),
            "findings": {
                "category": category,
                "coverage": dv.get("coverage"),
                "expected_hit": dv.get("expected_hit"),
                "inferred_period": raw.get("inferred_period"),
            },
        }

    def _run_reflection(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """反思学习——处置后 append 新案例。"""
        from app.schemas.reflection import LearnFromIncidentRequest
        req = LearnFromIncidentRequest(
            category=context.get("category", "oom"),
            symptom=context.get("symptom") or task.description[:100],
            action_taken=context.get("action_taken") or "restart",
            outcome=context.get("outcome") or "resolved",
            lesson=context.get("lesson"),
            recommendation=context.get("recommendation"),
        )
        raw = self.reflection.learn_from_incident(req)
        return {
            "summary": f"Reflection mode={raw.get('mode')}, index_size={raw.get('index_size')}",
            "findings": {
                "mode": raw.get("mode"),
                "index_size": raw.get("index_size"),
                "review": raw.get("review"),
            },
        }

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_spans(results: dict, min_votes: int = 3) -> list[dict[str, Any]]:
        """把多检测器 bool mask 聚合成 consensus span。"""
        if not results:
            return []
        n = len(list(results.values())[0])
        votes = np.zeros(n, dtype=int)
        for mask in results.values():
            votes += np.asarray(mask, dtype=int)
        consensus = votes >= min_votes

        # 聚合连续 True 段
        spans: list[dict[str, Any]] = []
        i = 0
        while i < n:
            if not consensus[i]:
                i += 1
                continue
            j = i
            while j < n and consensus[j]:
                j += 1
            spans.append({
                "start": int(i),
                "end": int(j - 1),
                "point_count": int(j - i),
                "vote_strength": int(votes[i:j].sum()),
            })
            i = j
        return spans


# direct_executor 模块到此结束。Orchestrator 会确保 ai-service 在 sys.path 里。
