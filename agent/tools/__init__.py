"""
Agent Tools Module.

所有 Agent 可以调用的工具统一在这里注册。
"""

from .base import AgentTool
from .registry import ToolRegistry
from .models import ToolMetadata
from .errors import (
    FAILURE_GRADE,
    ToolErrorCategory,
    ToolExecutionError,
    classify_exception,
)
from .validation import truncate_output, validate_arguments
from .shell import ShellTool
from .server import ServerStatusTool
from .knowledge import KnowledgeSearchTool
from .speech import SpeechToTextTool


__all__ = [
    "AgentTool",
    "ToolRegistry",
    "ToolMetadata",
    "ToolErrorCategory",
    "ToolExecutionError",
    "FAILURE_GRADE",
    "classify_exception",
    "validate_arguments",
    "truncate_output",
    "ShellTool",
    "ServerStatusTool",
    "KnowledgeSearchTool",
    "SpeechToTextTool",
]