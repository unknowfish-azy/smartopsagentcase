"""机器人域子智能体的拆解与执行单测。"""

from agent.orchestrator.direct_executor import DirectExecutor
from agent.orchestrator.dispatcher import decompose_goal
from agent.orchestrator.models import AgentSpecialty


def test_robot_goal_decomposes_into_three_specialties():
    tasks = decompose_goal("巡检 A 区并诊断 robot-car-01，顺便做合规审计")
    specialties = {task.required_specialty for task in tasks}
    assert specialties == {
        AgentSpecialty.PATROL_PLANNER,
        AgentSpecialty.DEVICE_DIAGNOSTICIAN,
        AgentSpecialty.COMPLIANCE_AUDITOR,
    }
    # 巡检与诊断可并行，合规审计必须依赖前两者
    compliance = next(t for t in tasks if t.required_specialty is AgentSpecialty.COMPLIANCE_AUDITOR)
    assert set(compliance.depends_on) == {"t_patrol_planner", "t_device_diagnostician"}


def test_robot_keyword_does_not_fall_into_aiops_chain():
    tasks = decompose_goal("查看设备遥测")
    assert [t.required_specialty for t in tasks] == [AgentSpecialty.DEVICE_DIAGNOSTICIAN]


def test_aiops_goal_still_uses_legacy_chain():
    tasks = decompose_goal("系统异常，帮我定位根因")
    specialties = {task.required_specialty for task in tasks}
    assert AgentSpecialty.ANOMALY_SLEUTH in specialties
    assert AgentSpecialty.ROOTCAUSE_HUNTER in specialties
    assert AgentSpecialty.PATROL_PLANNER not in specialties


def _executor_with_backend(responses: dict[str, object]) -> DirectExecutor:
    executor = object.__new__(DirectExecutor)
    executor._backend_request = lambda method, path, body=None: responses.get(path, [])
    return executor


def test_device_diagnostician_flags_low_battery():
    executor = _executor_with_backend({
        "/api/robot/devices/robot-car-01/live": {
            "mode": "AUTONOMOUS",
            "bridgeConnected": True,
            "telemetry": {"battery": 0.25, "obstacleDistance": 2.4},
        },
        "/api/robot/devices/robot-car-01/tasks": [
            {"status": "RUNNING"},
            {"status": "DONE"},
        ],
    })
    result = executor._run_device_diagnostician(None, {"device_key": "robot-car-01"})
    assert result["findings"]["risk_level"] == "WARN"
    assert result["findings"]["battery_percent"] == 25
    assert result["findings"]["task_status_counts"] == {"RUNNING": 1, "DONE": 1}


def test_device_diagnostician_without_telemetry_is_unknown():
    executor = _executor_with_backend({
        "/api/robot/devices/robot-car-02/live": {"mode": "OFFLINE"},
        "/api/robot/devices/robot-car-02/tasks": [],
    })
    result = executor._run_device_diagnostician(None, {"device_key": "robot-car-02"})
    # OFFLINE 直接高危，且不得编造电量
    assert result["findings"]["risk_level"] == "CRITICAL"
    assert result["findings"]["battery_percent"] is None


def test_compliance_auditor_reports_estop_with_running_task():
    executor = _executor_with_backend({
        "/api/robot/fleet/status": {"running": 1},
        "/api/robot/devices/robot-car-03/live": {"mode": "E_STOP"},
        "/api/robot/devices/robot-car-03/tasks": [{"status": "RUNNING"}],
    })
    result = executor._run_compliance_auditor(None, {"device_keys": ["robot-car-03"]})
    assert result["findings"]["requires_human"] is True
    assert result["findings"]["violations"][0]["rule"] == "estop_or_fault_with_running_task"


def test_backend_401_without_credentials_returns_actionable_error(monkeypatch):
    """未配置令牌/账号时应提示如何配置，而不是裸 401。"""
    import io
    from urllib.error import HTTPError

    from agent.orchestrator import direct_executor

    monkeypatch.delenv("SMARTOPS_AGENT_TOKEN", raising=False)
    monkeypatch.delenv("SMARTOPS_AGENT_USERNAME", raising=False)
    monkeypatch.delenv("SMARTOPS_AGENT_PASSWORD", raising=False)

    def _raise_401(*args, **kwargs):
        raise HTTPError("http://127.0.0.1:8080/x", 401, "unauth", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(direct_executor, "_open_request", _raise_401)
    try:
        direct_executor._backend_call("GET", "/api/robot/fleet/status")
    except RuntimeError as exc:
        assert "SMARTOPS_AGENT_USERNAME" in str(exc)
    else:
        raise AssertionError("期望抛出 RuntimeError")

