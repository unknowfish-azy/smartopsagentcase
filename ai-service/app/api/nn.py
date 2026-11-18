"""P0-1 + P0-2 + P1-2 + P1-3 + P1-4 + P2-1 + P2-2 + P2-3 + P3 神经网络能力路由。

所有路由走 /api/nn/*，Agent 通过 tool 调用。
P0-1 AnomalyTransformer: /model-info, /anomaly
P0-2 GCN RootCause:      /rootcause-info, /rootcause
P1-2 TinyBERT LogClassify: /log-info, /log-classify
P1-3 Case Retrieval:     /retrieve-info, /retrieve
P1-4 Adaptive Threshold: /adaptive-threshold-info, /adaptive-threshold
P2-1 Action Effect:      /action-info, /action-predict
P2-2 Fault Simulator:    /simulator-info, /simulate
P2-3 Reflection Loop:    /reflection-info, /learn-from-incident, /learn-history
P2-4 PatchTST Forecast:  /forecast-info, /forecast
P3 Orchestrator:         /orchestrator-info, /orchestrate
"""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas.anomaly import (
    AnomalyModelInfo,
    AnomalyRequest,
    AnomalyResponse,
)
from ..schemas.rootcause import (
    RootCauseModelInfo,
    RootCauseRequest,
    RootCauseResponse,
)
from ..schemas.log import (
    LogModelInfo,
    LogClassifyRequest,
    LogClassifyResponse,
)
from ..schemas.retrieve import (
    RetrieveModelInfo,
    CaseRetrieveRequest,
    CaseRetrieveResponse,
)
from ..schemas.action import (
    ActionEffectModelInfo,
    ActionEffectRequest,
    ActionEffectResponse,
)
from ..schemas.simulator import (
    SimulatorModelInfo,
    SimulateRequest,
    SimulateResponse,
)
from ..schemas.adaptive_threshold import (
    AdaptiveThresholdModelInfo,
    AdaptiveThresholdRequest,
    AdaptiveThresholdResponse,
)
from ..services import anomaly_detector
from ..services import rootcause_detector
from ..services import log_classifier
from ..services import case_retriever
from ..services import action_predictor
from ..services import simulator as simulator_svc
from ..services import reflection as reflection_svc
from ..schemas.reflection import (
    LearnModelInfo,
    LearnFromIncidentRequest,
    LearnFromIncidentResponse,
    LearnHistoryRequest,
    LearnHistoryResponse,
)
from ..schemas.orchestrator import (
    OrchestratorModelInfo,
    OrchestrateRequest,
    OrchestrateResponse,
)
from ..services import adaptive_threshold as adaptive_threshold_svc
from ..schemas.trace import TraceAnalyzeRequest, TraceAnalyzeResponse
from ..services import trace_detector as trace_svc
from ..schemas.forecast import ForecastModelInfo, ForecastRequest, ForecastResponse
from ..services import forecast_detector as forecast_svc
from ..schemas.tgat import TGATRequest, TGATResponse
from ..services import tgat_detector as tgat_svc


router = APIRouter()


@router.get(
    "/model-info",
    response_model=AnomalyModelInfo,
    summary="查询 AnomalyTransformer 模型状态",
)
async def get_anomaly_model_info() -> AnomalyModelInfo:
    return AnomalyModelInfo(**anomaly_detector.get_model_info())


@router.post(
    "/anomaly",
    response_model=AnomalyResponse,
    summary="时序异常检测（AnomalyTransformer 或 IsolationForest fallback）",
    description=(
        "接收一段或多段时序指标，返回逐点异常分、异常二值标记、聚合后的异常时间段。\n"
        "Agent 在告警研判时调用：先拿 anomaly_scores 判断'异常程度'，再根据 anomaly_spans 确定'什么时候开始出问题'。"
    ),
)
async def detect_anomaly(request: AnomalyRequest) -> AnomalyResponse:
    return anomaly_detector.detect(request)


# ---------------------------------------------------------------------------
# P0-2 / P1-1 根因定位（GCN/GAT + heuristic）
# ---------------------------------------------------------------------------

@router.get(
    "/rootcause-info",
    response_model=RootCauseModelInfo,
    summary="查询 GCN/GAT 根因定位模型状态",
)
async def get_rootcause_model_info() -> RootCauseModelInfo:
    return RootCauseModelInfo(**rootcause_detector.get_model_info())


@router.post(
    "/rootcause",
    response_model=RootCauseResponse,
    summary="根因定位（GCN/GAT 或 heuristic fallback）",
    description=(
        "接收关联告警图（节点 + 边），返回 top-k 候选根因节点（按 root_cause_probability 排序）。\n"
        "Agent 在告警风暴研判时调用：给一堆 correlated alerts，返回最可能的根因。"
    ),
)
async def detect_rootcause(request: RootCauseRequest) -> RootCauseResponse:
    return RootCauseResponse(**rootcause_detector.detect(request))


# ---------------------------------------------------------------------------
# P1-2 日志分类前置过滤（TinyBERT/TextCNN/heuristic）
# ---------------------------------------------------------------------------

@router.get(
    "/log-info",
    response_model=LogModelInfo,
    summary="查询日志分类模型状态",
)
async def get_log_model_info() -> LogModelInfo:
    return LogModelInfo(**log_classifier.get_model_info())


@router.post(
    "/log-classify",
    response_model=LogClassifyResponse,
    summary="日志分类 + noise 前置过滤",
    description=(
        "批量日志 → 8 类分类 + noise 前置过滤。\n"
        "Agent 在告警风暴场景先调这个：把海量原始日志过滤掉 noise 心跳，只把异常类日志送去做根因研判。"
    ),
)
async def classify_logs(request: LogClassifyRequest) -> LogClassifyResponse:
    return LogClassifyResponse(**log_classifier.classify(request))


# ---------------------------------------------------------------------------
# P1-3 故障案例向量检索（TinyBERT embedding + faiss）
# ---------------------------------------------------------------------------

@router.get(
    "/retrieve-info",
    response_model=RetrieveModelInfo,
    summary="查询故障案例向量检索状态",
)
async def get_retrieve_model_info() -> RetrieveModelInfo:
    return RetrieveModelInfo(**case_retriever.get_model_info())


@router.post(
    "/retrieve",
    response_model=CaseRetrieveResponse,
    summary="故障案例向量检索",
    description=(
        "给定故障 symptom/analysis，在 agent_decision_loop 历史案例库中做向量检索，返回 top-k 相似案例。\n"
        "Agent 在故障研判时调用：先查历史有没有同款故障，拿到根因思路 + 处置教训。"
    ),
)
async def retrieve_cases(request: CaseRetrieveRequest) -> CaseRetrieveResponse:
    return CaseRetrieveResponse(**case_retriever.retrieve(
        query=request.query,
        top_k=request.top_k,
        include_lesson=request.include_lesson,
        include_recommendation=request.include_recommendation,
    ))


# ---------------------------------------------------------------------------
# P1-4 指标自适应阈值（STL 分解 + ACF 周期推断）
# ---------------------------------------------------------------------------

@router.get(
    "/adaptive-threshold-info",
    response_model=AdaptiveThresholdModelInfo,
    summary="查询自适应阈值检测器状态",
)
async def get_adaptive_threshold_info() -> AdaptiveThresholdModelInfo:
    return AdaptiveThresholdModelInfo(**adaptive_threshold_svc.get_model_info())


@router.post(
    "/adaptive-threshold",
    response_model=AdaptiveThresholdResponse,
    summary="自适应阈值异常检测（STL + ACF 周期推断）",
    description=(
        "接收 calibration（正常基线）+ values（待检测段），返回：\n"
        "  - ACF 自动推断的周期\n"
        "  - STL 学到的 seasonal profile（前端可画正常周期基线）\n"
        "  - 两个自适应检测器的命中 + span 聚合\n"
        "Agent 用它解决'昼夜周期导致固定阈值误报/漏报'的场景。\n"
        "statsmodels 缺了自动退化到 rolling_z + ewma。"
    ),
)
async def detect_adaptive_threshold(request: AdaptiveThresholdRequest) -> AdaptiveThresholdResponse:
    return AdaptiveThresholdResponse(**adaptive_threshold_svc.detect(request))


# ---------------------------------------------------------------------------
# P2-1 处置动作效果预测（双任务 MLP + heuristic）
# ---------------------------------------------------------------------------

@router.get(
    "/action-info",
    response_model=ActionEffectModelInfo,
    summary="查询处置动作效果预测模型状态",
)
async def get_action_model_info() -> ActionEffectModelInfo:
    return ActionEffectModelInfo(**action_predictor.get_model_info())


@router.post(
    "/action-predict",
    response_model=ActionEffectResponse,
    summary="处置动作效果预测（双任务 MLP）",
    description=(
        "给定故障类别 + 严重度 + 候选动作列表，批量预测每个动作的成功概率 + 次生故障风险。\n"
        "Agent 在准备执行某个操作前调用：拿到 risk_score 排序，选最安全、成功率最高的动作。"
    ),
)
async def predict_action(request: ActionEffectRequest) -> ActionEffectResponse:
    return ActionEffectResponse(**action_predictor.predict(request))


# ---------------------------------------------------------------------------
# P2-2 故障仿真生成（纯 numpy 规则）
# ---------------------------------------------------------------------------

@router.get(
    "/simulator-info",
    response_model=SimulatorModelInfo,
    summary="查询故障仿真生成器状态",
)
async def get_simulator_info() -> SimulatorModelInfo:
    return SimulatorModelInfo(**simulator_svc.get_model_info())


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="生成一段合成故障时序（带检测器验证）",
    description=(
        "给定故障类别 → 生成 calibration + values + labels 三段。\n"
        "默认会用 detect_all() 跑一遍检测器验证 coverage，确保合成序列确实能被现有检测器检出。\n"
        "Agent 可以用它来批量演练处置流程，或给自己做'故障注入'测试。"
    ),
)
async def simulate_fault(request: SimulateRequest) -> SimulateResponse:
    return SimulateResponse(**simulator_svc.simulate(request))


# ---------------------------------------------------------------------------
# P2-3 策略自优化反思（处置后 append 新案例到 faiss）
# ---------------------------------------------------------------------------

@router.get(
    "/reflection-info",
    response_model=LearnModelInfo,
    summary="查询反思学习环状态",
)
async def get_reflection_info() -> LearnModelInfo:
    info = reflection_svc.get_model_info()
    # 字段对齐：service 返回 index_store_mode，schema 叫 faiss_mode
    info["faiss_mode"] = info.pop("index_store_mode", "unavailable")
    return LearnModelInfo(**info)


@router.post(
    "/learn-from-incident",
    response_model=LearnFromIncidentResponse,
    summary="处置完一个故障 → 反思 → append 进案例库",
    description=(
        "Agent 处置完故障后调用，把本次决策循环（symptom → action → outcome → lesson）\n"
        "写进 faiss 案例库，下次类似故障就能检索到。\n\n"
        "反思逻辑：\n"
        "  - lesson / recommendation 缺了自动按 outcome + category 补草稿\n"
        "  - incident_key 重复自动跳过\n"
        "  - 返回 review 报告（quality / signals / 自动补了什么）"
    ),
)
async def learn_from_incident(request: LearnFromIncidentRequest) -> LearnFromIncidentResponse:
    return LearnFromIncidentResponse(**reflection_svc.learn_from_incident(request))


@router.post(
    "/learn-history",
    response_model=LearnHistoryResponse,
    summary="查询学习历史（learn_history.jsonl）",
    description="查 Agent 最近 learn 过哪些故障处置，可按 category / outcome 过滤。",
)
async def get_learn_history(request: LearnHistoryRequest) -> LearnHistoryResponse:
    result = reflection_svc.get_history(
        limit=request.limit,
        category=request.category,
        outcome=request.outcome,
    )
    return LearnHistoryResponse(**result)


# ---------------------------------------------------------------------------
# P3 多 Agent 协同调度（Orchestrator）
# ---------------------------------------------------------------------------

def _get_orchestrator():
    """懒加载 Orchestrator（direct mode，ai-service 和 agent 包在同一 repo）。"""
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from agent.orchestrator import Orchestrator, ALL_PRESET_AGENTS
    orch = Orchestrator(mode="direct")
    return orch, ALL_PRESET_AGENTS


@router.get(
    "/orchestrator-info",
    response_model=OrchestratorModelInfo,
    summary="查询 Orchestrator 状态 + 已注册子 Agent 列表",
)
async def get_orchestrator_info() -> OrchestratorModelInfo:
    orch, agents = _get_orchestrator()
    return OrchestratorModelInfo(
        available=True,
        mode="direct" if orch._direct_executor else "unavailable",
        agents=[a.to_dict() for a in agents],
        max_concurrency=orch.max_concurrency,
    )


@router.post(
    "/orchestrate",
    response_model=OrchestrateResponse,
    summary="多 Agent 协同调度：goal → 任务分解 → 并发执行 → 结果整合",
    description=(
        "P3 核心能力。输入 goal + context（时序数据、日志、故障类别等），\n"
        "Orchestrator 自动拆分多个子任务，匹配专长对应的子 Agent，\n"
        "并发执行 + 冲突检测 + 最终 synthesis。\n\n"
        "内置 6 个子 Agent：AnomalySleuth / RootCauseHunter / LogInterpreter /\n"
        "CaseRetriever / ActionAdvisor / Reflection，每个有独立 system prompt +\n"
        "独立 tool_names 白名单（避免伪多 Agent）。\n\n"
        "Context 字段按需传：values/calibration/metric_name（Anomaly），logs（Log），\n"
        "category/severity/actions（Action），category/severity（Simulator）。"
    ),
)
async def orchestrate(request: OrchestrateRequest) -> OrchestrateResponse:
    orch, _ = _get_orchestrator()
    orch.max_concurrency = request.max_concurrency

    plan = orch.orchestrate(
        goal=request.goal,
        context=request.context,
        enable_agents=request.enable_agents,
        exclude_agents=request.exclude_agents,
    )

    # 让 _synthesize 能拿到 conflict_notes
    orch._last_plan = plan

    return OrchestrateResponse(
        goal=plan.goal,
        overall_status=plan.overall_status,
        subtasks=[t.to_dict() for t in plan.subtasks],
        results=[r.to_dict() for r in plan.results],
        conflict_notes=plan.conflict_notes,
        final_synthesis=plan.final_synthesis,
        agent_count=len(plan.results),
    )


# ---------------------------------------------------------------------------
# P2 阶段 2：调用链 Trace 感知（TraceFormer）
# ---------------------------------------------------------------------------


@router.get("/trace-info", tags=["neural-networks"], summary="Trace 感知模型状态")
async def trace_info() -> dict:
    return trace_svc.get_model_info()


@router.post(
    "/trace",
    response_model=TraceAnalyzeResponse,
    tags=["neural-networks"],
    summary="P2 调用链 Trace 异常感知",
    description=(
        "TraceFormer（轻量 Transformer）对 SkyWalking/Jaeger span 序列打分，"
        "定位慢节点/错误 span/关键路径，输出 top-k 可疑 span 结构化证据。"
        "无权重时降级 heuristic（慢+错误+耗时离群）。"
    ),
)
async def analyze_trace(request: TraceAnalyzeRequest) -> TraceAnalyzeResponse:
    return TraceAnalyzeResponse(**trace_svc.analyze(request))


# ---------------------------------------------------------------------------
# P2 阶段 4：PatchTST 时序预测
# ---------------------------------------------------------------------------


@router.get(
    "/forecast-info",
    response_model=ForecastModelInfo,
    tags=["neural-networks"],
    summary="PatchTST 时序预测模型状态",
)
async def forecast_info() -> ForecastModelInfo:
    return ForecastModelInfo(**forecast_svc.get_model_info())


@router.post(
    "/forecast",
    response_model=ForecastResponse,
    tags=["neural-networks"],
    summary="PatchTST 单指标多步预测",
    description=(
        "输出未来点值、95% 残差近似区间、趋势与启发式风险依据。"
        "无权重或输入不满足模型上下文/horizon 时显式降级 linear/seasonal_naive；"
        "risk_score 不是校准后的故障概率。"
    ),
)
async def forecast_series(request: ForecastRequest) -> ForecastResponse:
    return ForecastResponse(**forecast_svc.forecast(request))


# ---------------------------------------------------------------------------
# P2 阶段 3：TGAT 动态拓扑根因感知
# ---------------------------------------------------------------------------


@router.get("/tgat-info", tags=["neural-networks"], summary="TGAT 模型状态")
async def tgat_info() -> dict:
    return tgat_svc.get_model_info()


@router.post(
    "/tgat",
    response_model=TGATResponse,
    tags=["neural-networks"],
    summary="P2 TGAT 动态拓扑根因感知",
    description=(
        "TGAT（时序图注意力）对**多个时间切片的动态图序列**建模：逐切片图编码 + 时间维 GRU 聚合，"
        "输出跨时间根因候选、异常传播路径 spread_path、拓扑动态变化。"
        "适配 K8s 动态扩缩容下拓扑随时间变化的场景；无权重降级 heuristic。"
    ),
)
async def analyze_tgat(request: TGATRequest) -> TGATResponse:
    return TGATResponse(**tgat_svc.analyze(request))
