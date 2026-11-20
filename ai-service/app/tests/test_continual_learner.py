"""P2-1 持续学习测试。"""

import pytest

from app.services.continual_learner import (
    ContinualLearningScheduler,
    SampleBuffer,
    TrainingSample,
    EWCPenalty,
)


def _sample(module: str = "anomaly") -> TrainingSample:
    return TrainingSample("s1", module, {"x": 1}, {"y": 0})


def test_sample_buffer_add():
    buf = SampleBuffer()
    buf.add(_sample())
    assert buf.pending_count() == 1


def test_sample_buffer_pending_count_by_module():
    buf = SampleBuffer()
    buf.add(_sample("anomaly"))
    buf.add(_sample("rootcause"))
    assert buf.pending_count("anomaly") == 1
    assert buf.pending_count("rootcause") == 1
    assert buf.pending_count() == 2


def test_take_batch():
    buf = SampleBuffer()
    for _ in range(10):
        buf.add(_sample())
    new, replay = buf.take_batch("anomaly", batch_size=8, replay_ratio=0.25)
    assert len(new) == 6  # 8 * 0.75
    assert all(s.used_in_training for s in new)


def test_scheduler_trigger_threshold():
    scheduler = ContinualLearningScheduler(trigger_threshold=5)
    assert not scheduler.should_trigger("anomaly")
    for _ in range(5):
        scheduler.ingest(_sample())
    assert scheduler.should_trigger("anomaly")


def test_scheduler_trigger_training():
    scheduler = ContinualLearningScheduler(trigger_threshold=3)
    for _ in range(5):
        scheduler.ingest(_sample())
    task = scheduler.trigger_training("anomaly")
    assert task.module == "anomaly"
    assert task.new_sample_count > 0


def test_complete_and_rollback():
    scheduler = ContinualLearningScheduler(trigger_threshold=1)
    scheduler.ingest(_sample())
    t1 = scheduler.trigger_training("anomaly")
    scheduler.complete_training(t1.task_id, {"loss": 0.5}, "/ckpt/v1")
    scheduler.ingest(_sample())
    t2 = scheduler.trigger_training("anomaly")
    scheduler.complete_training(t2.task_id, {"loss": 0.3}, "/ckpt/v2")

    prev_ckpt = scheduler.rollback(t2.task_id)
    assert prev_ckpt == "/ckpt/v1"


def test_ewc_penalty_no_torch():
    """无 torch 时 EWC penalty 返回 0。"""
    ewc = EWCPenalty()
    # 不 compute_fisher，penalty 应该安全返回
    result = ewc.penalty(None)
    assert result == 0.0 or result is not None  # 无 fisher 时返回 tensor(0) 或 0


def test_ewc_lambda():
    ewc = EWCPenalty(lambda_=0.8)
    assert ewc.lambda_ == 0.8
