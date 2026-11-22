"""离线确定性角色代理（P2-7 / A1 的可注入实现）。

为什么需要它：方案 §2.6 风险 2 指出真实模型下 4 角色 × 2 轮 × n 题的调用成本
不可控（qwen3:1.7b 实测约 5.4s/次）。因此协议评测默认走**离线确定性角色**，
真实 LLM 角色可在后续以同样的 ``RoleAgent`` 接口注入（协议不变）。

确定性规则的**诚实边界**（必须随结果一起引用）：

1. ``PROBE_TYPE_CANDIDATES`` 是**人工按探针语义拟定**的封闭候选词表，
   不是从数据里学出来的模型；
2. 它描述的是「探针类型 → 可能的根因组」，因此**准确率反映的是命名/语义
   一致性，不是推理能力**，不得写成「多 Agent 辩论提升准确率 X%」；
3. 本模块**不产出**任何概率模型意义上的置信度，``confidence`` 只是
   ``支持探针类型数 / 视图内证据数`` 的覆盖比。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence_channels import ChannelView
from .debate import Conclusion, Rebuttal

# ---------------------------------------------------------------------------
# 封闭候选词表：探针类型 → 可能的根因组（按语义拟定，显式声明）
# ---------------------------------------------------------------------------

PROBE_TYPE_CANDIDATES: dict[str, tuple[str, ...]] = {
    # 进程 / 日志 / 内核态
    "log_line": ("l4-systemd", "conf-disk"),
    "oom_kills": ("l4-oom",),
    "systemd_state": ("l4-systemd",),
    "process": ("l4-process", "l4-systemd", "l4-fd", "conf-port", "conf-drift"),
    # 指标 / 资源 / 数据库 / HTTP
    "metric_threshold": ("http-latency", "db-redis", "db-conn-pool", "db-slow-query"),
    "latency": ("http-latency",),
    "memory": ("l4-oom",),
    "disk_usage": ("conf-disk",),
    "inode_usage": ("conf-disk",),
    "fd_count": ("l4-fd", "conf-ulimit"),
    "db_replication_lag": ("db-repl-lag",),
    "connection_pool": ("db-conn-pool",),
    "cache_ping": ("db-redis",),
    "db_query": ("db-repl-lag", "db-conn-pool", "db-slow-query"),
    "slow_query": ("db-slow-query",),
    "http_status": ("net-502", "http-503", "http-404", "http-latency",
                    "http-tls", "net-dns"),
    "http_body": ("http-404",),
    # 网络 / 拓扑 / 接入
    "icmp": ("net-timeout", "net-partition", "net-502"),
    "tcp_connect": ("net-timeout", "net-dns", "net-502", "net-partition",
                    "ssh-bastion"),
    "port": ("l4-process", "conf-port"),
    "dns_lookup": ("net-dns",),
    "bastion_reachable": ("ssh-bastion",),
    "tls_cert": ("http-tls",),
    "ssh_auth": ("ssh-key", "ssh-password", "ssh-knownhosts"),
    "known_hosts": ("ssh-knownhosts", "ssh-password"),
    # 配置 / 变更
    "config_value": ("conf-drift", "conf-ulimit", "ssh-key"),
}

# 每个根因组被多少种探针类型指向 → 越少越「具体」，用于平票时排序。
_SPECIFICITY: dict[str, int] = {}
for _probe_type, _groups in PROBE_TYPE_CANDIDATES.items():
    for _group in _groups:
        _SPECIFICITY[_group] = _SPECIFICITY.get(_group, 0) + 1


@dataclass(frozen=True)
class RuleRoleAgent:
    """确定性规则角色：只看自己的通道视图，按声明的候选词表推理。

    裁决规则（平票时）：支持探针类型数多者优先 → 更具体（被更少探针类型
    指向）者优先 → 名称字典序（保证可复现）。
    """

    table: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(PROBE_TYPE_CANDIDATES)
    )

    # -- round 0 ----------------------------------------------------------

    def conclude(self, role: str, question: str, view: ChannelView) -> Conclusion:
        scored = self._score(view)
        if not scored:
            return Conclusion(
                role=role,
                top1=None,
                candidates=(),
                evidence=(),
                support=0,
                confidence=None,
                rationale=f"通道 {role} 内无证据，弃权（不参与结论）",
            )

        ranked = _rank(scored)
        top1 = ranked[0][0]
        supporting_probe_types = ranked[0][3]
        evidence = tuple(
            item.evidence_id
            for item in view.items
            if top1 in self.table.get(item.probe_type, ())
        )
        support = len(supporting_probe_types)
        confidence = round(support / len(view.items), 6) if view.items else None
        candidates = tuple(group for group, _, _, _ in ranked)
        return Conclusion(
            role=role,
            top1=top1,
            candidates=candidates,
            evidence=evidence,
            support=support,
            confidence=confidence,
            rationale=(
                f"通道内可见探针类型 {sorted(view.probe_types)} → "
                f"候选 {list(candidates)}；取支持面最广的 {top1}"
                f"（{support} 类探针支持）"
            ),
        )

    # -- round 1+ ---------------------------------------------------------

    def rebut(
        self,
        role: str,
        question: str,
        view: ChannelView,
        others: dict[str, Conclusion],
        previous: Conclusion,
    ) -> Rebuttal:
        # 弃权者保持弃权：没有自己通道的证据，就不能被「说服」，
        # 否则 converged 只是多数服从，不是辩论生效。
        if previous.top1 is None:
            return Rebuttal(
                role=role,
                agree_with=None,
                dispute=None,
                new_evidence=(),
                revised_top1=None,
                rationale="本通道无证据，维持弃权",
            )

        scored = self._score(view)
        my_top1 = previous.top1
        my_support = scored.get(my_top1, (0, 0, ()))[0]

        # 只在「对方结论落在我的候选集内，且对方证据面不弱于我」时改判
        candidates = set(previous.candidates) or {my_top1}
        best: Conclusion | None = None
        for other_role in sorted(others):
            other = others[other_role]
            if not other.top1 or other.top1 == my_top1:
                continue
            if other.top1 not in candidates:
                continue
            if other.support < my_support:
                continue
            if best is None or other.support > best.support:
                best = other

        if best is not None:
            new_evidence = tuple(
                eid for eid in best.evidence if eid not in set(previous.evidence)
            )
            return Rebuttal(
                role=role,
                agree_with=best.role,
                dispute=None,
                new_evidence=new_evidence,
                revised_top1=best.top1,
                rationale=(
                    f"采纳 {best.role} 的 {best.top1}：它落在我的候选集内，"
                    f"且对方证据面（{best.support}）不弱于我（{my_support}）"
                ),
            )

        dispute = (
            f"维持 {my_top1}：我的证据 {list(previous.evidence)} 指向它；"
            f"未见到落在候选集内且证据面更强的新证据"
        )
        return Rebuttal(
            role=role,
            agree_with=None,
            dispute=dispute,
            new_evidence=(),
            revised_top1=my_top1,
            rationale=dispute,
        )

    # -- 内部 -------------------------------------------------------------

    def _score(self, view: ChannelView) -> dict[str, tuple[int, int, tuple[str, ...]]]:
        """根因组 → (支持探针类型数, 具体度, 支持它的探针类型)。"""

        support: dict[str, list[str]] = {}
        for item in view.items:
            for group in self.table.get(item.probe_type, ()):
                support.setdefault(group, []).append(item.probe_type)
        return {
            group: (
                len(set(probe_types)),
                -_SPECIFICITY.get(group, 0),
                tuple(sorted(set(probe_types))),
            )
            for group, probe_types in support.items()
        }


def _rank(
    scored: dict[str, tuple[int, int, tuple[str, ...]]],
) -> list[tuple[str, int, int, tuple[str, ...]]]:
    """按 (支持数降序, 具体度降序, 名称升序) 排序，保证确定性。"""

    return sorted(
        (
            (group, value[0], value[1], value[2])
            for group, value in scored.items()
        ),
        key=lambda entry: (-entry[1], -entry[2], entry[0]),
    )


__all__ = ["PROBE_TYPE_CANDIDATES", "RuleRoleAgent"]
