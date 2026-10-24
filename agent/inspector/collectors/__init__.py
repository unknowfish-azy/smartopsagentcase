"""
SmartOps Inspector Collectors。

从 Agent Runtime / EventBus 收集执行轨迹、证据、工具调用等，
供 Inspector 进行纠察。
"""

from agent.inspector.collectors.trace_collector import TraceCollector

__all__ = [
    "TraceCollector",
]
