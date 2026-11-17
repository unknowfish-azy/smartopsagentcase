"""声明式规则匹配基类：regex 规则编译缓存 + operation 精确匹配。"""

from __future__ import annotations

import re

from .models import BaselineRule


class RegexRuleGate:
    """规则闸门：对命令文本走正则，对 "工具.动作" 走精确名匹配。"""

    def __init__(self, rules: list[BaselineRule]) -> None:
        self._rules = list(rules)
        self._regex_rules: list[tuple[BaselineRule, re.Pattern[str]]] = []
        self._operation_rules: list[BaselineRule] = []
        for rule in self._rules:
            if rule.match == "operation":
                self._operation_rules.append(rule)
            else:
                self._regex_rules.append((rule, re.compile(rule.pattern, re.IGNORECASE)))

    def match_text(self, text: str) -> BaselineRule | None:
        if not text:
            return None
        for rule, pattern in self._regex_rules:
            if pattern.search(text):
                return rule
        return None

    def match_operation(self, operation: str) -> BaselineRule | None:
        if not operation:
            return None
        for rule in self._operation_rules:
            if rule.pattern == operation:
                return rule
        return None

    @property
    def rules(self) -> list[BaselineRule]:
        return list(self._rules)
