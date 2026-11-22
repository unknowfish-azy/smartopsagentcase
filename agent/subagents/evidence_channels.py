"""辩论证据通道（P2-7 / A2）：每角色独立工具视图 + 独立证据 id 空间。

铁律（方案 `docs/design/p2-7-causal-kg-debate-v1/DESIGN.md` §2.3）：

    每个角色**只能看到自己通道的证据**。若四个角色都读到同一份检索结果，
    结论一致是**同源自证**，不是辩论生效——这是硬约束，不是建议。

因此本模块提供两件事：

1. ``partition_items``：按**封闭**的「探针类型 → 通道」分区切分证据，
   每个证据 id 只归属一个通道（分区不相交）；
2. ``validate_isolation``：机检隔离性。任何两个通道出现共同 evidence_id、
   或某通道读到自己词表外的探针类型，都判 ``valid=False``。

负对照用 ``shared_pool_views``：把所有证据发给所有角色，
``validate_isolation`` 必须判为 **invalid**（门禁 A-G2）。

词表封闭：``CHANNEL_PROBE_TYPES`` 未收录的探针类型一律报错，
不得静默丢弃（与 B-G1 的「词表封闭」纪律一致）。
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 通道定义（封闭词表）
# ---------------------------------------------------------------------------

CHANNEL_ROLES: tuple[str, ...] = (
    "log_diagnosis",
    "metric_inspector",
    "topology_inspector",
    "change_auditor",
)

# 探针类型 → 通道。四个集合必须**不相交**（partition），不是重叠授权。
CHANNEL_PROBE_TYPES: dict[str, frozenset[str]] = {
    # 进程 / 日志 / 内核态信号
    "log_diagnosis": frozenset({
        "log_line", "oom_kills", "systemd_state", "process",
    }),
    # 指标阈值 / 资源水位 / 数据库与 HTTP 观测
    "metric_inspector": frozenset({
        "metric_threshold", "latency", "memory", "disk_usage", "inode_usage",
        "fd_count", "db_replication_lag", "connection_pool", "cache_ping",
        "db_query", "slow_query", "http_status", "http_body",
    }),
    # 网络可达性 / 依赖拓扑 / 接入链路
    "topology_inspector": frozenset({
        "icmp", "tcp_connect", "port", "dns_lookup", "bastion_reachable",
        "tls_cert", "ssh_auth", "known_hosts",
    }),
    # 配置与变更面
    "change_auditor": frozenset({
        "config_value",
    }),
}

# 每个通道允许使用的工具视图（必须是 ToolRegistry 中真实存在的工具名）。
CHANNEL_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "log_diagnosis": ("docker.logs", "nginx.logs", "knowledge.search"),
    "metric_inspector": ("sentinel.metrics", "sentinel.alerts", "slo.status"),
    "topology_inspector": ("inspector.events", "servers.list"),
    "change_auditor": ("audit.chain", "incidents.list"),
}

PROBE_TYPE_VOCABULARY: frozenset[str] = frozenset(
    probe_type
    for probe_types in CHANNEL_PROBE_TYPES.values()
    for probe_type in probe_types
)


def _check_partition() -> None:
    seen: dict[str, str] = {}
    for role, probe_types in CHANNEL_PROBE_TYPES.items():
        for probe_type in probe_types:
            if probe_type in seen:
                raise ValueError(
                    f"通道分区必须不相交：{probe_type} 同时属于 "
                    f"{seen[probe_type]} 与 {role}"
                )
            seen[probe_type] = role


_check_partition()


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """一条证据：id + 探针类型（决定它归属哪个通道）。"""

    evidence_id: str
    probe_type: str
    target: str = ""
    summary: str = ""


@dataclass(frozen=True)
class ChannelView:
    """单个角色的证据视图（只含本通道的探针类型）。"""

    role: str
    items: tuple[EvidenceItem, ...]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.evidence_id for item in self.items)

    @property
    def probe_types(self) -> frozenset[str]:
        return frozenset(item.probe_type for item in self.items)

    @property
    def empty(self) -> bool:
        return not self.items


@dataclass(frozen=True)
class IsolationReport:
    """隔离性校验结果。``valid=False`` 表示该组视图**不能**用来证明辩论生效。"""

    valid: bool
    shared_id_pairs: tuple[tuple[str, str], ...]
    unknown_probe_types: tuple[str, ...]
    offending_roles: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "shared_id_pairs": [list(pair) for pair in self.shared_id_pairs],
            "unknown_probe_types": list(self.unknown_probe_types),
            "offending_roles": list(self.offending_roles),
            "reasons": list(self.reasons),
        }


# ---------------------------------------------------------------------------
# 切分
# ---------------------------------------------------------------------------


def partition_items(
    items: list[EvidenceItem] | tuple[EvidenceItem, ...],
    role_names: tuple[str, ...] = CHANNEL_ROLES,
) -> dict[str, ChannelView]:
    """按通道分区切分证据；未知探针类型直接报错（词表封闭）。"""

    unknown = sorted({item.probe_type for item in items} - PROBE_TYPE_VOCABULARY)
    if unknown:
        raise ValueError(
            f"探针类型不在封闭词表内：{unknown}；"
            f"词表为 {sorted(PROBE_TYPE_VOCABULARY)}"
        )

    unknown_roles = sorted(set(role_names) - set(CHANNEL_PROBE_TYPES))
    if unknown_roles:
        raise ValueError(f"未知通道角色：{unknown_roles}")

    owner: dict[str, str] = {
        probe_type: role
        for role, probe_types in CHANNEL_PROBE_TYPES.items()
        for probe_type in probe_types
    }

    buckets: dict[str, list[EvidenceItem]] = {role: [] for role in role_names}
    dropped: list[EvidenceItem] = []
    for item in items:
        role = owner[item.probe_type]
        if role in buckets:
            buckets[role].append(item)
        else:
            dropped.append(item)
    if dropped:
        raise ValueError(
            f"有 {len(dropped)} 条证据属于未启用的通道"
            f"（如 {dropped[0].evidence_id} / {dropped[0].probe_type}）"
        )

    return {
        role: ChannelView(role=role, items=tuple(buckets[role]))
        for role in role_names
    }


def shared_pool_views(
    items: list[EvidenceItem] | tuple[EvidenceItem, ...],
    role_names: tuple[str, ...] = CHANNEL_ROLES,
) -> dict[str, ChannelView]:
    """**负对照**：所有角色看到同一份证据池（同源自证，必须被判 invalid）。"""

    return {
        role: ChannelView(role=role, items=tuple(items))
        for role in role_names
    }


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def validate_isolation(views: dict[str, ChannelView]) -> IsolationReport:
    """机检证据通道隔离性。

    三条判据，任一不满足即 ``valid=False``：

    1. 没有未知探针类型；
    2. 每个通道只读到自己词表内的探针类型；
    3. 任意两个通道的 evidence_id 集合**不相交**。
    """

    reasons: list[str] = []

    unknown = sorted({
        item.probe_type
        for view in views.values()
        for item in view.items
    } - PROBE_TYPE_VOCABULARY)
    if unknown:
        reasons.append(f"探针类型不在封闭词表内：{unknown}")

    offending: list[str] = []
    for role, view in views.items():
        allowed = CHANNEL_PROBE_TYPES.get(role)
        if allowed is None:
            offending.append(role)
            reasons.append(f"未知角色：{role}")
            continue
        outside = sorted(view.probe_types - allowed)
        if outside:
            offending.append(role)
            reasons.append(f"角色 {role} 读到了本通道词表外的探针类型：{outside}")

    roles = list(views)
    shared_pairs: list[tuple[str, str]] = []
    for i, left in enumerate(roles):
        for right in roles[i + 1:]:
            overlap = sorted(set(views[left].ids) & set(views[right].ids))
            if overlap:
                shared_pairs.append((left, right))
                reasons.append(
                    f"通道 {left} 与 {right} 共享 {len(overlap)} 条证据"
                    f"（如 {overlap[:3]}）→ 同源自证风险"
                )

    return IsolationReport(
        valid=not reasons,
        shared_id_pairs=tuple(shared_pairs),
        unknown_probe_types=tuple(unknown),
        offending_roles=tuple(sorted(set(offending))),
        reasons=tuple(reasons),
    )


__all__ = [
    "CHANNEL_ROLES",
    "CHANNEL_PROBE_TYPES",
    "CHANNEL_TOOL_NAMES",
    "PROBE_TYPE_VOCABULARY",
    "EvidenceItem",
    "ChannelView",
    "IsolationReport",
    "partition_items",
    "shared_pool_views",
    "validate_isolation",
]
