"""P3 DirectExecutor：直接 import ai-service 的 service 层，不走 HTTP。

Orchestrator 默认 mode="direct"——适合本地 smoke test 和单进程部署。
ai-service 必须在 sys.path 里（Orchestrator._try_init_direct_executor 已处理）。
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, Request, build_opener

import numpy as np

from .models import AgentProfile, SubTask

# Windows CPU crash 防护——在 transformers import 之前设
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# ---------------------------------------------------------------------------
# 机器人后端会话
#
# 优先级：
#   1. SMARTOPS_AGENT_TOKEN —— 直接作为 Bearer 使用；
#   2. SMARTOPS_AGENT_USERNAME / SMARTOPS_AGENT_PASSWORD —— 自动登录，
#      复用 Cookie 与 CSRF 令牌，401 时重登一次。
# 两者都未配置时保持匿名请求，由调用方得到明确的 401 提示。
# ---------------------------------------------------------------------------

_session_lock = threading.Lock()
_cookie_jar = http.cookiejar.CookieJar()
_opener = build_opener(HTTPCookieProcessor(_cookie_jar))
_session_state: dict[str, Any] = {"active": False, "csrf": ""}


def _backend_base() -> str:
    return os.environ.get("SMARTOPS_BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")


def _agent_credentials() -> tuple[str, str]:
    return (
        os.environ.get("SMARTOPS_AGENT_USERNAME", "").strip(),
        os.environ.get("SMARTOPS_AGENT_PASSWORD", ""),
    )


def _unwrap(raw: str) -> Any:
    parsed = json.loads(raw) if raw else {}
    if isinstance(parsed, dict) and "data" in parsed and "code" in parsed:
        return parsed.get("data")
    return parsed


def _open_request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    headers = {"Accept": "application/json"}
    token = os.environ.get("SMARTOPS_AGENT_TOKEN", "")
    payload = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        if _session_state.get("csrf"):
            headers["X-CSRF-TOKEN"] = str(_session_state["csrf"])
    request = Request(f"{_backend_base()}{path}", data=payload, headers=headers, method=method)
    with _opener.open(request, timeout=8) as response:  # noqa: S310 - 仅内网后端
        return _unwrap(response.read().decode("utf-8"))


def _reset_session() -> None:
    _cookie_jar.clear()
    _session_state["active"] = False
    _session_state["csrf"] = ""


def _login_session() -> None:
    """登录后端并缓存会话；并发调用只登录一次。"""
    username, password = _agent_credentials()
    if not username or not password:
        return
    if _session_state.get("active"):
        return
    with _session_lock:
        if _session_state.get("active"):
            return
        _reset_session()
        session = _open_request("GET", "/api/auth/session")
        csrf = (session or {}).get("csrfToken") if isinstance(session, dict) else None
        request = Request(
            f"{_backend_base()}/api/auth/login",
            data=json.dumps({"username": username, "password": password}).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                **({"X-CSRF-TOKEN": str(csrf)} if csrf else {}),
            },
            method="POST",
        )
        try:
            with _opener.open(request, timeout=8) as response:  # noqa: S310 - 仅内网后端
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:160]
            raise RuntimeError(f"后端登录失败 {exc.code}: {detail}") from exc
        code = payload.get("code") if isinstance(payload, dict) else None
        if code not in (200, 0, None):
            raise RuntimeError(f"后端登录失败: {payload.get('message') or code}")
        _session_state["active"] = True
        _session_state["csrf"] = str(csrf or "")


def _backend_call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    """调用后端；会话模式下 401 自动重登并重试一次。"""
    username, password = _agent_credentials()
    use_session = bool(username and password) and not os.environ.get("SMARTOPS_AGENT_TOKEN")
    if use_session:
        _login_session()
    try:
        return _open_request(method, path, body)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        if exc.code == 401 and use_session:
            _reset_session()
            _login_session()
            try:
                return _open_request(method, path, body)
            except HTTPError as retry_exc:
                retry_detail = retry_exc.read().decode("utf-8", "ignore")[:200]
                raise RuntimeError(
                    f"后端 {method} {path} 返回 {retry_exc.code}: {retry_detail}"
                ) from retry_exc
        if exc.code == 401 and not os.environ.get("SMARTOPS_AGENT_TOKEN"):
            raise RuntimeError(
                f"后端 {method} {path} 需要登录：请配置 SMARTOPS_AGENT_TOKEN 或 "
                "SMARTOPS_AGENT_USERNAME / SMARTOPS_AGENT_PASSWORD"
            ) from exc
        raise RuntimeError(f"后端 {method} {path} 返回 {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"后端不可达 {method} {path}: {exc.reason}") from exc

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
        elif specialty.value == "patrol_planner":
            return self._run_patrol_planner(task, context)
        elif specialty.value == "device_diagnostician":
            return self._run_device_diagnostician(task, context)
        elif specialty.value == "compliance_auditor":
            return self._run_compliance_auditor(task, context)
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
        from app.training.anomaly import DetectorConfig, detect_all

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
    # 机器人域子智能体：通过 Java 后端 REST 读取真实设备数据
    # ------------------------------------------------------------------

    def _backend_request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        """调用 Java 后端，返回 data 字段。Bearer 或服务账号会话二选一。"""
        return _backend_call(method, path, body)

    @staticmethod
    def _device_key(context: dict[str, Any]) -> str:
        value = context.get("device_key") or context.get("device") or ""
        return str(value).strip()

    def _run_patrol_planner(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """巡检调度：读取机队状态与现有任务，默认只给建议，不下发。"""
        fleet = self._backend_request("GET", "/api/robot/fleet/status") or {}
        device = self._device_key(context)
        current_tasks: list[Any] = []
        if device:
            current_tasks = self._backend_request(
                "GET", f"/api/robot/devices/{quote(device)}/tasks"
            ) or []

        route = context.get("route")
        submitted = False
        if context.get("submit") is True and device and route:
            self._backend_request(
                "POST",
                f"/api/robot/devices/{quote(device)}/tasks",
                {"route": route, "planId": context.get("plan_id")},
            )
            submitted = True

        running = [
            item for item in current_tasks
            if isinstance(item, dict) and str(item.get("status", "")).upper() == "RUNNING"
        ]
        summary = (
            f"巡检调度：机队状态已读取，设备 {device or '未指定'} "
            f"当前运行任务 {len(running)} 个；"
            + ("已按授权下发巡检任务" if submitted else "仅生成建议，未下发任务")
        )
        return {
            "summary": summary,
            "findings": {
                "device": device or None,
                "fleet_status": fleet,
                "running_tasks": len(running),
                "proposed_route": route if isinstance(route, list) else None,
                "submitted": submitted,
                "requires_approval": not submitted,
            },
        }

    def _run_device_diagnostician(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """设备诊断：真实遥测阈值判定，无数据不编造。"""
        device = self._device_key(context)
        if not device:
            return {
                "summary": "未提供 device_key，无法读取设备遥测",
                "findings": {"device": None, "risk_level": "UNKNOWN", "evidence": []},
            }

        live = self._backend_request("GET", f"/api/robot/devices/{quote(device)}/live") or {}
        tasks = self._backend_request("GET", f"/api/robot/devices/{quote(device)}/tasks") or []

        telemetry = live.get("telemetry") if isinstance(live, dict) else None
        mode = str((live or {}).get("mode") or "UNKNOWN").upper()
        evidence: list[str] = []
        level = "OK"

        def _raise_risk(candidate: str) -> None:
            nonlocal level
            order = {"OK": 0, "UNKNOWN": 1, "WARN": 2, "CRITICAL": 3}
            if order[candidate] > order[level]:
                level = candidate

        if mode in {"E_STOP", "FAULT", "OFFLINE"}:
            _raise_risk("CRITICAL")
            evidence.append(f"运行模式={mode}")
        if live.get("bridgeConnected") is False:
            _raise_risk("WARN")
            evidence.append("控制桥未连接")

        battery_raw = telemetry.get("battery") if isinstance(telemetry, dict) else None
        battery = None
        if isinstance(battery_raw, (int, float)):
            battery = round(battery_raw * 100) if battery_raw <= 1 else round(battery_raw)
            if battery < 15:
                _raise_risk("CRITICAL")
            elif battery < 30:
                _raise_risk("WARN")
            evidence.append(f"电量={battery}%")

        obstacle_raw = telemetry.get("obstacleDistance") if isinstance(telemetry, dict) else None
        if isinstance(obstacle_raw, (int, float)):
            if obstacle_raw < 0.5:
                _raise_risk("WARN")
            evidence.append(f"障碍距离={obstacle_raw:.2f}m")

        if not isinstance(telemetry, dict):
            # 无遥测只代表「未知」，不能覆盖已判定出的高危结论。
            _raise_risk("UNKNOWN")
            evidence.append("无遥测数据")

        status_counts: dict[str, int] = {}
        for item in tasks:
            if not isinstance(item, dict):
                continue
            key = str(item.get("status") or "UNKNOWN").upper()
            status_counts[key] = status_counts.get(key, 0) + 1

        summary = (
            f"设备 {device} 诊断完成：风险={level}，模式={mode}，"
            + ("；".join(evidence) if evidence else "无异常证据")
        )
        return {
            "summary": summary,
            "findings": {
                "device": device,
                "risk_level": level,
                "mode": mode,
                "battery_percent": battery,
                "evidence": evidence,
                "task_status_counts": status_counts,
            },
        }

    def _run_compliance_auditor(self, task: SubTask, context: dict[str, Any]) -> dict[str, Any]:
        """合规审计：只读核查，输出违规清单，不做自动处置。"""
        fleet = self._backend_request("GET", "/api/robot/fleet/status") or {}
        device_keys = context.get("device_keys")
        if not isinstance(device_keys, list) or not device_keys:
            single = self._device_key(context)
            device_keys = [single] if single else []

        violations: list[dict[str, Any]] = []
        checked: list[dict[str, Any]] = []
        for key in device_keys[:10]:
            device = str(key)
            live = self._backend_request("GET", f"/api/robot/devices/{quote(device)}/live") or {}
            tasks = self._backend_request("GET", f"/api/robot/devices/{quote(device)}/tasks") or []
            mode = str((live or {}).get("mode") or "UNKNOWN").upper()
            running = [
                item for item in tasks
                if isinstance(item, dict) and str(item.get("status", "")).upper() == "RUNNING"
            ]
            checked.append({"device": device, "mode": mode, "running_tasks": len(running)})
            if mode in {"E_STOP", "FAULT"} and running:
                violations.append({
                    "device": device,
                    "rule": "estop_or_fault_with_running_task",
                    "detail": f"{mode} 状态下仍有 {len(running)} 个运行任务",
                })

        summary = (
            f"合规审计完成：检查 {len(checked)} 台设备，发现 {len(violations)} 项违规"
        )
        return {
            "summary": summary,
            "findings": {
                "checked": checked,
                "violations": violations,
                "fleet_status": fleet,
                "requires_human": bool(violations),
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
