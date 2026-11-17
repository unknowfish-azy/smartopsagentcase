"""P0-1 + P0-2 + P1-2 + P1-3 + P1-4 + P2-1 + P2-2 神经网络能力路由。

所有路由走 /api/nn/*，Agent 通过 tool 调用。
P0-1 AnomalyTransformer: /model-info, /anomaly
P0-2 GCN RootCause:      /rootcause-info, /rootcause
P1-2 TinyBERT LogClassify: /log-info, /log-classify
P1-3 Case Retrieval:     /retrieve-info, /retrieve
P2-1 Action Effect:      /action-info, /action-predict
P2-2 Fault Simulator:    /simulator-info, /simulate
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
from ..services import anomaly_detector
from ..services import rootcause_detector
from ..services import log_classifier
from ..services import case_retriever
from ..services import action_predictor
from ..services import simulator as simulator_svc


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
