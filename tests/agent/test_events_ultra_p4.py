"""P4 测试：事件溯源（EventStream）+ Ultra 多路择优（UltraRunner）。

蒸馏自 AgentForge：状态由事件推导、回放免费不调模型、一键回滚、
同一环节并行多路不同取向 → 择优 → 校准。
"""

import time

import pytest

from agent.planner.events import (
    EVENT_PLAN_CREATED,
    EVENT_PLAN_FINISHED,
    EVENT_REFLECTION,
    EVENT_RUN_FINISHED,
    EVENT_STEP_FINISHED,
    EVENT_STEP_STARTED,
    EventStream,
)
from agent.planner.runner import PlanRunner
from agent.providers.storage.file import FileStorage
from agent.ultra import ULTRA_PERSONAS, UltraError, UltraRunner


class MemoryStorage:
    """最小 KeyValueStorage 内存实现（接口与 FileStorage 一致）。"""

    def __init__(self):
        self.data: dict[str, dict] = {}

    def save(self, key, value):
        self.data[key] = value

    def load(self, key):
        return self.data.get(key)


# ---------------------------------------------------------------------------
# EventStream 基础
# ---------------------------------------------------------------------------


def test_event_stream_append_assigns_monotonic_seq():
    stream = EventStream(MemoryStorage(), "run-1")
    first = stream.append(EVENT_PLAN_CREATED, plan_id="p1", planner="rule", step_count=2)
    second = stream.append(EVENT_RUN_FINISHED, status="completed")
    assert first.seq == 1 and second.seq == 2
    assert len(stream) == 2


def test_event_stream_events_returns_copy():
    stream = EventStream(MemoryStorage(), "run-1")
    stream.append(EVENT_PLAN_CREATED, plan_id="p1")
    events = stream.events()
    events.clear()
    assert len(stream) == 1  # 外部改动不影响内部


def test_event_stream_persists_and_reloads():
    storage = MemoryStorage()
    stream = EventStream(storage, "run-1")
    stream.append(EVENT_PLAN_CREATED, plan_id="p1", planner="llm", step_count=3)
    stream.append(EVENT_RUN_FINISHED, status="completed")

    reloaded = EventStream(storage, "run-1")
    assert len(reloaded) == 2
    assert reloaded.events()[0].payload["plan_id"] == "p1"


def test_event_stream_derive_state_rebuilds_from_events():
    stream = EventStream(MemoryStorage(), "run-1")
    stream.append(EVENT_PLAN_CREATED, plan_id="p1", planner="rule", step_count=2)
    stream.append(EVENT_STEP_STARTED, step_id=1)
    stream.append(EVENT_STEP_FINISHED, step_id=1, success=True)
    stream.append(EVENT_STEP_STARTED, step_id=2)
    stream.append(EVENT_STEP_FINISHED, step_id=2, success=False)
    stream.append(EVENT_REFLECTION, decision="replan", reason="步骤2失败")
    stream.append(EVENT_RUN_FINISHED, status="failed")

    state = stream.derive_state()
    assert state.plan_ids == ["p1"]
    assert state.planners == ["rule"]
    assert state.steps_started == {1, 2}
    assert state.steps_finished == {1: True, 2: False}
    assert state.reflections == 1
    assert state.status == "failed"


def test_event_stream_empty_derives_running():
    assert EventStream(MemoryStorage(), "run-x").derive_state().status == "running"


def test_event_stream_rollback_truncates_after_seq():
    stream = EventStream(MemoryStorage(), "run-1")
    stream.append(EVENT_PLAN_CREATED, plan_id="p1")
    stream.append(EVENT_PLAN_FINISHED, plan_id="p1", status="aborted")
    stream.append(EVENT_RUN_FINISHED, status="failed")

    kept = stream.rollback_to(2)  # 回滚到 plan_finished，撤销 run_finished

    assert kept == 2
    assert len(stream) == 2
    assert [event.type for event in stream.events()] == [EVENT_PLAN_CREATED, EVENT_PLAN_FINISHED]
    assert stream.derive_state().status == "running"


def test_event_stream_rollback_persists_truncation():
    storage = MemoryStorage()
    stream = EventStream(storage, "run-1")
    stream.append(EVENT_PLAN_CREATED, plan_id="p1")
    stream.append(EVENT_RUN_FINISHED, status="failed")
    stream.rollback_to(1)

    reloaded = EventStream(storage, "run-1")
    assert len(reloaded) == 1


def test_replay_is_free_and_readable():
    """回放零模型调用：时间线摘要完整、顺序正确。"""

    stream = EventStream(MemoryStorage(), "run-1")
    stream.append(EVENT_PLAN_CREATED, plan_id="p1", planner="rule", step_count=2)
    stream.append(EVENT_STEP_FINISHED, step_id=1, success=False)
    stream.append(EVENT_RUN_FINISHED, status="failed")

    timeline = stream.replay()
    assert len(timeline) == 3
    assert timeline[0]["seq"] == 1 and "p1" in timeline[0]["summary"]
    assert "失败" in timeline[1]["summary"]
    assert "failed" in timeline[2]["summary"]
    assert [item["seq"] for item in timeline] == [1, 2, 3]


def test_replay_state_round_trip_to_dict():
    stream = EventStream(MemoryStorage(), "run-1")
    stream.append(EVENT_PLAN_CREATED, plan_id="p1", planner="llm", step_count=1)
    state = stream.derive_state()
    data = state.to_dict()
    assert data["plan_ids"] == ["p1"]
    assert data["status"] == "running"


# ---------------------------------------------------------------------------
# PlanRunner 事件流集成
# ---------------------------------------------------------------------------


def test_runner_emits_full_event_sequence(tmp_path):
    """用最小 stub 件跑通 runner，校验事件序列完整。"""

    class _Plan:
        def __init__(self, steps):
            self.steps = steps
            self.planner = "rule"

    class _Result:
        def __init__(self, success, status="completed"):
            self.success = success
            self.status = status

    class _Planner:
        def __init__(self, steps):
            self._steps = steps

        def create_plan(self, goal, failure_context=None):
            return _Plan(self._steps)

    class _Executor:
        def __init__(self, success):
            self.success = success

        def execute_plan(self, steps, context, **kwargs):
            return _Result(self.success)

    class _Reflector:
        def __init__(self):
            self.calls = 0

        def review(self, goal, result):
            self.calls += 1
            first_round = self.calls == 1

            class _Verdict:
                decision = "replan" if first_round else "stop"
                reason = "第一轮建议重规划" if first_round else "评审不通过"
                failed_step_ids = [1]

            return _Verdict()

    storage = FileStorage(tmp_path / "events")
    stream = EventStream(storage, "run-e2e")
    runner = PlanRunner(
        planner=_Planner([1, 2]),
        executor=_Executor(False),
        reflector=_Reflector(),
        event_stream=stream,
        max_execution_rounds=2,
    )

    outcome = runner.run("目标", context=object())

    assert outcome.status == "failed"
    types = [event.type for event in stream.events()]
    # 第一轮 replan → 第二轮 stop：共两轮 plan_created/plan_finished，两次 reflection
    assert types.count(EVENT_PLAN_CREATED) == 2
    assert types.count(EVENT_PLAN_FINISHED) == 2
    assert types.count(EVENT_REFLECTION) == 2
    assert types[-1] == EVENT_RUN_FINISHED
    assert stream.derive_state().status == "failed"
    assert stream.derive_state().reflections == 2


def test_runner_success_run_event_status_matches(tmp_path):
    class _Plan:
        steps = [1]
        planner = "llm"

    class _Result:
        success = True
        status = "completed"

    class _Planner:
        def create_plan(self, goal, failure_context=None):
            return _Plan()

    class _Executor:
        def execute_plan(self, steps, context, **kwargs):
            return _Result()

    stream = EventStream(FileStorage(tmp_path / "events"), "run-ok")
    runner = PlanRunner(planner=_Planner(), executor=_Executor(), event_stream=stream)

    outcome = runner.run("目标", context=object())

    assert outcome.success is True
    assert stream.derive_state().status == "completed"
    assert stream.events()[-1].type == EVENT_RUN_FINISHED


def test_runner_without_event_stream_unchanged():
    """未接入事件流时行为不变（向后兼容）。"""

    class _Plan:
        steps = [1]
        planner = "rule"

    class _Result:
        success = True
        status = "completed"

    class _Planner:
        def create_plan(self, goal, failure_context=None):
            return _Plan()

    class _Executor:
        def execute_plan(self, steps, context, **kwargs):
            return _Result()

    runner = PlanRunner(planner=_Planner(), executor=_Executor())
    outcome = runner.run("目标", context=object())
    assert outcome.success is True  # 无事件流也不报错


# ---------------------------------------------------------------------------
# Ultra 多路择优
# ---------------------------------------------------------------------------


def test_ultra_selects_highest_scored_candidate():
    def generate(objective, persona, prompt):
        return f"产出[{persona}]"

    def judge(objective, candidates):
        scores = {"rigorous": 0.3, "pragmatic": 0.9, "creative": 0.6}
        return (
            {key: scores[key] for key in candidates},
            {key: f"评估 {key}" for key in candidates},
        )

    result = UltraRunner(generate, judge_fn=judge, judge_name="rubric-v1").run_stage("目标")

    assert result.best_persona == "pragmatic"
    assert result.best_output == "产出[pragmatic]"
    assert result.judge == "rubric-v1"
    assert result.scores["pragmatic"] == 0.9


def test_ultra_failed_lane_isolated():
    def generate(objective, persona, prompt):
        if persona == "creative":
            raise RuntimeError("该路崩溃")
        return f"产出[{persona}]"

    result = UltraRunner(generate).run_stage("目标")

    assert "creative" in result.failures
    assert "RuntimeError" in result.failures["creative"]
    assert "rigorous" in result.outputs  # 其他路不受影响
    assert result.success is True


def test_ultra_all_lanes_failed_raises():
    def generate(objective, persona, prompt):
        raise RuntimeError("全线崩溃")

    with pytest.raises(UltraError, match="全部 3 路候选失败"):
        UltraRunner(generate).run_stage("目标")


def test_ultra_empty_output_counts_as_failure():
    def generate(objective, persona, prompt):
        return "   " if persona == "creative" else f"产出[{persona}]"

    result = UltraRunner(generate).run_stage("目标")
    assert result.failures["creative"] == "空产出"


def test_ultra_default_first_when_no_judge():
    def generate(objective, persona, prompt):
        return f"产出[{persona}]"

    result = UltraRunner(generate).run_stage("目标")

    assert result.judge == "default_first"
    assert result.best_persona == next(iter(ULTRA_PERSONAS))
    assert "非择优" in result.reasons[result.best_persona]


def test_ultra_calibration_wraps_best_output():
    def generate(objective, persona, prompt):
        return f"产出[{persona}]"

    def judge(objective, candidates):
        return {"rigorous": 0.2, "pragmatic": 0.5, "creative": 0.8}, {}

    def calibrate(objective, best_output):
        return f"校准后({best_output})"

    result = UltraRunner(generate, judge_fn=judge, calibrate_fn=calibrate).run_stage("目标")

    assert result.calibrated is True
    assert result.best_output == "校准后(产出[creative])"


def test_ultra_personas_reach_generate_with_prompts():
    seen = []

    def generate(objective, persona, prompt):
        seen.append((persona, prompt))
        return "x"

    UltraRunner(generate).run_stage("目标")
    assert {persona for persona, _ in seen} == set(ULTRA_PERSONAS)
    for persona, prompt in seen:
        assert prompt == ULTRA_PERSONAS[persona]  # 取向提示词原文下发


def test_ultra_parallel_faster_than_serial():
    def generate(objective, persona, prompt):
        time.sleep(0.12)
        return persona

    started = time.perf_counter()
    UltraRunner(generate, max_concurrency=3).run_stage("目标")
    elapsed = time.perf_counter() - started

    assert elapsed < 0.30  # 串行 0.36s，并行 ~0.12s


def test_ultra_custom_personas_dict():
    def generate(objective, persona, prompt):
        return f"{persona}:{prompt[-4:]}"

    result = UltraRunner(generate).run_stage(
        "目标", personas={"alpha": "取向A-tail", "beta": "取向B-tail"}
    )
    assert set(result.outputs) == {"alpha", "beta"}


def test_ultra_result_to_dict_roundtrip_shape():
    def generate(objective, persona, prompt):
        return f"产出[{persona}]"

    data = UltraRunner(generate).run_stage("目标").to_dict()
    assert {"objective", "best_persona", "best_output", "outputs", "failures",
            "scores", "reasons", "judge", "calibrated"} <= set(data)
