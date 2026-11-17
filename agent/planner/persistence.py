"""计划持久化与断点续跑（P1）。

把计划的执行状态落盘：哪些步骤已成功、哪些失败、整体状态。
服务重启 / 任务中断后，可以从最近 checkpoint 恢复，
已成功的步骤不重复执行（对写操作尤其关键）。

存储后端只需要提供 `save(key, dict)` / `load(key)` 两个方法，
`FileStorage` 即满足；后续可平滑替换为 Redis/MySQL 实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .steps import PlanStep


class KeyValueStorage(Protocol):
    """最小存储契约：与 FileStorage 对齐。"""

    def save(self, key: str, value: dict[str, Any]) -> None: ...

    def load(self, key: str) -> dict[str, Any] | None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlanRunState:
    """一次计划执行的持久化状态。"""

    plan_id: str

    goal: str

    steps: list[dict[str, Any]] = field(default_factory=list)

    # [{step_id, success, error_category, error, recorded_at}]
    outcomes: list[dict[str, Any]] = field(default_factory=list)

    status: str = "running"  # running / completed / aborted_fatal / aborted_loop / max_rounds_exceeded / failed

    updated_at: str = field(default_factory=_now)

    @property
    def completed_step_ids(self) -> set[int]:
        return {
            int(item["step_id"])
            for item in self.outcomes
            if item.get("success")
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": self.steps,
            "outcomes": self.outcomes,
            "status": self.status,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanRunState":
        return cls(
            plan_id=str(data["plan_id"]),
            goal=str(data.get("goal", "")),
            steps=list(data.get("steps") or []),
            outcomes=list(data.get("outcomes") or []),
            status=str(data.get("status", "running")),
            updated_at=str(data.get("updated_at", "")),
        )


class PlanStore:
    """计划状态存储（断点续跑）。"""

    def __init__(self, storage: KeyValueStorage) -> None:
        self._storage = storage

    def create(
        self,
        plan_id: str,
        goal: str,
        steps: list[PlanStep],
    ) -> PlanRunState:
        state = PlanRunState(
            plan_id=plan_id,
            goal=goal,
            steps=[step.to_dict() for step in steps],
        )
        self._persist(state)
        return state

    def load(self, plan_id: str) -> PlanRunState | None:
        data = self._storage.load(f"plan:{plan_id}")
        return PlanRunState.from_dict(data) if data else None

    def record_step(
        self,
        plan_id: str,
        step_id: int,
        success: bool,
        error_category: str | None = None,
        error: str | None = None,
    ) -> PlanRunState | None:
        """每步执行完立即落盘 checkpoint（幂等：同一步骤重复记录以最新为准）。"""

        state = self.load(plan_id)
        if state is None:
            return None

        state.outcomes = [
            item for item in state.outcomes
            if int(item.get("step_id", -1)) != int(step_id)
        ]
        state.outcomes.append({
            "step_id": step_id,
            "success": success,
            "error_category": error_category,
            "error": error,
            "recorded_at": _now(),
        })
        state.updated_at = _now()
        self._persist(state)
        return state

    def finish(self, plan_id: str, status: str) -> PlanRunState | None:
        state = self.load(plan_id)
        if state is None:
            return None
        state.status = status
        state.updated_at = _now()
        self._persist(state)
        return state

    def remaining_steps(
        self,
        plan_id: str,
        *,
        skip_succeeded: bool = True,
    ) -> list[PlanStep]:
        """取尚未成功（或全部）的步骤，用于断点续跑。"""

        state = self.load(plan_id)
        if state is None:
            return []
        done = state.completed_step_ids if skip_succeeded else set()
        return [
            PlanStep.from_dict(item)
            for item in state.steps
            if int(item.get("step_id", -1)) not in done
        ]

    def _persist(self, state: PlanRunState) -> None:
        self._storage.save(f"plan:{state.plan_id}", state.to_dict())


__all__ = [
    "KeyValueStorage",
    "PlanRunState",
    "PlanStore",
]
