"""多 Agent 辩论协议（P2-7 / A1）。

方案口径：`docs/design/p2-7-causal-kg-debate-v1/DESIGN.md` §2。

协议（可机检）
------------

    round 0（独立）：每角色产 conclusion_i = {top1, candidates[], evidence[ids], rationale}
    round 1+（反驳）：每角色看到「他人 top1 集合 + 各自 evidence id」，必须产出
                      rebuttal_i = {agree_with, dispute, new_evidence, revised_top1}
    仲裁：按最后一轮 top1 的一致性判 converged / escalated

三条判据（都落盘，可机检）
------------------------

- ``converged``：最后一轮所有**未弃权**角色 ``top1`` 相同；
- ``changed``：至少一个角色在反驳后改了 ``top1``（说明反驳真的起了作用）；
- ``escalated``：达到最大轮数仍不一致 → **如实记为未收敛**，不得粉饰成「达成一致」。

本模块只做协议与判定，**不做**推理：推理由可注入的 ``RoleAgent`` 提供，
因此同一协议既能跑真实 LLM 角色，也能跑离线确定性角色（见 ``debate_rules.py``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from .base import SubAgentSpec
from .evidence_channels import CHANNEL_TOOL_NAMES, ChannelView

# ---------------------------------------------------------------------------
# 角色声明（直接复用 SubAgentSpec，不新建编排框架）
# ---------------------------------------------------------------------------

DEBATE_ROLES: tuple[SubAgentSpec, ...] = (
    SubAgentSpec(
        name="log_diagnosis",
        title="日志诊断",
        description="从进程 / 日志 / 内核态信号找故障现象与时间点",
        keywords=("日志", "log", "报错", "进程", "oom"),
        tool_names=CHANNEL_TOOL_NAMES["log_diagnosis"],
    ),
    SubAgentSpec(
        name="metric_inspector",
        title="指标巡查",
        description="从指标越界与资源水位定位异常面",
        keywords=("指标", "metric", "阈值", "水位", "内存", "磁盘"),
        tool_names=CHANNEL_TOOL_NAMES["metric_inspector"],
    ),
    SubAgentSpec(
        name="topology_inspector",
        title="拓扑巡查",
        description="从网络可达性与依赖传播定位候选根因",
        keywords=("网络", "拓扑", "连通", "依赖", "dns", "证书"),
        tool_names=CHANNEL_TOOL_NAMES["topology_inspector"],
    ),
    SubAgentSpec(
        name="change_auditor",
        title="变更审计",
        description="关联近期配置变更，判断是否变更引入",
        keywords=("变更", "配置", "发布", "审计", "config"),
        tool_names=CHANNEL_TOOL_NAMES["change_auditor"],
    ),
)

DEBATE_ROLE_NAMES: tuple[str, ...] = tuple(role.name for role in DEBATE_ROLES)


# ---------------------------------------------------------------------------
# 协议数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Conclusion:
    """round 0 的独立结论（或反驳后的修订结论）。"""

    role: str
    top1: str | None
    candidates: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    support: int = 0
    confidence: float | None = None
    rationale: str = ""


@dataclass(frozen=True)
class Rebuttal:
    """round 1+ 的反驳：必须明确「同意谁」或「不同意什么」（具体到证据 id）。"""

    role: str
    agree_with: str | None
    dispute: str | None
    new_evidence: tuple[str, ...] = ()
    revised_top1: str | None = None
    rationale: str = ""


@dataclass(frozen=True)
class Verdict:
    """仲裁结果。``status`` 只有 ``converged`` / ``escalated`` 两个取值。"""

    status: str
    converged: bool
    changed: bool
    changed_roles: tuple[str, ...]
    final_top1: str | None
    agree_roles: tuple[str, ...]
    abstain_roles: tuple[str, ...]
    rounds: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "converged": self.converged,
            "changed": self.changed,
            "changed_roles": list(self.changed_roles),
            "final_top1": self.final_top1,
            "agree_roles": list(self.agree_roles),
            "abstain_roles": list(self.abstain_roles),
            "rounds": self.rounds,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DebateRecord:
    """一场辩论的完整留痕。"""

    question: str
    rounds: tuple[dict[str, Conclusion], ...]
    rebuttals: tuple[dict[str, Rebuttal], ...]
    verdict: Verdict
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "rounds": {
                index: {role: _conclusion_to_dict(c) for role, c in round_.items()}
                for index, round_ in enumerate(self.rounds)
            },
            "rebuttals": {
                index: {role: _rebuttal_to_dict(r) for role, r in round_.items()}
                for index, round_ in enumerate(self.rebuttals)
            },
            "verdict": self.verdict.to_dict(),
            "metadata": self.metadata,
        }


def _conclusion_to_dict(conclusion: Conclusion) -> dict:
    return {
        "role": conclusion.role,
        "top1": conclusion.top1,
        "candidates": list(conclusion.candidates),
        "evidence": list(conclusion.evidence),
        "support": conclusion.support,
        "confidence": conclusion.confidence,
        "rationale": conclusion.rationale,
    }


def _rebuttal_to_dict(rebuttal: Rebuttal) -> dict:
    return {
        "role": rebuttal.role,
        "agree_with": rebuttal.agree_with,
        "dispute": rebuttal.dispute,
        "new_evidence": list(rebuttal.new_evidence),
        "revised_top1": rebuttal.revised_top1,
        "rationale": rebuttal.rationale,
    }


# ---------------------------------------------------------------------------
# 纯函数判定（门禁 A-G1）
# ---------------------------------------------------------------------------


def detect_changes(
    initial: dict[str, Conclusion],
    final: dict[str, Conclusion],
) -> tuple[str, ...]:
    """返回 ``top1`` 发生变化的角色（含「弃权 → 有结论」与「有结论 → 弃权」）。"""

    roles = sorted(set(initial) | set(final))
    return tuple(
        role for role in roles
        if _top1(initial.get(role)) != _top1(final.get(role))
    )


def judge_verdict(
    initial: dict[str, Conclusion],
    final: dict[str, Conclusion],
    *,
    rounds: int,
    max_rounds: int,
) -> Verdict:
    """仲裁：只看最后一轮 ``top1`` 的一致性。

    - 未弃权角色的 ``top1`` 全相同 → ``converged``；
    - 否则（含全部弃权、或仍有分歧）→ ``escalated``，此时 ``final_top1=None``，
      **不得**给出单一结论。
    """

    roles = sorted(set(final) | set(initial))
    active = [role for role in roles if _top1(final.get(role))]
    abstain = [role for role in roles if not _top1(final.get(role))]
    distinct = sorted({_top1(final[role]) for role in active})

    changed_roles = detect_changes(initial, final)
    converged = bool(active) and len(distinct) == 1

    if converged:
        status = "converged"
        final_top1 = distinct[0]
        reason = f"第 {rounds} 轮后 {len(active)} 个角色一致收敛到 {final_top1}"
        if changed_roles:
            reason += f"；{len(changed_roles)} 个角色在反驳后修正了结论"
    else:
        status = "escalated"
        final_top1 = None
        if not active:
            reason = f"第 {rounds} 轮后全部角色弃权，无结论（未收敛）"
        else:
            reason = (
                f"第 {rounds} 轮后仍有分歧：{distinct}；"
                f"如实记为未收敛（轮数上限 {max_rounds}）"
            )

    return Verdict(
        status=status,
        converged=converged,
        changed=bool(changed_roles),
        changed_roles=changed_roles,
        final_top1=final_top1,
        agree_roles=tuple(active) if converged else (),
        abstain_roles=tuple(abstain),
        rounds=rounds,
        reason=reason,
    )


def _top1(conclusion: Conclusion | None) -> str | None:
    return None if conclusion is None else conclusion.top1


# ---------------------------------------------------------------------------
# 角色代理接口与运行器
# ---------------------------------------------------------------------------


class RoleAgent(Protocol):
    """角色代理：由调用方注入真实 LLM 实现或离线确定性实现。"""

    def conclude(self, role: str, question: str, view: ChannelView) -> Conclusion:
        """round 0：只看自己的通道视图，独立给结论。"""

    def rebut(
        self,
        role: str,
        question: str,
        view: ChannelView,
        others: dict[str, Conclusion],
        previous: Conclusion,
    ) -> Rebuttal:
        """round 1+：看到他人 top1 与证据 id 后，选择同意 / 反驳 / 修正。"""


class DebateRunner:
    """辩论运行器：协议固定，推理注入。

    ``max_rebuttal_rounds`` 是**反驳轮**上限（不含 round 0）。第 1 轮反驳必跑
    （否则 ``changed`` 恒为假），之后仅在未收敛时继续。
    """

    def __init__(
        self,
        agent: RoleAgent,
        roles: Sequence[SubAgentSpec] = DEBATE_ROLES,
        max_rebuttal_rounds: int = 2,
    ) -> None:
        if max_rebuttal_rounds < 1:
            raise ValueError("max_rebuttal_rounds 至少为 1")
        self.agent = agent
        self.roles = tuple(roles)
        self.role_names = tuple(role.name for role in self.roles)
        self.max_rebuttal_rounds = max_rebuttal_rounds

    def run(
        self,
        question: str,
        views: dict[str, ChannelView],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> DebateRecord:
        missing = [role for role in self.role_names if role not in views]
        if missing:
            raise ValueError(f"缺少通道视图：{missing}")

        initial = {
            role: self.agent.conclude(role, question, views[role])
            for role in self.role_names
        }
        rounds: list[dict[str, Conclusion]] = [dict(initial)]
        rebuttals: list[dict[str, Rebuttal]] = []
        current = dict(initial)

        for round_index in range(1, self.max_rebuttal_rounds + 1):
            others_by_role = {
                role: {
                    other: current[other]
                    for other in self.role_names
                    if other != role
                }
                for role in self.role_names
            }
            round_rebuttals = {
                role: self.agent.rebut(
                    role, question, views[role], others_by_role[role], current[role]
                )
                for role in self.role_names
            }
            rebuttals.append(round_rebuttals)

            revised = dict(current)
            for role, rebuttal in round_rebuttals.items():
                before = current[role]
                revised[role] = Conclusion(
                    role=role,
                    top1=rebuttal.revised_top1,
                    candidates=before.candidates,
                    evidence=tuple(dict.fromkeys(before.evidence + rebuttal.new_evidence)),
                    support=before.support,
                    confidence=before.confidence,
                    rationale=rebuttal.rationale or before.rationale,
                )
            current = revised
            rounds.append(dict(current))

            probe = judge_verdict(initial, current, rounds=round_index,
                                  max_rounds=self.max_rebuttal_rounds)
            if probe.converged:
                break

        verdict = judge_verdict(
            initial, current,
            rounds=len(rebuttals),
            max_rounds=self.max_rebuttal_rounds,
        )
        return DebateRecord(
            question=question,
            rounds=tuple(rounds),
            rebuttals=tuple(rebuttals),
            verdict=verdict,
            metadata=dict(metadata or {}),
        )


__all__ = [
    "DEBATE_ROLES",
    "DEBATE_ROLE_NAMES",
    "Conclusion",
    "Rebuttal",
    "Verdict",
    "DebateRecord",
    "RoleAgent",
    "DebateRunner",
    "detect_changes",
    "judge_verdict",
]
