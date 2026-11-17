"""Ultra 多路择优（P4，蒸馏 AgentForge）：同一环节并行多路 → 择优 → 校准。"""

from agent.ultra.parallel import ULTRA_PERSONAS, UltraError, UltraResult, UltraRunner

__all__ = ["UltraRunner", "UltraResult", "UltraError", "ULTRA_PERSONAS"]
