"""
SmartOps Harness Providers.

Providers用于向SmartOps Harness提供外部能力适配：

- Skill Provider
- Model Provider
- Tool Provider
- Storage Provider

Provider本身主要负责：
    发现
    连接
    适配
    获取

不直接负责：
    Permission
    Risk
    SafeAgent
    Approval
    Sandbox
    Executor
"""

__version__ = "0.1.0"

__all__ = [
    "skill",
    "model",
    "tool",
    "storage",
]