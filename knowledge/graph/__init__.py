"""知识图谱（P2-7 / B）：词表 + 规则抽取 + 邻接表存储 + 符号推理。

神经符号边界：**神经**负责召回（现有 hybrid 检索），**符号**负责可解释推导。
符号结论必须能回溯到边与 ``source_entry_id``，否则标 ``neural_only``。
"""

from .extract import RuleExtractor, parse_entry_payload
from .reason import (
    CANDIDATE_TYPES,
    Candidate,
    DerivationStep,
    ReasoningResult,
    SymbolicReasoner,
)
from .schema import (
    COMPONENT_VOCAB,
    ENTITY_TYPES,
    METRIC_VOCAB,
    RELATION_TYPES,
    RUN_VOCAB,
    Edge,
    Entity,
    ExtractionResult,
    match_entities,
)
from .store import KnowledgeGraph

__all__ = [
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "COMPONENT_VOCAB",
    "METRIC_VOCAB",
    "RUN_VOCAB",
    "Entity",
    "Edge",
    "ExtractionResult",
    "match_entities",
    "RuleExtractor",
    "parse_entry_payload",
    "KnowledgeGraph",
    "CANDIDATE_TYPES",
    "Candidate",
    "DerivationStep",
    "ReasoningResult",
    "SymbolicReasoner",
]
