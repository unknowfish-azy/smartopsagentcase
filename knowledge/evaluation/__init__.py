"""
SmartOpsAgent Knowledge Evaluation Module.

用于知识库检索效果评估，支持：

- EvaluationCase：评估样本
- load_dataset：加载 JSON 评估数据集
- hit_at_k：Hit@K
- recall_at_k：Recall@K
- mrr：MRR
- RetrievalEvaluator：检索器统一评估器
"""

from .models import EvaluationCase
from .dataset import load_dataset
from .metrics import hit_at_k, recall_at_k, mrr
from .evaluator import RetrievalEvaluator


__all__ = [
    "EvaluationCase",
    "load_dataset",
    "hit_at_k",
    "recall_at_k",
    "mrr",
    "RetrievalEvaluator",
]