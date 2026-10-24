"""
SmartOps File Session Plugin.

提供基于本地 JSON 文件的 Session 持久化能力。

适用场景：
- 本地开发
- Demo
- 单元测试
- 集成测试
- 单机实验

注意：
File Session 不适合高并发、分布式生产环境。
"""

from .provider import FileSessionProvider


__all__ = [
    "FileSessionProvider",
]


__version__ = "1.0.0"
__provider_name__ = "file"