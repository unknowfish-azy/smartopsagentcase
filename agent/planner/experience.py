"""失败复盘沉淀（P5）：PlanRunner 失败终止后，把教训写回运维记忆。

复用 backend 的内部记忆接口 ``POST /api/internal/memory/experience``（recordLearned，
DECISION_LOOP 类型），下一次 chat 召回时即可注入「以后遇到 X 先 Y」式教训。

与 ``agent/recovery_contracts/publisher.py`` 的关键语义差异：这里**全程 fail-open**——
配置缺失、网络失败、非 2xx 一律记 warning 后吞掉，绝不把上报失败冒泡进执行链路；
复盘沉淀是锦上添花，不是主链路的一环。
"""

from __future__ import annotations

import json
import logging
import os
import re
from urllib import request as urllib_request

from agent.recovery_contracts.publisher import (
    ENV_BACKEND_URL,
    ENV_INTERNAL_TOKEN,
    INTERNAL_TOKEN_HEADER,
)

logger = logging.getLogger(__name__)

# 与 recovery publisher 相同的两个 env；未配置就不上报（不视为错误）。
EXPERIENCE_ENDPOINT = "/api/internal/memory/experience"

# 失败终态：只有这两种 status 值得上报教训（completed 不需要）。
FAILURE_STATUSES = {"failed", "reflection_budget_exhausted"}

# goal 常见的动词前缀：剥掉后更适合做 recall 的子串匹配 incident_key。
_GOAL_VERB_PREFIXES = (
    "请", "帮我", "麻烦", "排查", "检查", "处理", "修复", "解决", "诊断", "巡检", "分析",
)

_MAX_INCIDENT_KEY = 40


def incident_key_from_goal(goal: str) -> str:
    """从目标提取 incident_key：剥动词前缀、去空白、截断。

    recall 的匹配方向是「incident_key ⊂ 用户这句话」，所以这里尽量保留
    名词性关键词（如「nginx 502」），去掉口语动词前缀。
    """
    text = re.sub(r"\s+", " ", str(goal or "")).strip()
    changed = True
    while changed and text:
        changed = False
        for prefix in _GOAL_VERB_PREFIXES:
            if text.startswith(prefix) and len(text) > len(prefix):
                text = text[len(prefix):].strip()
                changed = True
    return text[:_MAX_INCIDENT_KEY]


def lesson_from_outcome(outcome) -> str:
    """把失败结果凝练成一句教训（preferred_action）。

    取最后一轮的失败步骤：工具名 + 错误分类 + 错误信息，并注明
    重规划仍未解决、需人工核实——这不是可自动执行的指令。
    """
    final = outcome.final_result
    failures = [r for r in (final.step_results if final else []) if not r.success]
    details = "; ".join(
        "步骤{sid}[{tool}] {cat}: {err}".format(
            sid=r.metadata.get("step_id", "?"),
            tool=r.tool_name,
            cat=r.error_category or "UNKNOWN",
            err=(r.error or "无错误信息")[:120],
        )
        for r in failures
    )
    if not details:
        details = outcome.reason or "失败原因未记录"
    rounds = len(outcome.plan_results)
    return (
        f"历史运行失败教训（{rounds} 轮重规划仍未解决）：{details}。"
        "再次遇到该问题时先核实上述失败环节，不要重复同样路径，必要时人工介入。"
    )


class ExperienceSink:
    """失败复盘上报器：只上报失败终态，全链路 fail-open。"""

    def __init__(
        self,
        backend_url: str | None = None,
        internal_token: str | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        # 不在构造期抛错：配置读取延迟到 report，缺配置只 warning。
        self._backend_url = backend_url
        self._internal_token = internal_token
        self.timeout = timeout

    def report(self, outcome, user_id: str | None = None) -> bool:
        """失败终态时上报教训；返回是否实际发出。任何异常都不冒泡。"""
        try:
            return self._report(outcome, user_id)
        except Exception as exc:  # noqa: BLE001 - 复盘上报绝不阻塞执行链路
            logger.warning(
                "experience.report failed plan_id=%s: %s",
                outcome.plan_ids[-1] if outcome.plan_ids else "-",
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _report(self, outcome, user_id) -> bool:
        if outcome.status not in FAILURE_STATUSES:
            return False
        numeric = str(user_id or "").strip()
        if not numeric.isdigit():
            # 记忆表按数字 userId 隔离；匿名/非数字会话没有归属，跳过。
            return False
        backend_url = str(
            self._backend_url if self._backend_url is not None
            else os.getenv(ENV_BACKEND_URL, "")
        ).strip()
        token = str(
            self._internal_token if self._internal_token is not None
            else os.getenv(ENV_INTERNAL_TOKEN, "")
        ).strip()
        if not backend_url or not token:
            logger.warning(
                "experience.skip plan_id=%s: 缺少 %s/%s，不上报复盘教训",
                outcome.plan_ids[-1] if outcome.plan_ids else "-",
                ENV_BACKEND_URL, ENV_INTERNAL_TOKEN,
            )
            return False

        plan_id = outcome.plan_ids[-1] if outcome.plan_ids else "unknown"
        payload = {
            "userId": int(numeric),
            "incidentKey": incident_key_from_goal(outcome.goal),
            "preferredAction": lesson_from_outcome(outcome),
            "sourceRefs": f"PLAN_RUN:{plan_id}",
        }
        if not payload["incidentKey"]:
            return False
        request = urllib_request.Request(
            backend_url.rstrip("/") + EXPERIENCE_ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                INTERNAL_TOKEN_HEADER: token,
            },
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=self.timeout) as response:
            response.read()
        logger.info(
            "experience.reported plan_id=%s user_id=%s incident_key=%s",
            plan_id, numeric, payload["incidentKey"],
        )
        return True

    # PlanRunner 挂点用的回调别名：失败终态时调用，任何异常内部已兜底。
    def on_run_finished(self, outcome, context) -> bool:
        return self.report(outcome, getattr(context, "user_id", None))


__all__ = [
    "ENV_BACKEND_URL",
    "ENV_INTERNAL_TOKEN",
    "EXPERIENCE_ENDPOINT",
    "FAILURE_STATUSES",
    "ExperienceSink",
    "incident_key_from_goal",
    "lesson_from_outcome",
]
