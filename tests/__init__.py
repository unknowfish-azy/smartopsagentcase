"""
SmartOpsAgent Test Suite.

测试目录统一入口。

测试分层：

    tests/api
        API 接口测试

    tests/agent
        Agent / Harness 测试

    tests/e2e
        端到端业务流程测试

    tests/integration
        Spring Boot / MySQL / Redis
        等基础设施集成测试

测试原则：

    Unit
        单元能力验证

    API
        HTTP 接口验证

    Integration
        服务之间的真实连接验证

    E2E
        完整业务链路验证
"""

from __future__ import annotations


__version__ = "0.1.0"

__all__ = [
    "api",
    "agent",
    "e2e",
    "integration",
]