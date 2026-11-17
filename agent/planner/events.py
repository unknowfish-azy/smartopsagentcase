"""事件溯源（P4，蒸馏 AgentForge 的 Event Sourcing 层）。

AgentForge 机制：所有变化都记 run event，状态由事件推导；回放免费
（纯本地遍历事件流，不调模型不花 token）；可按序号回滚（截断重建）。

本实现：
* ``RunEvent``      单条事件（seq 单调递增 / 类型 / 载荷）；
* ``EventStream``   append-only 事件流：内存列表 + KeyValueStorage 持久化；
* ``derive_state``  从事件流**推导**运行状态（ReplayState）——状态是事件的函数，
                    不依赖快照；
* ``replay``        输出可读时间线（零模型调用，成本恒为 0）；
* ``rollback_to``   截断 seq 之后的事件（回滚 = 回到事件序列某一点）。

诚实口径：
* 持久化用 KeyValueStorage 全量重写——事件量小（单任务 < 数百条）时足够，
  生产换 Redis Stream / MySQL append-only 表时接口不变；
* step 级事件由执行层调用方插入（Executor 未侵入），当前 PlanRunner
  记录 plan/round/reflection 粒度，step 粒度由 PlanStore checkpoint 覆盖。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent.planner.persistence import KeyValueStorage

logger = logging.getLogger(__name__)

# 事件类型常量（当前 runner 层粒度；step_* 预留给执行层挂钩）
EVENT_PLAN_CREATED = "plan_created"
EVENT_PLAN_FINISHED = "plan_finished"
EVENT_REFLECTION = "reflection"
EVENT_RUN_FINISHED = "run_finished"
EVENT_STEP_STARTED = "step_started"
EVENT_STEP_FINISHED = "step_finished"


@dataclass
class RunEvent:
    """单条溯源事件。seq 在流内单调递增，是回放与回滚的定位锚点。"""

    seq: int
    ts: str
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "ts": self.ts, "type": self.type, "payload": self.payload}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunEvent":
        return cls(
            seq=int(data["seq"]),
            ts=str(data.get("ts", "")),
            type=str(data["type"]),
            payload=dict(data.get("payload") or {}),
        )


@dataclass
class ReplayState:
    """由事件流推导出的运行状态（状态 = f(事件)，不依赖快照）。"""

    run_id: str
    plan_ids: list[str] = field(default_factory=list)
    planners: list[str] = field(default_factory=list)
    steps_started: set[int] = field(default_factory=set)
    steps_finished: dict[int, bool] = field(default_factory=dict)  # step_id -> success
    reflections: int = 0
    status: str = "running"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan_ids": self.plan_ids,
            "planners": self.planners,
            "steps_started": sorted(self.steps_started),
            "steps_finished": {str(k): v for k, v in sorted(self.steps_finished.items())},
            "reflections": self.reflections,
            "status": self.status,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class EventStream:
    """一次运行（run）的 append-only 事件流。

    用法：``stream = EventStream(storage, run_id)``（自动加载已有事件），
    ``stream.append(type, **payload)`` 追加，``stream.derive_state()`` 推导，
    ``stream.rollback_to(seq)`` 回滚，``stream.replay()`` 免费回放。
    """

    def __init__(self, storage: KeyValueStorage, run_id: str) -> None:
        self.storage = storage
        self.run_id = run_id
        self._key = f"events:{run_id}"
        raw = storage.load(self._key)
        self._events: list[RunEvent] = (
            [RunEvent.from_dict(item) for item in raw.get("events", [])] if raw else []
        )

    # -- 写入 ----------------------------------------------------------------

    def append(self, event_type: str, **payload: Any) -> RunEvent:
        seq = (self._events[-1].seq if self._events else 0) + 1
        event = RunEvent(seq=seq, ts=_now(), type=event_type, payload=payload)
        self._events.append(event)
        self._persist()
        return event

    def _persist(self) -> None:
        self.storage.save(
            self._key,
            {"run_id": self.run_id, "events": [event.to_dict() for event in self._events]},
        )

    # -- 读取 ----------------------------------------------------------------

    def events(self) -> list[RunEvent]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

    # -- 推导 / 回放 / 回滚 --------------------------------------------------

    def derive_state(self) -> ReplayState:
        """重放事件流推导状态——纯本地计算，零模型调用。"""

        state = ReplayState(run_id=self.run_id)
        for event in self._events:
            payload = event.payload
            if event.type == EVENT_PLAN_CREATED:
                state.plan_ids.append(str(payload.get("plan_id", "")))
                state.planners.append(str(payload.get("planner", "")))
            elif event.type == EVENT_STEP_STARTED:
                state.steps_started.add(int(payload.get("step_id", 0)))
            elif event.type == EVENT_STEP_FINISHED:
                state.steps_finished[int(payload.get("step_id", 0))] = bool(
                    payload.get("success", False)
                )
            elif event.type == EVENT_REFLECTION:
                state.reflections += 1
            elif event.type == EVENT_RUN_FINISHED:
                state.status = str(payload.get("status", "finished"))
        return state

    def replay(self) -> list[dict[str, Any]]:
        """时间线回放：事件顺序 + 摘要。免费——不调任何模型。"""

        return [
            {
                "seq": event.seq,
                "ts": event.ts,
                "type": event.type,
                "summary": _summarize(event),
            }
            for event in self._events
        ]

    def rollback_to(self, seq: int) -> int:
        """一键回滚：截断 seq 之后（不含 seq）的所有事件。返回保留条数。"""

        kept = [event for event in self._events if event.seq <= seq]
        removed = len(self._events) - len(kept)
        self._events = kept
        self._persist()
        logger.info("event_stream.rollback run=%s kept=%s removed=%s", self.run_id, len(kept), removed)
        return len(kept)


def _summarize(event: RunEvent) -> str:
    payload = event.payload
    if event.type == EVENT_PLAN_CREATED:
        return f"规划产出 {payload.get('plan_id')}（{payload.get('planner')}，{payload.get('step_count')} 步）"
    if event.type == EVENT_PLAN_FINISHED:
        return f"计划 {payload.get('plan_id')} 执行完毕: {payload.get('status')}"
    if event.type == EVENT_REFLECTION:
        return f"反思评审: {payload.get('decision')} — {payload.get('reason', '')}"
    if event.type == EVENT_STEP_STARTED:
        return f"步骤 {payload.get('step_id')} 开始"
    if event.type == EVENT_STEP_FINISHED:
        result = "成功" if payload.get("success") else "失败"
        return f"步骤 {payload.get('step_id')} {result}"
    if event.type == EVENT_RUN_FINISHED:
        return f"运行结束: {payload.get('status')}"
    return event.type


__all__ = [
    "EventStream",
    "ReplayState",
    "RunEvent",
    "EVENT_PLAN_CREATED",
    "EVENT_PLAN_FINISHED",
    "EVENT_REFLECTION",
    "EVENT_RUN_FINISHED",
    "EVENT_STEP_STARTED",
    "EVENT_STEP_FINISHED",
]
