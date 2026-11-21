"""
`python -m agent.mcp` —— 启动 SmartOps MCP 服务端（stdio）。

    python -m agent.mcp                          # 默认只读工具集，dry-run
    python -m agent.mcp --list-tools             # 打印将暴露的工具清单后退出
    python -m agent.mcp --allowlist nginx.status,redis.info
    python -m agent.mcp --no-dry-run             # 允许真实执行（谨慎）
    python -m agent.mcp --security               # 挂载安全基线（审计链）

环境变量：
    MCP_TOOL_ALLOWLIST   逗号分隔的工具名（等价 --allowlist）
    MCP_DRY_RUN          1/true 时演练态（默认）；0/false 允许真实执行

纪律：
    * stdout 只写 MCP 消息，日志一律走 stderr（`StdioServerTransport.log`）；
    * 未显式 allowlist 时只暴露 REAL + LOW/MEDIUM + SAFE_RETRY 的只读工具；
    * 调用仍走 AgentExecutor 的安全基线 / 风险 / 审批 / 审计链。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from agent.executor.executor import AgentExecutor
from agent.mcp.catalog import ToolCatalog
from agent.mcp.server import (
    MCPServerOptions,
    SmartOpsMCPServer,
)
from agent.mcp.transport import StdioServerTransport
from agent.policies.policy_engine import PolicyEngine
from agent.registry.tool_registry import ToolRegistry
from agent.tools.registry import ToolRegistry as ExecutorToolRegistry
from agent.plugins.installed.mysql.tools import (
    MySQLReadOnlyQueryTool,
    MySQLStatusTool,
    MySQLVariablesTool,
)
from agent.plugins.installed.nginx.tools import (
    NginxConfigTestTool,
    NginxLogsTool,
    NginxStatusTool,
)
from agent.plugins.installed.redis.tools import (
    RedisInfoTool,
    RedisMemoryTool,
)

logger = logging.getLogger("agent.mcp")


def _default_tools() -> list:
    """内置的只读工具实例集合。

    这里只装配查询类工具；写操作（restart/reload 等）不进入默认集，
    需要时通过 `--allowlist` 显式暴露。
    """

    return [
        NginxStatusTool(),
        NginxConfigTestTool(),
        NginxLogsTool(),
        MySQLStatusTool(),
        MySQLVariablesTool(),
        MySQLReadOnlyQueryTool(),
        RedisInfoTool(),
        RedisMemoryTool(),
    ]


def _parse_allowlist(
    raw: str | None,
) -> list[str] | None:
    if not raw:
        return None

    return [
        item.strip()
        for item in raw.split(",")
        if item.strip()
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agent.mcp",
        description="SmartOps MCP 服务端（stdio）",
    )
    parser.add_argument(
        "--allowlist",
        default=os.environ.get("MCP_TOOL_ALLOWLIST"),
        help="逗号分隔的工具名白名单（默认只暴露只读工具）",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="打印将暴露的工具清单后退出",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=_env_bool(
            "MCP_DRY_RUN",
            True,
        ),
        help="演练态执行（默认开启）",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="允许真实执行（会触发写操作时必须显式指定）",
    )
    parser.add_argument(
        "--security",
        action="store_true",
        help="挂载安全基线（需要可用审计存储，fail-closed）",
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get(
            "MCP_USER_ID",
            "mcp-client",
        ),
        help="调用使用的执行身份（默认 mcp-client）",
    )
    parser.add_argument(
        "--server-name",
        default="smartops-agent",
    )
    parser.add_argument(
        "--version",
        default="0.1.0",
    )
    return parser


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    raw = os.environ.get(name)

    if raw is None:
        return default

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    args = build_parser().parse_args(argv)

    plugin_registry = ToolRegistry()
    executor_registry = ExecutorToolRegistry()

    for tool in _default_tools():
        plugin_registry.register(tool)
        executor_registry.register(tool)

    allowlist = _parse_allowlist(args.allowlist)
    catalog = ToolCatalog.from_registry(
        plugin_registry,
        allowlist=allowlist,
    )

    if args.list_tools:
        for entry in catalog.list_entries():
            print(
                f"{entry.name}\t{entry.risk.value}\t"
                f"{entry.idempotency}\t{entry.description}"
            )
        print(
            f"# 共 {len(catalog)} 个工具（dry_run={args.dry_run}）",
            file=sys.stderr,
        )
        return 0

    options = MCPServerOptions(
        server_name=args.server_name,
        version=args.version,
        dry_run=args.dry_run,
        user_id=args.user_id,
    )

    security_engine = None
    if args.security:
        from agent.security_baseline import (
            build_security_baseline,
        )

        bundle = build_security_baseline()
        security_engine = bundle.engine

    executor = AgentExecutor(
        executor_registry,
        PolicyEngine(),
        security_engine=security_engine,
    )

    server = SmartOpsMCPServer(
        executor,
        catalog,
        options=options,
    )

    transport = StdioServerTransport()

    logger.info(
        "smartops mcp server 启动：tools=%d dry_run=%s security=%s",
        len(catalog),
        args.dry_run,
        "ON" if security_engine else "OFF",
    )

    try:
        asyncio.run(server.serve(transport))
    except KeyboardInterrupt:
        logger.info("收到中断，退出")
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
