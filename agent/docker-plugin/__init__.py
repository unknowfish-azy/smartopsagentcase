"""
SmartOps Docker Plugin.

提供：
- docker.ps
- docker.inspect
- docker.logs
- docker.compose
- docker.restart
"""

from .plugin import DockerPlugin

__all__ = [
    "DockerPlugin",
]