"""LLM 全链路内容护栏（GUARDRAIL v1）。

设计口径见 docs/design/llm-guardrail-v1/DESIGN.md。三条铁律：
1. 全部判定为确定性规则（正则 / 编码解码 / 字符控制），不做、不宣称
   「AI 识别指令风险」——风险分级口径沿用 F10 的工具级声明。
2. reasons 只放规则 id，禁止放命中原文，防止审计表二次泄露。
3. fail-closed：护栏自身异常时按配置拒绝，绝不静默放行。
"""

from .contract import ALLOW, GuardDecision

__all__ = ["ALLOW", "GuardDecision"]
