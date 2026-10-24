from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest

from agent.tools.shell import ShellTool
from agent.tools.builtin.shell import ShellCommandDenied
from agent.tools.builtin.shell import ShellTool as BuiltinShellTool


def test_allowed_command_uses_argv_and_shell_false(monkeypatch):
    run = Mock(
        return_value=subprocess.CompletedProcess(
            ["whoami"], 0, "smartops\n", ""
        )
    )
    monkeypatch.setattr(subprocess, "run", run)

    result = ShellTool().execute("whoami")

    assert result["success"] is True
    assert result["command"] == ["whoami"]
    assert result["stdout"] == "smartops\n"
    assert run.call_args.args[0] == ["whoami"]
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "unknown-command",
        "whoami | hostname",
        "whoami > output.txt",
        "whoami && hostname",
        "whoami || hostname",
        "whoami; hostname",
        "whoami $(hostname)",
        "whoami `hostname`",
        "whoami\nhostname",
    ],
)
def test_rejects_disallowed_or_injected_commands(command):
    with pytest.raises(PermissionError):
        ShellTool().execute(command)


def test_timeout_is_reported_without_retry(monkeypatch):
    run = Mock(side_effect=subprocess.TimeoutExpired("whoami", 1))
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(TimeoutError, match="命令执行超时"):
        ShellTool(timeout=1).execute("whoami")

    assert run.call_count == 1


def test_large_output_is_truncated(monkeypatch):
    run = Mock(
        return_value=subprocess.CompletedProcess(
            ["hostname"], 0, "abcdefgh", "12345678"
        )
    )
    monkeypatch.setattr(subprocess, "run", run)

    result = ShellTool(max_output_chars=4).execute("hostname")

    assert result["truncated"] is True
    assert result["stdout"].startswith("abcd")
    assert result["stderr"].startswith("1234")


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["cmd", "powershell"])
async def test_builtin_shell_rejects_command_interpreters(command):
    with pytest.raises(ShellCommandDenied):
        await BuiltinShellTool().execute([command, "--version"])
