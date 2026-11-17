"""L0 合规红线测试——法律硬边界，命中即 BLOCK 且不可审批豁免。"""

from __future__ import annotations

import pytest

from agent.security_baseline import BaselineLayer, ComplianceGuard, load_baseline
from agent.security_baseline.models import GateAction


@pytest.fixture(scope="module")
def guard():
    return ComplianceGuard(load_baseline())


@pytest.mark.parametrize(
    "command,rule_id",
    [
        ("nmap -sV 10.0.0.1", "CL-001"),
        ("masscan 0.0.0.0/0 -p1-65535", "CL-001"),
        ("gobuster dir -u http://target", "CL-001"),
        ("ghidra ./target.bin", "CL-002"),
        ("frida -U -f com.vendor.app", "CL-002"),
        ("upx -d packed.exe", "CL-002"),
        ("hydra -l root -P pass.txt ssh://10.0.0.5", "CL-003"),
        ("hashcat -m 0 hash.txt rockyou.txt", "CL-003"),
        ("ettercap -Tq -i eth0", "CL-004"),
        ("responder -I eth0", "CL-004"),
        ("ngrok http 8080", "CL-005"),
        ("frpc -c frpc.toml", "CL-005"),
        ("msfvenom -p windows/meterpreter/reverse_tcp", "CL-006"),
        ("mimikatz # sekurlsa::logonpasswords", "CL-006"),
        ("python crawl.py --proxy_pool 200", "CL-007"),
        ("node solve.js --captcha-solver 2captcha", "CL-007"),
    ],
)
def test_illegal_tools_are_blocked(guard, command, rule_id):
    decision = guard.check(command=command)
    assert decision is not None
    assert decision.action is GateAction.BLOCK
    assert decision.layer is BaselineLayer.L0_COMPLIANCE
    assert decision.reasons[0].startswith(rule_id)
    # 法律依据必须随决策留痕
    assert "网络安全法" in decision.reasons[0] or "刑法" in decision.reasons[0] or "著作权法" in decision.reasons[0]


@pytest.mark.parametrize(
    "command",
    [
        "kubectl logs nginx-7d9f --tail=100",
        "redis-cli info memory",
        "docker ps -a",
        "curl https://example.com/api/health",
        "tcpdump -i lo port 8001 -c 5",
    ],
)
def test_legitimate_ops_commands_pass(guard, command):
    assert guard.check(command=command) is None


def test_compliance_rules_are_not_exemptible(guard):
    assert guard.approval_exemptible is False


def test_word_boundary_avoids_false_positive(guard):
    # 工具名作为其他单词的子串时不得误杀
    assert guard.check(command="echo mapping_nmap_results done") is None
