"""安全基线生产装配工厂（组合根）。

把"轮转哈希链审计接收器 + 安全基线引擎 + 机器人守卫"装配成一个可直接
注入执行链的组合包，未来应用层组合根只需一行调用：

    bundle = build_security_baseline()
    executor = AgentExecutor(registry, policy, security_engine=bundle.engine)
    robot_plugin = RobotPlugin(guard=bundle.robot_guard)

设计约束：
* 纯增量模块，只依赖 security_baseline 包内部件，不导入也不修改任何
  既有运行时/执行器/插件代码，依赖方向始终保持单向；
* 审计接收器在构造期即执行哈希链恢复校验，历史被篡改/清单失锚时直接
  抛 ValueError，绝不在无审计锚点的情况下静默启动（fail-closed 引导）；
* 默认落盘 data/security_audit/baseline.jsonl（仓库根 /data/ 已在
  .gitignore 中忽略），路径与轮转参数均可显式覆盖，测试须传 tmp_path；
* 不读取任何环境变量、不接触 .env，部署差异全部通过显式参数表达。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit_rotation import RotatingJsonlAuditSink
from .engine import SecurityBaselineEngine
from .robot_guard import RobotActionGuard

# 默认为相对仓库运行目录的路径；/data/ 整体被 .gitignore 忽略，审计文件不入库。
DEFAULT_AUDIT_DIR = Path("data/security_audit")
DEFAULT_AUDIT_FILE_NAME = "baseline.jsonl"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class SecurityBaselineBundle:
    """一次装配产出的完整基线组合，部件之间的接线在工厂内闭合。"""

    engine: SecurityBaselineEngine
    audit_sink: RotatingJsonlAuditSink
    robot_guard: RobotActionGuard | None
    audit_path: Path

    def verify_audit_chain(self) -> dict[str, Any]:
        """运行期巡检委托：清单哈希 + 全分段/活动段跨链锚点 + seq 连续性。"""
        return self.audit_sink.verify_all()


def _validate_audit_file_name(name: str) -> None:
    """审计文件名只允许裸文件名，封堵路径穿越与清单/分段命名冲突。"""
    if not name or name in {".", ".."}:
        raise ValueError("audit_file_name 不能为空或目录占位符")
    if Path(name).name != name:
        raise ValueError(f"audit_file_name 必须是裸文件名，不允许路径分隔符: {name}")
    if not name.endswith(".jsonl"):
        raise ValueError(f"audit_file_name 必须以 .jsonl 结尾: {name}")
    if ".manifest." in name:
        raise ValueError(f"audit_file_name 不得占用清单命名空间: {name}")


def build_security_baseline(
    *,
    audit_dir: str | Path = DEFAULT_AUDIT_DIR,
    audit_file_name: str = DEFAULT_AUDIT_FILE_NAME,
    config_path: str | Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_segments: int | None = None,
    with_robot_guard: bool = True,
    clock=None,
) -> SecurityBaselineBundle:
    """装配生产可用的安全基线组合包。

    参数：
        audit_dir: 审计目录，不存在时由接收器自动创建。
        audit_file_name: 活动审计文件名，仅允许裸 .jsonl 文件名。
        config_path: 可选外部基线 YAML；None 时加载包内 baseline.yaml，
            其失效再回退内置 DEFAULT_BASELINE。
        max_bytes: 单个审计文件的轮转阈值（字节）。
        max_segments: 保留分段上限，None 表示永久保留、绝不静默删除。
        with_robot_guard: 是否同时装配机器人物理动作守卫。
        clock: 可选时钟注入，主要供固定时钟测试使用。

    抛出：
        ValueError: 文件名非法、轮转参数非法，或既有审计历史哈希链/清单
            校验失败——后者意味着审计存储可能被篡改，引导必须 fail-closed。
    """
    _validate_audit_file_name(audit_file_name)
    audit_path = Path(audit_dir) / audit_file_name

    # 先建 sink：构造期恢复校验不过则直接中断引导，禁止"无审计裸奔"。
    audit_sink = RotatingJsonlAuditSink(
        audit_path,
        max_bytes=max_bytes,
        max_segments=max_segments,
    )
    engine = SecurityBaselineEngine(
        str(config_path) if config_path is not None else None,
        audit_sink=audit_sink,
        clock=clock,
    )
    robot_guard = RobotActionGuard(engine) if with_robot_guard else None

    return SecurityBaselineBundle(
        engine=engine,
        audit_sink=audit_sink,
        robot_guard=robot_guard,
        audit_path=audit_path,
    )


__all__ = [
    "SecurityBaselineBundle",
    "build_security_baseline",
    "DEFAULT_AUDIT_DIR",
    "DEFAULT_AUDIT_FILE_NAME",
    "DEFAULT_MAX_BYTES",
]
