"""P1-1 LLM 知识先验注入服务。

为大模型增强型 GNN 提供节点初始化特征：
- 调用 LLM 生成运维领域故障传播规则（"Redis 阻塞 → 网关超时"）；
- 结构化为 (source, relation, target, weight) 四元组；
- 供 GAT/GCN 训练时作为节点特征初始化的先验知识；
- LLM 不可用时返回内置静态规则集，保证永远可用。

设计原则：
- 不伪造：LLM 返回的规则经过格式校验 + 白名单过滤；
- 可降级：内置 15 条通用运维规则，无 LLM 时也能工作；
- 可审计：每条规则标注来源（llm / builtin / user），支持人工审核。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .llm import LLMService


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class PriorRule:
    """一条运维故障传播先验规则。"""
    source: str          # 源节点类型，如 "redis"
    relation: str        # 关系类型，如 "blocks" / "causes_timeout" / "cascades"
    target: str          # 目标节点类型，如 "gateway"
    weight: float        # 传播权重 0-1
    source_type: Literal["llm", "builtin", "user"] = "builtin"
    verified: bool = False  # 是否经人工审核

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "weight": self.weight,
            "source_type": self.source_type,
            "verified": self.verified,
        }


@dataclass
class NodePrior:
    """GNN 节点初始化先验特征。"""
    node_id: str
    node_type: str
    # 该节点作为 source 的出边规则
    outgoing: list[PriorRule] = field(default_factory=list)
    # 该节点作为 target 的入边规则
    incoming: list[PriorRule] = field(default_factory=list)
    # 节点重要度（出边权重之和），用于 GNN 注意力初始化
    importance: float = 0.0

    def to_feature_vector(self) -> list[float]:
        """转为 GNN 节点特征向量（简化版，真实场景应接 embedding）。

        特征维度：重要度、出边数、入边数、平均出边权重、平均入边权重。
        """
        out_w = sum(r.weight for r in self.outgoing) / max(len(self.outgoing), 1)
        in_w = sum(r.weight for r in self.incoming) / max(len(self.incoming), 1)
        return [
            self.importance,
            float(len(self.outgoing)),
            float(len(self.incoming)),
            out_w,
            in_w,
        ]


# ---------------------------------------------------------------------------
# 内置静态规则集（LLM 不可用时的降级）
# ---------------------------------------------------------------------------

BUILTIN_RULES: list[PriorRule] = [
    PriorRule("redis", "blocks", "gateway", 0.85, "builtin"),
    PriorRule("redis", "slow_response", "api_service", 0.75, "builtin"),
    PriorRule("mysql", "connection_exhausted", "api_service", 0.90, "builtin"),
    PriorRule("mysql", "slow_query", "api_service", 0.70, "builtin"),
    PriorRule("disk", "full", "mysql", 0.95, "builtin"),
    PriorRule("disk", "full", "elasticsearch", 0.90, "builtin"),
    PriorRule("elasticsearch", "yellow_status", "search_service", 0.80, "builtin"),
    PriorRule("kafka", "lag_increase", "consumer", 0.75, "builtin"),
    PriorRule("nginx", "upstream_timeout", "gateway", 0.85, "builtin"),
    PriorRule("gateway", "timeout", "frontend", 0.80, "builtin"),
    PriorRule("api_service", "high_latency", "gateway", 0.70, "builtin"),
    PriorRule("cpu", "saturation", "api_service", 0.65, "builtin"),
    PriorRule("memory", "oom", "api_service", 0.90, "builtin"),
    PriorRule("dns", "resolution_failure", "all_services", 0.95, "builtin"),
    PriorRule("network", "packet_loss", "all_services", 0.80, "builtin"),
]

# LLM 生成规则时允许的关系类型白名单
ALLOWED_RELATIONS = {
    "blocks", "causes_timeout", "cascades", "slow_response",
    "connection_exhausted", "slow_query", "full", "oom",
    "high_latency", "saturation", "upstream_timeout",
    "yellow_status", "lag_increase", "resolution_failure",
    "packet_loss", "timeout", "overload",
}

# 允许的节点类型白名单
ALLOWED_NODE_TYPES = {
    "redis", "mysql", "postgresql", "mongodb", "elasticsearch",
    "kafka", "rabbitmq", "nginx", "gateway", "api_service",
    "frontend", "disk", "cpu", "memory", "dns", "network",
    "docker", "kubernetes", "jvm", "tomcat", "all_services",
    "search_service", "consumer", "producer", "cache",
    "load_balancer", "cdn", "object_storage", "message_queue",
}


# ---------------------------------------------------------------------------
# LLM 先验生成
# ---------------------------------------------------------------------------

_PRIOR_PROMPT = """你是运维领域专家。请为以下服务拓扑生成故障传播先验规则。

已知服务节点类型：{node_types}

请生成 5-10 条故障传播规则，每条规则格式为：
source_node | relation | target_node | weight

其中：
- source_node / target_node 必须是上述节点类型之一
- relation 必须是以下之一：{relations}
- weight 是 0-1 之间的小数，表示故障传播概率

示例：
redis | blocks | gateway | 0.85
mysql | connection_exhausted | api_service | 0.90

只输出规则行，不要任何解释。"""


async def generate_priors_with_llm(
    node_types: list[str],
    llm: LLMService,
) -> list[PriorRule]:
    """调用 LLM 生成故障传播先验规则。

    LLM 不可用时返回空列表（调用方应 fallback 到 BUILTIN_RULES）。
    """
    prompt = _PRIOR_PROMPT.format(
        node_types=", ".join(sorted(set(node_types))),
        relations=", ".join(sorted(ALLOWED_RELATIONS)),
    )
    try:
        raw = await llm.generate(
            prompt,
            system_prompt="你是运维故障分析专家，只输出结构化规则。",
        )
    except Exception:
        return []

    return parse_llm_rules(raw)


def parse_llm_rules(raw: str) -> list[PriorRule]:
    """解析 LLM 输出的规则文本，过滤非法格式。"""
    rules: list[PriorRule] = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            continue
        source, relation, target, weight_str = parts
        # 白名单校验
        if source not in ALLOWED_NODE_TYPES or target not in ALLOWED_NODE_TYPES:
            continue
        if relation not in ALLOWED_RELATIONS:
            continue
        try:
            weight = float(weight_str)
        except ValueError:
            continue
        if not 0 < weight <= 1:
            continue
        rules.append(PriorRule(source, relation, target, weight, "llm"))
    return rules


# ---------------------------------------------------------------------------
# 先验特征构建
# ---------------------------------------------------------------------------

def build_node_priors(
    node_types: list[str],
    rules: list[PriorRule] | None = None,
) -> dict[str, NodePrior]:
    """为给定节点类型构建 GNN 初始化先验。

    如果 rules 为 None，使用内置规则集。
    """
    if rules is None:
        rules = BUILTIN_RULES

    priors: dict[str, NodePrior] = {}
    for nt in node_types:
        priors[nt] = NodePrior(node_id=nt, node_type=nt)

    for rule in rules:
        if rule.source in priors:
            priors[rule.source].outgoing.append(rule)
        if rule.target in priors:
            priors[rule.target].incoming.append(rule)

    # 计算重要度
    for prior in priors.values():
        prior.importance = sum(r.weight for r in prior.outgoing)

    return priors


def get_model_info() -> dict[str, Any]:
    """返回服务元信息。"""
    return {
        "available": True,
        "kind": "llm_augmented",
        "reason": "LLM 生成 + 内置规则降级",
        "builtin_rules": len(BUILTIN_RULES),
        "allowed_relations": sorted(ALLOWED_RELATIONS),
        "allowed_node_types": sorted(ALLOWED_NODE_TYPES),
    }
