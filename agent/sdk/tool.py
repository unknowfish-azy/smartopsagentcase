from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.policies.risk import RiskLevel


class ImplementationStatus(str, Enum):
    """工具实现状态。

    与 Java 侧 `OperationToolService.ImplementationStatus` 对齐：
    只有 REAL 才可以真正执行；TEMPLATE / UNAVAILABLE 必须在目录里如实标注，
    避免"注册了但跑不通"被当成"执行失败"。
    """

    REAL = "REAL"
    TEMPLATE = "TEMPLATE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class ToolDefinition:
    """工具能力声明。

    字段与后端工具能力目录一一对应：Python 侧与 Java 侧看到的是同一组语义，
    包括实现状态、目标类型、输入输出 Schema、风险、所需权限、
    总超时、输出预算、幂等语义与核验方式。
    """

    name: str
    description: str
    risk: RiskLevel = RiskLevel.LOW

    version: str = "1"
    implementation_status: ImplementationStatus = ImplementationStatus.REAL
    target_type: str = "REMOTE_HOST"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_scope: str | None = None
    # 单次执行总预算（毫秒），不是单条命令超时
    deadline_ms: int = 30_000
    # 输出预算（字节），超出需截断并标记
    output_limit_bytes: int = 512 * 1024
    # SAFE_RETRY（只读，可安全重试）/ AT_MOST_ONCE（写操作，最多一次）
    idempotency: str = "SAFE_RETRY"
    verification: str = ""


class PluginTool(ABC):
    """插件工具基类。

    执行契约固定为 `async execute(arguments, context)`；
    Executor 通过适配层兼容旧式 `execute(**kwargs)` 工具，
    因此两种写法不会再出现"注册成功但永远调不动"的分叉。
    """

    definition: ToolDefinition

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def risk_level(self) -> RiskLevel:
        return self.definition.risk

    @property
    def requires_approval(self) -> bool:
        return self.definition.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> Any:
        raise NotImplementedError
