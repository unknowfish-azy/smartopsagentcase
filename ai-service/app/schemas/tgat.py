"""P2 阶段 3：TGAT 动态拓扑根因感知请求/响应模型。

与静态 RootCause（单快照）的区别：输入是**多个时间切片的图序列**，
建模云原生 K8s 下服务/实例随扩缩容、故障传播而变化的动态调用拓扑。
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field

from .rootcause import AlertNode, AlertEdge


class GraphSnapshot(BaseModel):
    """一个时间切片的调用拓扑 + 节点异常特征。"""
    timestamp: float = Field(description="切片时间戳（秒，递增）")
    nodes: List[AlertNode] = Field(min_length=1, description="该时刻的告警节点")
    edges: List[AlertEdge] = Field(default_factory=list, description="该时刻的调用/关联边")


class TGATRequest(BaseModel):
    snapshots: List[GraphSnapshot] = Field(min_length=1, description="时间切片序列（按时间升序）")
    top_k: int = Field(default=3, ge=1, le=20, description="top-k 根因候选")
    time_decay: float = Field(default=0.9, ge=0.0, le=1.0, description="时间衰减（越近权重越大）")


class NodeScore(BaseModel):
    alert_id: str
    score: float = Field(ge=0.0, le=1.0)
    first_seen: float = 0.0
    last_seen: float = 0.0
    peak_snapshot: int = 0
    severity: str = "P2"


class TopologyChange(BaseModel):
    snapshot: int
    timestamp: float
    added_nodes: List[str] = Field(default_factory=list)
    removed_nodes: List[str] = Field(default_factory=list)
    added_edges: int = 0
    removed_edges: int = 0


class TGATResponse(BaseModel):
    ok: bool
    mode: str = Field(description="tgat / heuristic")
    root_candidates: List[NodeScore] = Field(description="top-k 根因候选（跨时间聚合）")
    node_scores: List[NodeScore] = Field(default_factory=list)
    spread_path: List[str] = Field(description="异常传播路径（按首次异常时间排序的节点序列）")
    topology_changes: List[TopologyChange] = Field(default_factory=list, description="拓扑动态变化")
    anomaly_score: float = 0.0
    explanation: str = ""
