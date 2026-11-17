"""L2 运维红线检查器测试。"""

from __future__ import annotations

import pytest

from agent.security_baseline import BaselineLayer, RedlineChecker, load_baseline
from agent.security_baseline.models import GateAction


@pytest.fixture(scope="module")
def checker():
    return RedlineChecker(load_baseline())


@pytest.mark.parametrize(
    "command,rule_id",
    [
        ("rm -rf /", "OL-001"),
        ("rm -rf /var/log", "OL-001"),
        ("rm -rf .", "OL-001"),
        ("rm -rf ..", "OL-001"),
        ("rm --no-preserve-root -rf /", "OL-001"),
        ("mkfs.ext4 /dev/sdb1", "OL-002"),
        ("fdisk /dev/sda", "OL-002"),
        ("shutdown -h now", "OL-003"),
        ("sudo reboot", "OL-003"),
        ("iptables -F", "OL-004"),
        ("systemctl stop firewalld", "OL-004"),
        ("ufw disable", "OL-004"),
        ("DROP TABLE orders", "OL-005"),
        ("truncate table audit_log", "OL-005"),
        ("history -c", "OL-006"),
        ("journalctl --vacuum-time=1s", "OL-006"),
        ("dr switchover --site b", "OL-009"),
        ("rollback --force v1.2.0", "OL-009"),
    ],
)
def test_destructive_commands_are_blocked(checker, command, rule_id):
    decision = checker.check(command=command)
    assert decision is not None
    assert decision.action is GateAction.BLOCK
    assert decision.layer is BaselineLayer.L2_OPERATIONS
    assert decision.reasons[0].startswith(rule_id)


@pytest.mark.parametrize(
    "command",
    [
        "ls -al /var/log",
        "rm -rf ./tmp/cache",
        "systemctl status firewalld",
        "iptables -L -n",
        "SELECT * FROM orders",
        "kubectl logs nginx-7d9f",
    ],
)
def test_normal_commands_pass(checker, command):
    assert checker.check(command=command) is None


def test_operation_level_redlines(checker):
    decision = checker.check(operation="database.drop")
    assert decision is not None and decision.action is GateAction.BLOCK
    assert decision.reasons[0].startswith("OL-011")

    decision = checker.check(operation="server.delete")
    assert decision is not None and decision.reasons[0].startswith("OL-012")


def test_benign_operation_passes(checker):
    assert checker.check(operation="nginx.status") is None
