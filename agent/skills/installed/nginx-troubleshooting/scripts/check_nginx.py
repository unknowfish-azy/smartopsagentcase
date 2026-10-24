"""
SmartOps Nginx Read-only Diagnostic Script.

用途：
    为 nginx-troubleshooting Skill 提供基础的 Nginx 环境取证能力。

设计原则：
    1. 只读
    2. 不使用 shell=True
    3. 不执行 restart / reload / stop / kill
    4. 所有外部命令都有超时
    5. 支持 JSON 输出，便于 Agent / Tool / Audit 使用
    6. 单个检查失败不能导致整个诊断流程崩溃
    7. 不把脚本本身作为 Permission / Risk / Approval 的替代物

典型调用链：

    User
      ↓
    Planner
      ↓
    nginx-troubleshooting Skill
      ↓
    nginx.status / nginx.config_test / nginx.logs
      ↓
    Evidence
      ↓
    Reasoning
      ↓
    SafeAgent
      ↓
    Verification
      ↓
    Audit
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


# ============================================================
# Constants
# ============================================================

DEFAULT_TIMEOUT = 10

MAX_OUTPUT_CHARS = 20_000

NGINX_CONFIG_TEST_COMMAND = "-t"

LINUX_SYSTEMCTL = "systemctl"
LINUX_SS = "ss"
LINUX_NETSTAT = "netstat"
LINUX_PGREP = "pgrep"

WINDOWS_NGINX_SERVICE = "nginx"

READ_ONLY = True


# ============================================================
# Data Models
# ============================================================


@dataclass(slots=True)
class CommandResult:
    """
    外部命令执行结果。
    """

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    command_not_found: bool = False

    @property
    def success(self) -> bool:
        """
        判断命令是否成功。
        """
        return (
            self.returncode == 0
            and not self.timed_out
            and not self.command_not_found
        )

    @property
    def output(self) -> str:
        """
        返回优先级更高的输出。
        """
        if self.stdout.strip():
            return self.stdout

        return self.stderr

    def to_dict(self) -> dict[str, Any]:
        """
        转换为 JSON 可序列化字典。
        """
        return asdict(self)


@dataclass(slots=True)
class DiagnosticResult:
    """
    Nginx 完整诊断结果。
    """

    nginx_installed: bool
    nginx_binary: str | None

    nginx_version: CommandResult | None
    config_test: CommandResult | None

    service_status: CommandResult | None
    process_status: CommandResult | None
    listening_ports: CommandResult | None

    environment: dict[str, Any]

    generated_at: float

    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典。
        """
        return asdict(self)


# ============================================================
# Utility Functions
# ============================================================


def truncate_output(
    value: str,
    max_chars: int = MAX_OUTPUT_CHARS,
) -> str:
    """
    限制输出长度。

    防止：
        - 日志过大
        - 命令输出过大
        - Agent 上下文膨胀

    不修改原始服务器状态。
    """
    if len(value) <= max_chars:
        return value

    return (
        value[:max_chars]
        + "\n\n"
        "[SmartOps] Output truncated."
    )


def find_binary(
    name: str,
) -> str | None:
    """
    在 PATH 中寻找命令。
    """
    return shutil.which(name)


def safe_text(
    value: Any,
) -> str:
    """
    将输出转换为安全字符串。
    """
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    return str(value)


# ============================================================
# Command Execution
# ============================================================


def run_command(
    command: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> CommandResult:
    """
    安全执行外部命令。

    安全原则：

    - 参数列表执行
    - shell=False
    - 有超时
    - 捕获 stdout / stderr
    - 限制输出
    - 不允许命令字符串拼接
    """
    command_list = [
        str(item)
        for item in command
    ]

    if not command_list:
        raise ValueError(
            "command 不能为空"
        )

    if timeout <= 0:
        raise ValueError(
            "timeout 必须大于 0"
        )

    start = time.monotonic()

    try:
        completed = subprocess.run(
            command_list,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )

        duration_ms = int(
            (time.monotonic() - start) * 1000
        )

        stdout = truncate_output(
            safe_text(completed.stdout)
        )

        stderr = truncate_output(
            safe_text(completed.stderr)
        )

        return CommandResult(
            command=command_list,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired as exc:
        duration_ms = int(
            (time.monotonic() - start) * 1000
        )

        stdout = truncate_output(
            safe_text(exc.stdout)
        )

        stderr = truncate_output(
            safe_text(exc.stderr)
        )

        return CommandResult(
            command=command_list,
            returncode=124,
            stdout=stdout,
            stderr=(
                stderr
                or "command timeout"
            ),
            duration_ms=duration_ms,
            timed_out=True,
        )

    except FileNotFoundError as exc:
        duration_ms = int(
            (time.monotonic() - start) * 1000
        )

        return CommandResult(
            command=command_list,
            returncode=127,
            stdout="",
            stderr=str(exc),
            duration_ms=duration_ms,
            command_not_found=True,
        )

    except OSError as exc:
        duration_ms = int(
            (time.monotonic() - start) * 1000
        )

        return CommandResult(
            command=command_list,
            returncode=1,
            stdout="",
            stderr=str(exc),
            duration_ms=duration_ms,
        )


# ============================================================
# Nginx Checks
# ============================================================


def find_nginx() -> str | None:
    """
    查找 nginx 可执行文件。
    """
    candidates = [
        "nginx",
        "nginx.exe",
    ]

    for candidate in candidates:
        binary = find_binary(candidate)

        if binary:
            return binary

    return None


def check_nginx_version(
    nginx_binary: str,
    timeout: int,
) -> CommandResult:
    """
    获取 Nginx 版本。
    """
    return run_command(
        [
            nginx_binary,
            "-v",
        ],
        timeout=timeout,
    )


def check_nginx_config(
    nginx_binary: str,
    timeout: int,
) -> CommandResult:
    """
    执行 nginx -t。

    此操作用于检查配置，
    不执行 reload / restart。
    """
    return run_command(
        [
            nginx_binary,
            NGINX_CONFIG_TEST_COMMAND,
        ],
        timeout=timeout,
    )


def check_service_status(
    timeout: int,
) -> CommandResult | None:
    """
    检查 Linux systemd 中的 nginx 服务。

    如果当前系统没有 systemctl，则返回 None。
    """
    systemctl = find_binary(
        LINUX_SYSTEMCTL
    )

    if systemctl is None:
        return None

    return run_command(
        [
            systemctl,
            "status",
            WINDOWS_NGINX_SERVICE,
            "--no-pager",
            "--plain",
        ],
        timeout=timeout,
    )


def check_process_status(
    timeout: int,
) -> CommandResult | None:
    """
    检查 nginx 进程。

    优先 pgrep。
    """
    pgrep = find_binary(
        LINUX_PGREP
    )

    if pgrep is not None:
        return run_command(
            [
                pgrep,
                "-a",
                "nginx",
            ],
            timeout=timeout,
        )

    # Windows 环境可以尝试 tasklist。
    tasklist = find_binary(
        "tasklist"
    )

    if tasklist is not None:
        return run_command(
            [
                tasklist,
                "/FI",
                "IMAGENAME eq nginx.exe",
            ],
            timeout=timeout,
        )

    return None


def check_listening_ports(
    timeout: int,
) -> CommandResult | None:
    """
    获取监听端口。

    优先：
        ss

    其次：
        netstat
    """
    ss = find_binary(
        LINUX_SS
    )

    if ss is not None:
        return run_command(
            [
                ss,
                "-lntp",
            ],
            timeout=timeout,
        )

    netstat = find_binary(
        LINUX_NETSTAT
    )

    if netstat is not None:
        return run_command(
            [
                netstat,
                "-lntp",
            ],
            timeout=timeout,
        )

    # Windows netstat
    windows_netstat = find_binary(
        "netstat.exe"
    )

    if windows_netstat is not None:
        return run_command(
            [
                windows_netstat,
                "-ano",
            ],
            timeout=timeout,
        )

    return None


# ============================================================
# Environment Detection
# ============================================================


def detect_environment() -> dict[str, Any]:
    """
    检测当前运行环境。

    用于：

    - Linux / Windows 判断
    - systemd 判断
    - Docker 判断
    - Kubernetes 基础环境判断

    不执行修改操作。
    """
    platform_name = sys.platform

    is_linux = platform_name.startswith(
        "linux"
    )

    is_windows = platform_name.startswith(
        "win"
    )

    is_docker = Path(
        "/.dockerenv"
    ).exists()

    cgroup_path = Path(
        "/proc/1/cgroup"
    )

    cgroup_content = ""

    if cgroup_path.exists():
        try:
            cgroup_content = cgroup_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            cgroup_content = ""

    cgroup_lower = cgroup_content.lower()

    docker_in_cgroup = (
        "docker" in cgroup_lower
        or "containerd" in cgroup_lower
    )

    kubernetes = bool(
        (
            Path(
                "/var/run/secrets/kubernetes.io/serviceaccount"
            ).exists()
        )
        or (
            "kubepods" in cgroup_lower
        )
    )

    systemctl_available = (
        find_binary("systemctl")
        is not None
    )

    return {
        "platform": platform_name,
        "linux": is_linux,
        "windows": is_windows,
        "docker": (
            is_docker
            or docker_in_cgroup
        ),
        "kubernetes": kubernetes,
        "systemctl_available": systemctl_available,
        "read_only": READ_ONLY,
    }


# ============================================================
# Diagnostic Builder
# ============================================================


def build_diagnostic(
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> DiagnosticResult:
    """
    执行完整 Nginx 诊断。

    单个检查失败不会导致整个诊断直接退出。
    """
    environment = detect_environment()

    nginx_binary = find_nginx()

    if nginx_binary is None:
        return DiagnosticResult(
            nginx_installed=False,
            nginx_binary=None,
            nginx_version=None,
            config_test=None,
            service_status=check_service_status(
                timeout
            ),
            process_status=check_process_status(
                timeout
            ),
            listening_ports=check_listening_ports(
                timeout
            ),
            environment=environment,
            generated_at=time.time(),
        )

    return DiagnosticResult(
        nginx_installed=True,
        nginx_binary=nginx_binary,
        nginx_version=check_nginx_version(
            nginx_binary,
            timeout,
        ),
        config_test=check_nginx_config(
            nginx_binary,
            timeout,
        ),
        service_status=check_service_status(
            timeout
        ),
        process_status=check_process_status(
            timeout
        ),
        listening_ports=check_listening_ports(
            timeout
        ),
        environment=environment,
        generated_at=time.time(),
    )


# ============================================================
# Evidence Summary
# ============================================================


def determine_config_status(
    result: CommandResult | None,
) -> str:
    """
    判断 nginx -t 状态。
    """
    if result is None:
        return "UNKNOWN"

    if result.timed_out:
        return "TIMEOUT"

    if result.command_not_found:
        return "NOT_FOUND"

    if result.returncode == 0:
        return "PASS"

    return "FAIL"


def determine_process_status(
    result: CommandResult | None,
) -> str:
    """
    判断进程状态。
    """
    if result is None:
        return "UNKNOWN"

    if result.command_not_found:
        return "UNKNOWN"

    if result.timed_out:
        return "TIMEOUT"

    if result.returncode == 0:
        return "RUNNING"

    return "NOT_RUNNING"


def build_evidence_summary(
    result: DiagnosticResult,
) -> dict[str, Any]:
    """
    根据诊断结果生成初步证据摘要。

    注意：

    这里是证据摘要，
    不是最终 Root Cause。
    """
    config_status = determine_config_status(
        result.config_test
    )

    process_status = determine_process_status(
        result.process_status
    )

    if result.nginx_installed:
        nginx_status = "INSTALLED"
    else:
        nginx_status = "NOT_FOUND"

    return {
        "nginx": nginx_status,
        "process": process_status,
        "config_test": config_status,
        "service_check": (
            "AVAILABLE"
            if result.service_status is not None
            else "UNAVAILABLE"
        ),
        "port_check": (
            "AVAILABLE"
            if result.listening_ports is not None
            else "UNAVAILABLE"
        ),
        "read_only": result.read_only,
    }


# ============================================================
# Human Output
# ============================================================


def print_section(
    title: str,
) -> None:
    """
    打印报告章节。
    """
    print()
    print(f"[{title}]")
    print("-" * 60)


def print_human_readable(
    result: DiagnosticResult,
) -> None:
    """
    输出人类可读报告。
    """
    print("=" * 70)
    print("SmartOps Nginx Diagnostic")
    print("=" * 70)

    print_section("Environment")

    for key, value in result.environment.items():
        print(
            f"{key}: {value}"
        )

    print_section("Nginx")

    print(
        "installed: "
        f"{result.nginx_installed}"
    )

    print(
        "binary: "
        f"{result.nginx_binary}"
    )

    if result.nginx_version is not None:
        print_section(
            "Nginx Version"
        )

        print(
            result.nginx_version.output
            or "<no output>"
        )

        print(
            f"success: "
            f"{result.nginx_version.success}"
        )

    if result.config_test is not None:
        print_section(
            "Configuration Test"
        )

        print(
            result.config_test.output
            or "<no output>"
        )

        print(
            "status: "
            f"{determine_config_status(result.config_test)}"
        )

    if result.service_status is not None:
        print_section(
            "Service Status"
        )

        output = (
            result.service_status.stdout
            or result.service_status.stderr
            or "<no output>"
        )

        print(output)

    if result.process_status is not None:
        print_section(
            "Process Status"
        )

        output = (
            result.process_status.stdout
            or result.process_status.stderr
            or "<no output>"
        )

        print(output)

        print(
            "status: "
            f"{determine_process_status(result.process_status)}"
        )

    if result.listening_ports is not None:
        print_section(
            "Listening Ports"
        )

        output = (
            result.listening_ports.stdout
            or result.listening_ports.stderr
            or "<no output>"
        )

        print(output)

    print_section(
        "Evidence Summary"
    )

    evidence = build_evidence_summary(
        result
    )

    for key, value in evidence.items():
        print(
            f"{key}: {value}"
        )

    print_section(
        "Safety"
    )

    print(
        "read_only: "
        f"{result.read_only}"
    )

    print()
    print("=" * 70)


# ============================================================
# JSON Output
# ============================================================


def print_json(
    result: DiagnosticResult,
) -> None:
    """
    输出 JSON。

    JSON 形式便于：

    - Tool
    - Agent
    - Evidence Engine
    - Audit
    - 测试
    """
    payload = result.to_dict()

    payload["evidence_summary"] = (
        build_evidence_summary(
            result
        )
    )

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


# ============================================================
# CLI
# ============================================================


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    """
    解析命令参数。
    """
    parser = argparse.ArgumentParser(
        description=(
            "SmartOps read-only "
            "Nginx diagnostic tool"
        )
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=(
            "单个命令最大执行时间，"
            "单位为秒，默认 10"
        ),
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON",
    )

    return parser.parse_args(
        argv
    )


# ============================================================
# Exit Code
# ============================================================


def determine_exit_code(
    result: DiagnosticResult,
) -> int:
    """
    根据诊断结果返回程序退出码。

    约定：

        0 = Nginx 已发现，诊断脚本正常完成
        1 = Nginx 未发现
        2 = 参数错误
        3 = 诊断存在严重执行错误

    注意：

    退出码不是 Root Cause。
    """
    if not result.nginx_installed:
        return 1

    checks = [
        result.nginx_version,
        result.config_test,
        result.service_status,
        result.process_status,
        result.listening_ports,
    ]

    fatal_execution_error = False

    for check in checks:
        if check is None:
            continue

        if check.command_not_found:
            continue

        if check.timed_out:
            continue

        # returncode 非 0 不一定是脚本错误。
        # 例如 pgrep 查不到 nginx 时本身就会返回非 0。
        #
        # 因此这里只在无法合理解释的情况下保留诊断完成状态。
        if check.returncode < 0:
            fatal_execution_error = True

    if fatal_execution_error:
        return 3

    return 0


# ============================================================
# Main
# ============================================================


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """
    程序入口。
    """
    args = parse_args(
        argv
    )

    if args.timeout <= 0:
        print(
            "错误：--timeout 必须大于 0",
            file=sys.stderr,
        )
        return 2

    try:
        result = build_diagnostic(
            timeout=args.timeout
        )

    except KeyboardInterrupt:
        print(
            "\nSmartOps Nginx Diagnostic interrupted.",
            file=sys.stderr,
        )
        return 130

    except Exception as exc:
        print(
            (
                "SmartOps diagnostic "
                f"failed: {exc}"
            ),
            file=sys.stderr,
        )
        return 3

    if args.json:
        print_json(result)
    else:
        print_human_readable(result)

    return determine_exit_code(
        result
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )