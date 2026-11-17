"""P1-2 TinyBERT 日志分类共享模型。

标签空间（运维场景，7 类 + noise 用于前置过滤）：

  oom            内存耗尽    Java heap / worker OOM killer
  timeout        超时        连接/请求超时
  disk_full      磁盘满      inode / space 耗尽
  connection_refused  连接拒绝  port close / endpoint down
  process_crash  进程崩溃    segfault / exit code
  auth_error     认证失败    401/403/Token expired
  network_error  网络异常    DNS / unreachable / reset
  noise          正常心跳    健康检查、周期性 INFO 日志

设计：
- 预训练 TinyBERT4Chinese（hfl/chinese-tinybert-v2-sentence）+ 冻结 backbone + 线性分类头
  ——小数据弱标注场景的最优策略（经验 1800066：只训练分类头）
- 依赖缺失时 → TextCNN 轻量 fallback（纯 PyTorch，不用 transformers）
- 全部 forward 签名统一：forward(texts, return_probs=True) → (probs, label_ids)

经验 578502 教训：
- 不要重复 from_pretrained，单例全局复用
- Windows 下 torch.set_num_threads(1) 避免 CPU 崩溃
- 自定义 state_dict 保存，不是 transformers.save_pretrained 格式
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# 全局线程限制（经验 578502：Windows CPU 推理崩溃预防）
# ---------------------------------------------------------------------------
import os
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_TORCH_AVAILABLE = False
_TRANSFORMERS_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    import torch.nn as nn  # type: ignore[import-untyped]

    _TORCH_AVAILABLE = True
    try:
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except Exception:
        pass
except ImportError:
    torch = None
    nn = None

try:
    from transformers import (  # type: ignore[import-untyped]
        BertTokenizerFast,
        BertModel,
        AutoConfig,
    )

    _TRANSFORMERS_AVAILABLE = True
except ImportError:  # pragma: no cover
    BertTokenizerFast = None
    BertModel = None
    AutoConfig = None


# ---------------------------------------------------------------------------
# 标签空间（固定顺序，训练和推理必须对齐）
# ---------------------------------------------------------------------------

LABEL_SPACE: tuple[str, ...] = (
    "oom",
    "timeout",
    "disk_full",
    "connection_refused",
    "process_crash",
    "auth_error",
    "network_error",
    "noise",
)
NUM_LABELS = len(LABEL_SPACE)
LABEL_TO_ID: dict[str, int] = {name: i for i, name in enumerate(LABEL_SPACE)}
ID_TO_LABEL: dict[int, str] = {i: name for i, name in enumerate(LABEL_SPACE)}


def available() -> str:
    if _TORCH_AVAILABLE and _TRANSFORMERS_AVAILABLE:
        return "tinybert"
    if _TORCH_AVAILABLE:
        return "textcnn"
    return "heuristic"


# ---------------------------------------------------------------------------
# TinyBERT 模型
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE and _TRANSFORMERS_AVAILABLE:

    class TinyBERTLogClassifier(nn.Module):
        """预训练 TinyBERT4Chinese + 冻结 backbone + 线性分类头。

        forward(text_ids, attention_mask) → logits (B, 8)
        训练时可 set mode="finetune" 解冻最后一层。
        """

        def __init__(
            self,
            num_labels: int = NUM_LABELS,
            model_name: str = "huawei-noah/TinyBERT_General_4L_312D",
            freeze_backbone: bool = True,
            dropout: float = 0.1,
        ):
            super().__init__()
            self.num_labels = num_labels
            self.model_name = model_name
            self.config = AutoConfig.from_pretrained(model_name)
            self.bert = BertModel.from_pretrained(model_name)
            self.hidden_dim = self.config.hidden_size
            self.dropout = nn.Dropout(dropout)
            self.classifier = nn.Linear(self.hidden_dim, num_labels)

            if freeze_backbone:
                for param in self.bert.parameters():
                    param.requires_grad = False

        def forward(self, input_ids, attention_mask=None):
            outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
            # 用 CLS token 做分类
            cls = outputs.last_hidden_state[:, 0, :]
            cls = self.dropout(cls)
            logits = self.classifier(cls)
            return logits


# ---------------------------------------------------------------------------
# TextCNN fallback（纯 PyTorch，不依赖 transformers）
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE and not _TRANSFORMERS_AVAILABLE:

    class TextCNNLogClassifier(nn.Module):
        """词袋特征 + Conv1d 多头卷积 + 分类。

        当 transformers 没装时的降级路径——简单好训，足够做 baseline。
        词表是预先定义的运维关键词集合（见 KEYWORD_VOCAB）。
        """

        def __init__(
            self,
            num_labels: int = NUM_LABELS,
            vocab_size: int = 128,
            embed_dim: int = 64,
            num_filters: int = 32,
            filter_sizes: tuple[int, ...] = (2, 3, 4),
            max_len: int = 64,
        ):
            super().__init__()
            self.num_labels = num_labels
            self.vocab_size = vocab_size
            self.max_len = max_len
            self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
            self.convs = nn.ModuleList([
                nn.Conv1d(embed_dim, num_filters, kernel_size=f) for f in filter_sizes
            ])
            self.pool = nn.AdaptiveMaxPool1d(1)
            self.dropout = nn.Dropout(0.3)
            self.classifier = nn.Linear(num_filters * len(filter_sizes), num_labels)

        def forward(self, input_ids, attention_mask=None):
            emb = self.embedding(input_ids)  # (B, L, D)
            emb = emb.transpose(1, 2)  # (B, D, L) — Conv1d 要 channel 在 dim=1
            conv_out = []
            for conv in self.convs:
                c = conv(emb)
                c = torch.relu(c)
                c = self.pool(c).squeeze(-1)
                conv_out.append(c)
            h = torch.cat(conv_out, dim=1)
            h = self.dropout(h)
            logits = self.classifier(h)
            return logits


# ---------------------------------------------------------------------------
# 关键词词表 + 向量化（heuristic fallback 用，也给 TextCNN 用）
# ---------------------------------------------------------------------------

KEYWORD_VOCAB: dict[str, int] = {
    # 0 留给 padding
    "oom": 1, "out of memory": 2, "heap": 3, "killed": 4,
    "timeout": 5, "timed out": 6, "connect": 7,
    "disk": 8, "no space": 9, "inode": 10,
    "refused": 11, "connection refused": 12, "econnrefused": 13,
    "crash": 14, "segmentation": 15, "segfault": 16, "exit code": 17,
    "401": 18, "403": 19, "unauthorized": 20, "forbidden": 21, "token expired": 22,
    "dns": 23, "unreachable": 24, "reset": 25, "network": 26,
    "heartbeat": 27, "health check": 28, "alive": 29, "pong": 30,
    "warning": 31, "warn": 32, "error": 33, "fatal": 34, "info": 35,
    "started": 36, "stopped": 37, "running": 38, "ready": 39,
    "java": 40, "python": 41, "go": 42, "node": 43, "kubernetes": 44, "pod": 45,
    "redis": 46, "mysql": 47, "postgres": 48, "mongo": 49, "kafka": 50,
    "prometheus": 51, "grafana": 52, "nginx": 53, "docker": 54,
    "exception": 55, "traceback": 56, "stack": 57,
    "slow": 58, "latency": 59, "high cpu": 60, "high memory": 61,
    "retry": 62, "fail": 63, "success": 64, "ok": 65,
}


def keywords_to_ids(text: str, max_len: int = 64, vocab: dict[str, int] | None = None) -> np.ndarray:
    """简单的关键词匹配 → ID 序列。用于 heuristic + TextCNN fallback。"""
    vocab = vocab or KEYWORD_VOCAB
    text_lower = text.lower()
    ids = []
    for kw, kid in sorted(vocab.items(), key=lambda x: -len(x[0])):  # 先匹配长的
        while kw in text_lower:
            ids.append(kid)
            idx = text_lower.find(kw)
            text_lower = text_lower[:idx] + " " * len(kw) + text_lower[idx + len(kw):]
    if not ids:
        ids = [0]  # padding
    ids = ids[:max_len]
    if len(ids) < max_len:
        ids = ids + [0] * (max_len - len(ids))
    return np.array(ids, dtype=np.int64)


def heuristic_classify(text: str) -> tuple[str, float]:
    """无 torch 时的 heuristic：关键词匹配打分。"""
    text_lower = text.lower()
    scores: dict[str, float] = {}

    # oom
    if any(k in text_lower for k in ("out of memory", "oom", "heap memory", "killed process", "error")):
        scores["oom"] = 2.0 if any(k in text_lower for k in ("oom", "out of memory", "killed")) else 0.5
    # timeout
    if any(k in text_lower for k in ("timeout", "timed out", "deadline exceeded", "context deadline")):
        scores["timeout"] = 2.0
    # disk_full
    if any(k in text_lower for k in ("no space left", "disk full", "out of disk", "inode")):
        scores["disk_full"] = 2.0
    # connection_refused
    if any(k in text_lower for k in ("connection refused", "econnrefused", "port closed", "not reachable")):
        scores["connection_refused"] = 2.0
    # process_crash
    if any(k in text_lower for k in ("segmentation fault", "segfault", "exit code", "crash", "aborted")):
        scores["process_crash"] = 2.0
    # auth_error
    if any(k in text_lower for k in ("unauthorized", "403", "forbidden", "token expired", "auth fail")):
        scores["auth_error"] = 2.0
    # network_error
    if any(k in text_lower for k in ("dns fail", "unreachable", "connection reset", "network error")):
        scores["network_error"] = 2.0
    # noise（心跳/健康检查）
    if any(k in text_lower for k in ("heartbeat", "health check", "alive", "pong", "started", "ready")):
        scores["noise"] = 1.5

    if not scores:
        return "noise", 0.1  # 默认当作噪音
    label = max(scores, key=scores.get)
    return label, min(scores[label] / 2.0, 1.0)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class LogClassifierConfig:
    variant: str = "tinybert"  # "tinybert" | "textcnn" | "heuristic"
    model_name: str = "huawei-noah/TinyBERT_General_4L_312D"
    freeze_backbone: bool = True
    dropout: float = 0.1
    max_len: int = 64
    lr: float = 2e-3
    epochs: int = 30
    batch_size: int = 32
    seed: int = 17
