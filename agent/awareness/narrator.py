"""简报叙述模板：不依赖任何模型也能产出人话版本。

作用：把 ``SecurityBrief`` 的结构化字段翻成"风险优先"的中文叙述。
模型可用时只负责润色，不允许改写风险等级、影响面、审批与证据口径。
"""

from __future__ import annotations

from typing import Any


class BriefNarrator:
    """确定性叙述器（纯字符串拼接，无外部依赖）。"""

    def narrate(self, brief: Any) -> str:
        """按"风险 → 影响面 → 前置 → 回滚 → 验证 → 审批 → 证据 → 置信度"输出。"""
        reasons = "、".join(getattr(brief, "risk_reasons", []) or []) or "规则未命中"
        lines = [f"【风险等级】{getattr(brief, 'risk_level', 'LOW')}（依据：{reasons}）"]

        attack_report = getattr(brief, "attack_report", "") or ""
        if attack_report:
            lines.append(f"【安全提示】{attack_report}")

        blast = getattr(brief, "blast_radius", {}) or {}
        assets = "、".join(blast.get("assets") or []) or "未识别"
        services = "、".join(blast.get("services") or []) or "未识别"
        users = blast.get("estimated_users")
        users_text = f"{users} 人（规则估算）" if isinstance(users, int) else "未运行/无数据"
        lines.append(f"【影响面】资产：{assets}；服务：{services}；影响用户：{users_text}")

        preconditions = getattr(brief, "preconditions", []) or []
        if preconditions:
            lines.append("【执行前置】" + "；".join(preconditions))

        rollback = getattr(brief, "rollback_plan", "") or "未声明（不允许无回滚执行）"
        lines.append(f"【回滚方案】{rollback}")

        verification = getattr(brief, "verification_plan", []) or []
        if verification:
            lines.append("【验证方案】" + "；".join(verification))

        approvals = getattr(brief, "required_approvals", []) or []
        if approvals:
            lines.append("【所需审批】" + "、".join(approvals))

        evidence = getattr(brief, "evidence_refs", []) or []
        lines.append("【证据】" + ("、".join(evidence) if evidence else "无"))

        requires_human = bool(getattr(brief, "requires_human", False))
        lines.append(
            f"【置信度】{getattr(brief, 'confidence', 0.0)}；需人工确认：{'是' if requires_human else '否'}"
        )
        lines.append(f"【诚实说明】{getattr(brief, 'honesty_note', '')}")
        return "\n".join(lines)


__all__ = ["BriefNarrator"]
