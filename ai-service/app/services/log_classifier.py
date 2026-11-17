"""P1-2 日志分类推理服务。

设计：
- 全局单例模型（经验 578502：避免重复 from_pretrained 导致的 Windows 崩溃）
- torch 缺失 → TextCNN fallback；transformers 缺失 → keyword heuristic
- 标签空间与训练脚本严格对齐（LABEL_SPACE / LABEL_TO_ID / ID_TO_LABEL）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

# 经验 578502：Windows CPU 推理崩溃预防——必须在 transformers import 之前设
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ---------------------------------------------------------------------------
# 依赖探测
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
_TRANSFORMERS_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None

try:
    from transformers import BertTokenizerFast  # type: ignore[import-untyped]
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    BertTokenizerFast = None


from ..training.log_model import (  # noqa: E402
    LABEL_SPACE,
    NUM_LABELS,
    ID_TO_LABEL,
    LABEL_TO_ID,
    heuristic_classify,
    keywords_to_ids,
    KEYWORD_VOCAB,
    _TORCH_AVAILABLE as _TORCH_TRAINING,
    _TRANSFORMERS_AVAILABLE as _TF_TRAINING,
)
# 用 training 模块的标志覆盖（它已经 import 过 transformers）
_TORCH_AVAILABLE = _TORCH_TRAINING
_TRANSFORMERS_AVAILABLE = _TF_TRAINING


# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------

@dataclass
class _ModelState:
    kind: Literal["unavailable", "heuristic", "textcnn", "tinybert"] = "unavailable"
    variant: str = "heuristic"
    reason: str | None = None
    model: Any = None            # TinyBERT/TextCNN nn.Module 或 None
    tokenizer: Any = None        # BertTokenizerFast 或 None
    max_len: int = 64
    model_name: str | None = None
    vocab_size: int = len(KEYWORD_VOCAB) + 1


_state: _ModelState | None = None


def init_model(model_path: Path | None = None) -> _ModelState:
    """加载权重或初始化 fallback（幂等）。"""
    global _state
    state = _ModelState()

    if not _TORCH_AVAILABLE:
        state.kind = "heuristic"
        state.variant = "heuristic"
        state.reason = "torch 未安装，降级为关键词匹配 heuristic"
        _state = state
        return state

    # 权重存在 → 加载（自动识别 variant）
    if model_path and model_path.exists():
        try:
            ckpt = torch.load(model_path, map_location="cpu")
            variant = ckpt.get("variant", "textcnn")
            state.variant = variant
            state.max_len = ckpt.get("max_len", 64)

            if variant == "tinybert" and _TRANSFORMERS_AVAILABLE:
                from ..training.log_model import TinyBERTLogClassifier

                model_name = ckpt.get("model_name", "huawei-noah/TinyBERT_General_4L_312D")
                state.model_name = model_name
                model = TinyBERTLogClassifier(num_labels=NUM_LABELS, model_name=model_name, freeze_backbone=True)
                model.load_state_dict(ckpt["model_state"])
                model.eval()
                state.model = model
                # tokenizer 尝试从同目录加载，否则 from_pretrained
                tokenizer_dir = model_path.parent / "tokenizer"
                if tokenizer_dir.exists():
                    state.tokenizer = BertTokenizerFast.from_pretrained(str(tokenizer_dir))
                else:
                    state.tokenizer = BertTokenizerFast.from_pretrained(model_name)
                state.kind = "tinybert"
            elif variant == "textcnn":
                from ..training.log_model import TextCNNLogClassifier

                vocab_size = ckpt.get("vocab_size", len(KEYWORD_VOCAB) + 1)
                model = TextCNNLogClassifier(num_labels=NUM_LABELS, vocab_size=vocab_size, max_len=state.max_len)
                model.load_state_dict(ckpt["model_state"])
                model.eval()
                state.model = model
                state.kind = "textcnn"
            else:
                state.kind = "heuristic"
                state.reason = f"未知 variant={variant}，降级为 heuristic"
        except Exception as exc:
            state.kind = "heuristic"
            state.variant = "heuristic"
            state.reason = f"权重加载失败({exc})，降级为 heuristic"
    else:
        state.kind = "heuristic"
        state.variant = "heuristic"
        state.reason = "未找到 log_classifier.pt，降级为关键词匹配 heuristic"

    _state = state
    return state


def get_state() -> _ModelState:
    if _state is None:
        return init_model()
    return _state


# ---------------------------------------------------------------------------
# 推理入口
# ---------------------------------------------------------------------------

def classify(request) -> dict:
    """主入口：LogClassifyRequest → 分类结果字典。"""
    state = get_state()

    logs = request.logs
    texts = [log.text for log in logs]

    # 打分
    if state.kind == "tinybert" and _TORCH_AVAILABLE and state.tokenizer is not None:
        probs = _score_tinybert(state, texts)
    elif state.kind == "textcnn" and _TORCH_AVAILABLE and state.model is not None:
        probs = _score_textcnn(state, texts)
    else:
        probs = _score_heuristic(texts)

    # 后处理
    noise_idx = LABEL_TO_ID["noise"]
    results = []
    label_distribution: dict[str, int] = {}
    num_filtered = 0

    for i, log in enumerate(logs):
        text_probs = probs[i]  # (8,)
        pred_id = int(np.argmax(text_probs))
        confidence = float(text_probs[pred_id])
        label = ID_TO_LABEL[pred_id]
        is_noise = (pred_id == noise_idx)

        top_idx = np.argsort(-text_probs)[:3]
        top_labels = [
            {"label": ID_TO_LABEL[int(k)], "confidence": round(float(text_probs[int(k)]), 4)}
            for k in top_idx
        ]

        should_keep = not (request.filter_noise and is_noise)
        if request.filter_noise and is_noise:
            num_filtered += 1

        results.append({
            "label": label,
            "confidence": round(confidence, 4),
            "is_noise": is_noise,
            "top_labels": top_labels,
            "should_keep": should_keep,
        })
        label_distribution[label] = label_distribution.get(label, 0) + 1

    return {
        "ok": True,
        "mode": state.kind,
        "num_total": len(logs),
        "num_kept": len(logs) - num_filtered,
        "num_filtered_noise": num_filtered,
        "results": results,
        "label_distribution": label_distribution,
    }


def get_model_info() -> dict:
    state = get_state()
    return {
        "available": state.kind != "unavailable",
        "kind": state.kind,
        "variant": state.variant,
        "reason": state.reason,
        "torch_available": _TORCH_AVAILABLE,
        "transformers_available": _TRANSFORMERS_AVAILABLE,
        "num_labels": NUM_LABELS,
    }


# ---------------------------------------------------------------------------
# 内部打分
# ---------------------------------------------------------------------------

def _score_tinybert(state: _ModelState, texts: list[str]) -> np.ndarray:
    """TinyBERT batch 推理 → (B, 8) softmax probs。"""
    if not texts or state.model is None or state.tokenizer is None:
        return np.zeros((len(texts), NUM_LABELS), dtype=np.float32)
    enc = state.tokenizer(
        texts, padding=True, truncation=True,
        max_length=state.max_len, return_tensors="pt",
    )
    with torch.no_grad():
        logits = state.model(enc["input_ids"], enc["attention_mask"])
        probs = torch.softmax(logits, dim=-1).numpy()
    return probs


def _score_textcnn(state: _ModelState, texts: list[str]) -> np.ndarray:
    """TextCNN batch 推理 → (B, 8) softmax probs。"""
    if not texts or state.model is None:
        return np.zeros((len(texts), NUM_LABELS), dtype=np.float32)
    ids = np.stack([keywords_to_ids(t, state.max_len) for t in texts])
    with torch.no_grad():
        logits = state.model(torch.tensor(ids))
        probs = torch.softmax(logits, dim=-1).numpy()
    return probs


def _score_heuristic(texts: list[str]) -> np.ndarray:
    """Keyword heuristic → (B, 8) 确定性 probs（argmax 用）。"""
    probs = np.zeros((len(texts), NUM_LABELS), dtype=np.float32)
    for i, text in enumerate(texts):
        label, conf = heuristic_classify(text)
        probs[i, LABEL_TO_ID[label]] = max(conf, 0.5)
        # 剩余概率均分给其他标签（让 softmax 后 argmax 正确）
        remaining = 1.0 - probs[i, LABEL_TO_ID[label]]
        n_other = NUM_LABELS - 1
        for j in range(NUM_LABELS):
            if j != LABEL_TO_ID[label]:
                probs[i, j] = remaining / n_other
    return probs
