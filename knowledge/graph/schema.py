"""知识图谱词表与数据结构（P2-7 / B1）。

方案口径：`docs/design/p2-7-causal-kg-debate-v1/DESIGN.md` §3。

**词表封闭**（门禁 B-G1）：抽取器不得产出本文件词表之外的实体 / 关系类型。
新增词表必须显式改本文件，并在测试里被钉住。

实体类型：``service`` / ``component`` / ``alert`` / ``metric`` / ``run``
关系类型：``depends_on`` / ``emits`` / ``caused_by`` / ``mitigated_by`` / ``cites``

**神经符号边界**（方案 §3.3，必须随结果引用）：
- **神经**负责召回与排序（现有 hybrid 检索）；
- **符号**负责可解释推导与硬约束；
- 符号结论必须能回溯到具体边与 ``source_entry_id``，否则只能标 ``neural_only``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 封闭类型词表
# ---------------------------------------------------------------------------

ENTITY_TYPES: tuple[str, ...] = (
    "service",
    "component",
    "alert",
    "metric",
    "run",
)

RELATION_TYPES: tuple[str, ...] = (
    "depends_on",
    "emits",
    "caused_by",
    "mitigated_by",
    "cites",
)

# ---------------------------------------------------------------------------
# 受控关键词词表：(规范名, 正则)
# ---------------------------------------------------------------------------

COMPONENT_VOCAB: tuple[tuple[str, str], ...] = (
    ("磁盘", r"磁盘|空间|disk|space|filesystem|inode|只读|read-only"),
    ("内存", r"内存|memory|oom|ram"),
    ("CPU", r"\bcpu\b|负载|load average"),
    ("网络", r"网络|链路|network|connectivity|连通|丢包|loss"),
    ("端口", r"端口|port|监听|listen"),
    ("证书", r"证书|certificate|\btls\b|ssl"),
    ("配置", r"配置|config|configuration|参数"),
    ("进程", r"进程|process|daemon|systemd"),
    ("文件描述符", r"文件描述符|\bfd\b|ulimit|句柄"),
    ("连接池", r"连接池|connection pool|conn pool"),
    ("复制", r"复制|replication|主从"),
    ("路由", r"路由|routing|route"),
    ("DNS", r"\bdns\b|解析|resolution"),
    ("防火墙", r"防火墙|firewall|安全组|security group"),
    ("容器", r"容器|container|docker"),
    ("权限", r"权限|permission|acl|ownership|selinux|属主"),
    ("身份", r"身份|identity|machine-id|\bmac\b|克隆主机|clone"),
    ("负载均衡", r"负载均衡|\blb\b|gateway|网关"),
    ("数据库", r"数据库|database|\bmysql\b|\bredis\b"),
    ("缓存", r"缓存|cache"),
)

METRIC_VOCAB: tuple[tuple[str, str], ...] = (
    ("cpu_usage", r"\bcpu\b"),
    ("memory_usage", r"内存|memory"),
    ("disk_usage", r"磁盘|空间|disk|inode"),
    ("latency", r"延迟|时延|latency"),
    ("error_rate", r"错误率|error rate|报错|错误"),
    ("connections", r"连接数|connections"),
    ("replication_lag", r"复制延迟|replication lag|主从延迟"),
    ("oom", r"\boom\b|内存耗尽"),
    ("http_status", r"http\s*\d{3}|状态码"),
    ("tcp_connect", r"tcp|建连|三次握手"),
    ("dns_lookup", r"\bdns\b|解析"),
)

RUN_VOCAB: tuple[tuple[str, str], ...] = (
    ("隔离", r"隔离|isolate"),
    ("核验", r"核验|验证|确认|检查|inspect|verify"),
    ("审批", r"审批|approve"),
    ("修正", r"修正|修复|fix|repair"),
    ("重启", r"重启|restart|reboot"),
    ("回滚", r"回滚|rollback"),
    ("扩容", r"扩容|scale"),
    ("切换", r"切换|switch|failover"),
    ("轮换", r"轮换|rotate"),
    ("演练", r"演练|drill"),
    ("配置变更", r"配置变更|变更|change"),
)

_VOCAB: dict[str, tuple[tuple[str, str], ...]] = {
    "component": COMPONENT_VOCAB,
    "metric": METRIC_VOCAB,
    "run": RUN_VOCAB,
}

_COMPILED: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    entity_type: tuple(
        (canonical, re.compile(pattern, re.IGNORECASE))
        for canonical, pattern in vocab
    )
    for entity_type, vocab in _VOCAB.items()
}


def match_entities(entity_type: str, *texts: str) -> tuple[str, ...]:
    """在给定文本里匹配某类实体，返回**去重且确定序**的规范名。"""

    if entity_type not in _COMPILED:
        raise ValueError(
            f"未知实体类型：{entity_type}；词表为 {sorted(_COMPILED)}"
        )
    haystack = "\n".join(t for t in texts if t)
    if not haystack.strip():
        return ()
    return tuple(
        canonical
        for canonical, pattern in _COMPILED[entity_type]
        if pattern.search(haystack)
    )


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Entity:
    """图节点。``id`` 在 ``type`` 命名空间内唯一。"""

    type: str
    id: str
    label: str = ""

    def __post_init__(self) -> None:
        if self.type not in ENTITY_TYPES:
            raise ValueError(
                f"实体类型不在封闭词表内：{self.type}；词表为 {ENTITY_TYPES}"
            )
        if not self.id:
            raise ValueError("实体 id 不能为空")

    @property
    def key(self) -> tuple[str, str]:
        return (self.type, self.id)

    def to_dict(self) -> dict:
        return {"type": self.type, "id": self.id, "label": self.label}


@dataclass(frozen=True)
class Edge:
    """有向边。``confidence`` 与 ``source_entry_id`` 是入图的硬要求。"""

    src_type: str
    src_id: str
    dst_type: str
    dst_id: str
    relation: str
    confidence: float
    source_entry_id: str
    extractor: str
    evidence_text: str = ""

    def __post_init__(self) -> None:
        if self.relation not in RELATION_TYPES:
            raise ValueError(
                f"关系类型不在封闭词表内：{self.relation}；词表为 {RELATION_TYPES}"
            )
        if self.src_type not in ENTITY_TYPES or self.dst_type not in ENTITY_TYPES:
            raise ValueError("边的端点类型必须在封闭词表内")
        if not self.source_entry_id:
            raise ValueError("边必须带 source_entry_id（可回溯硬要求）")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence 越界：{self.confidence}")

    @property
    def src_key(self) -> tuple[str, str]:
        return (self.src_type, self.src_id)

    @property
    def dst_key(self) -> tuple[str, str]:
        return (self.dst_type, self.dst_id)

    def to_dict(self) -> dict:
        return {
            "src_type": self.src_type,
            "src_id": self.src_id,
            "dst_type": self.dst_type,
            "dst_id": self.dst_id,
            "relation": self.relation,
            "confidence": self.confidence,
            "source_entry_id": self.source_entry_id,
            "extractor": self.extractor,
            "evidence_text": self.evidence_text,
        }


@dataclass
class ExtractionResult:
    """一次抽取的完整产物（含被拒边）。"""

    entities: dict[tuple[str, str], Entity] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    entry_stats: dict[str, dict] = field(default_factory=dict)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    def to_dict(self) -> dict:
        return {
            "n_entities": len(self.entities),
            "n_edges": len(self.edges),
            "n_rejected": self.rejected_count,
            "entity_type_counts": _counts(
                entity.type for entity in self.entities.values()
            ),
            "relation_counts": _counts(edge.relation for edge in self.edges),
            "extractor_counts": _counts(edge.extractor for edge in self.edges),
            "entities": [entity.to_dict() for entity in self.entities.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "rejected": list(self.rejected),
        }


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


__all__ = [
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "COMPONENT_VOCAB",
    "METRIC_VOCAB",
    "RUN_VOCAB",
    "Entity",
    "Edge",
    "ExtractionResult",
    "match_entities",
]
