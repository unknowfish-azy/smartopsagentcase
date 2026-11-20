"""Agent 生产入口：python -m agent [--audit-dir PATH] [--no-security] [--dag]

演示如何一行取用 build_agent_assembly() 组合根；同时作为首个真实调用点，
确保生产装配工厂可以被独立运行并产出 AgentAssembly。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent.assembly import build_agent_assembly


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent",
        description="智维Agent 生产执行链入口（组合根装配）",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=Path("data/security_audit"),
        help="审计落盘目录（仅基线开启时使用），默认 data/security_audit",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help="可选外部基线 YAML 路径，默认用包内 baseline.yaml",
    )
    parser.add_argument(
        "--dag",
        action="store_true",
        help="使用 DagExecutor（Kahn 分波调度），否则用线性 AgentExecutor",
    )
    parser.add_argument(
        "--no-security",
        action="store_true",
        help="显式关闭安全基线（逃生口）。关闭后 security_engine=None、"
             "robot 守卫=None，行为逐字节回到历史版本",
    )
    parser.add_argument(
        "--no-robot-guard",
        action="store_true",
        help="仅给 RobotPlugin 不注入守卫，引擎仍然开启（细粒度控制）",
    )

    args = parser.parse_args(argv)

    try:
        assembly = build_agent_assembly(
            audit_dir=args.audit_dir,
            config_path=args.config_path,
            dag=args.dag,
            security_enabled=not args.no_security,
            with_robot_guard=not args.no_robot_guard,
        )
    except ValueError as exc:
        # 哈希链恢复失败等 fail-closed 场景：原样透传，绝不吞没
        print(f"[agent] 装配失败（fail-closed）：{exc}", file=sys.stderr)
        return 2

    # 装配摘要：一行呈现所有关键接线状态
    engine = assembly.executor.security_engine
    bundle = assembly.baseline
    robot_voice = next(
        (t for t in assembly.robot_plugin.tools if t.__class__.__name__ == "RobotVoiceCommandTool"),
        None,
    )
    print(
        f"[agent] 装配成功\n"
        f"  executor      : {type(assembly.executor).__name__}\n"
        f"  policy_engine : {type(assembly.policy_engine).__name__}\n"
        f"  security      : {'ON' if engine else 'OFF'}"
        + (f"  (engine={type(engine).__name__})" if engine else "")
        + "\n"
        + (
            f"  robot_guard   : ON  (guard={type(bundle.robot_guard).__name__})\n"
            if bundle and bundle.robot_guard
            else f"  robot_guard   : OFF\n"
        )
        + (
            f"  audit_chain   : ok={report['ok']}  total_events={report['total_events']}\n"
            if (report := assembly.verify_audit_chain())
            else f"  audit_chain   : N/A (security disabled)\n"
        )
        + (
            f"  audit_path    : {bundle.audit_path}\n"
            if bundle
            else ""
        )
        + (
            f"  voice_tool.guard: {'ON' if robot_voice and robot_voice.guard else 'OFF'}\n"
            if robot_voice
            else ""
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
