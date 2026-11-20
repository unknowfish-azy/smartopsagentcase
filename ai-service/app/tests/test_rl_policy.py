"""P2-2 强化学习策略测试。"""

import pytest

from app.services.rl_policy import (
    DiagnosisState,
    QLearningPolicy,
    RLPolicyService,
    compute_reward,
)


def test_diagnosis_state_to_key():
    s = DiagnosisState("cpu", "high", True, "1-2", False)
    key = s.to_key()
    assert "cpu" in key
    assert "high" in key
    assert "rc=1" in key


def test_diagnosis_state_from_steps():
    s0 = DiagnosisState.from_steps("cpu", "high", False, 0, False)
    assert s0.step_bucket == "0"
    s1 = DiagnosisState.from_steps("cpu", "high", False, 2, False)
    assert s1.step_bucket == "1-2"
    s5 = DiagnosisState.from_steps("cpu", "high", False, 5, False)
    assert s5.step_bucket == "3-5"
    s9 = DiagnosisState.from_steps("cpu", "high", False, 9, False)
    assert s9.step_bucket == "6+"


def test_compute_reward_success():
    r = compute_reward("restart_service", "success", 10.0)
    assert r > 0.5  # 1.0 - 0.01


def test_compute_reward_final_bonus():
    r_final = compute_reward("restart_service", "success", 10.0, is_final_action=True)
    r_normal = compute_reward("restart_service", "success", 10.0)
    assert r_final > r_normal + 1.5  # 终止奖励 +2.0


def test_compute_reward_side_effect():
    r = compute_reward("restart_service", "side_effect", 5.0)
    assert r < -1.5  # -2.0 强惩罚


def test_compute_reward_time_penalty():
    r_fast = compute_reward("query_logs", "success", 1.0)
    r_slow = compute_reward("query_logs", "success", 100.0)
    assert r_fast > r_slow


def test_q_learning_update():
    policy = QLearningPolicy(learning_rate=0.5)
    state = DiagnosisState("cpu", "high", False, "0", False)
    new_q = policy.update(state, "query_logs", 1.0, None)
    # 初始 Q=0，α=0.5，r=1.0 → Q = 0 + 0.5 * (1.0 - 0) = 0.5
    assert new_q == pytest.approx(0.5)


def test_q_learning_multiple_updates():
    policy = QLearningPolicy(learning_rate=0.5)
    state = DiagnosisState("cpu", "high", False, "0", False)
    policy.update(state, "query_logs", 1.0, None)
    new_q = policy.update(state, "query_logs", 1.0, None)
    # 第二次：Q = 0.5 + 0.5 * (1.0 - 0.5) = 0.75
    assert new_q == pytest.approx(0.75)


def test_select_action_no_history():
    policy = QLearningPolicy()
    state = DiagnosisState("cpu", "high", False, "0", False)
    action, reason = policy.select_action(state, explore=False)
    assert action in ["query_logs", "query_metrics", "retrieve_similar_cases"]


def test_select_action_exploit():
    policy = QLearningPolicy()
    state = DiagnosisState("cpu", "high", False, "0", False)
    # 训练：query_logs 成功
    for _ in range(5):
        policy.update(state, "query_logs", 1.0, None)
    action, reason = policy.select_action(state, explore=False)
    assert action == "query_logs"


def test_rl_service_recommend():
    service = RLPolicyService()
    result = service.recommend("cpu", "high", False, 0, False)
    assert "recommended_action" in result
    assert "q_values" in result


def test_rl_service_record_step():
    service = RLPolicyService()
    result = service.record_step(
        "ep1", "cpu", "high", False, 0, False,
        "query_logs", "success", 5.0, is_final=False,
    )
    assert result["reward"] > 0
    assert "new_q_value" in result


def test_rl_service_stats():
    service = RLPolicyService()
    service.record_step("ep1", "cpu", "high", False, 0, False, "query_logs", "success", 5.0)
    stats = service.get_stats()
    assert stats["total_episodes"] == 1
    assert stats["total_steps"] == 1


def test_q_table_export_import():
    policy = QLearningPolicy()
    state = DiagnosisState("cpu", "high", False, "0", False)
    policy.update(state, "query_logs", 1.0, None)

    exported = policy.export_q_table()
    assert len(exported) > 0

    new_policy = QLearningPolicy()
    new_policy.import_q_table(exported)
    assert new_policy._get_entry(state.to_key(), "query_logs").q_value == pytest.approx(0.1)
