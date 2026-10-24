"""
SmartOps Agent Runtime Context.

Context用于保存Agent运行期间的请求级信息，
例如：
- request_id
- user_id
- role
- environment
- dry_run
- metadata
"""

from .context import RuntimeContext

__all__ = [
    "RuntimeContext",
]