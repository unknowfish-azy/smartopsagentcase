"""数字人「情绪识别输入」（缺口清单 P2-8 收口）。

背景：数字人三短板（音素口型 / 情绪识别输入 / 打断能力）中，
口型（`useLipSync.js` + `chineseViseme.js`）与打断（`PersonaPet.vue` 的 barge-in）
均已落地，本模块补最后一项——把**用户文本**（ASR 转写 / 文本输入）识别成情绪标签，
供前端 `withEmotion(profile, emotion)` 叠加到 `personaStates.js` 的 expressions 权重。

三条边界（与 `app/vision/ocr.py` 同纪律）：
1. **不伪造**：引擎缺失 / 失败一律 `status=UNAVAILABLE` + 原因，不编造标签；
2. **不冒充**：模型本质是「情感极性二分类」时如实标注维度限制，
   不写成「五分类情绪模型」；
3. **纯函数可测**：`normalize_text` / 词表匹配 / 标签映射均可独立单测。

懒加载：`import app.emotion.engine` 不加载模型，pytest 与离线脚本可正常导入。
"""

from __future__ import annotations

import importlib.util
import os
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

_REQUIRED_MODULES = ("jieba",)
_OPTIONAL_MODULES = ("torch", "transformers")

# 渲染层实际支持的表情枚举（见 frontend/src/components/persona/personaStates.js）
EMOTION_LABELS = ("happy", "sad", "angry", "surprised", "neutral")

DEFAULT_MIN_CONFIDENCE = 0.0
DEFAULT_MAX_TEXT = 200

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = _REPO_ROOT / "models" / "emotion" / "erlangshen-sentiment"


class EmotionEngineUnavailable(RuntimeError):
    """情绪引擎不可用（缺依赖 / 权重缺失），由调用方降级。"""


class EmotionInputError(ValueError):
    """入参不可用（空文本等），由路由映射成 400。"""


# ---------------------------------------------------------------------------
# 词表（自建，中文）。分「强」「弱」两档：强词命中即判定，弱词命中给低置信度。
# 说明：这是**兜底路径**，词表小、覆盖面有限，如实标注为 rule 来源。
# ---------------------------------------------------------------------------
_STRONG_LEXICON: dict[str, tuple[str, ...]] = {
    "happy": (
        "开心", "高兴", "快乐", "兴奋", "欢喜", "喜悦", "满意", "舒服",
        "太棒了", "棒极了", "成功了", "顺利", "好消息", "哈哈", "嘿嘿", "嘻嘻",
    ),
    "sad": (
        "难过", "伤心", "悲伤", "失望", "沮丧", "郁闷", "痛苦", "委屈",
        "崩溃", "糟透了", "失败了", "呜呜", "想哭",
    ),
    "angry": (
        "生气", "愤怒", "恼火", "气愤", "气死", "火大", "忍无可忍",
        "混蛋", "该死", "讨厌", "可恶",
    ),
    "surprised": (
        "惊讶", "吃惊", "震惊", "意外", "天哪", "天啊", "居然", "竟然",
        "没想到", "吓一跳", "哇", "啊",
    ),
}

_WEAK_LEXICON: dict[str, tuple[str, ...]] = {
    "happy": ("好", "棒", "赞", "喜欢", "可以", "不错", "感谢", "期待"),
    "sad": ("差", "坏", "糟", "问题", "故障", "报错", "失败", "慢", "卡"),
    "angry": ("垃圾", "服了", "无语", "烦"),
    "surprised": ("嗯?", "咦", "哦?", "真的吗"),
}

_NEGATIONS = ("不", "没", "没有", "别", "非", "未", "无", "莫")


def normalize_text(text: str) -> str:
    """NFKC 归一 + 折叠空白 + 去零宽字符。纯函数，可单测。"""
    import unicodedata

    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def truncate_text(text: str, limit: int) -> str:
    """按字符截断；limit<=0 不截断。"""
    if limit is None or limit <= 0:
        return text
    return text[:limit]


@dataclass(frozen=True)
class EmotionResult:
    """一次情绪识别的结果。`status` 取 `SUCCEEDED` / `EMPTY` / `UNAVAILABLE`。"""

    label: str = "neutral"
    confidence: float | None = None
    scores: dict[str, float] = field(default_factory=dict)
    engine: str = ""
    status: str = "UNAVAILABLE"
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0


# ---------------------------------------------------------------------------
# 词典引擎（兜底，零下载）
# ---------------------------------------------------------------------------
class LexiconEmotionEngine:
    """基于 jieba 分词 + 自建词表的情绪判定。覆盖面有限，如实标 `engine="lexicon"`。"""

    name = "lexicon"

    def __init__(self, strong: dict[str, tuple[str, ...]] | None = None,
                 weak: dict[str, tuple[str, ...]] | None = None) -> None:
        self._strong = strong or _STRONG_LEXICON
        self._weak = weak or _WEAK_LEXICON

    @staticmethod
    def _tokens(text: str) -> list[str]:
        import jieba

        return [t for t in jieba.cut(text) if t.strip()]

    def recognize(self, text: str) -> EmotionResult:
        started = time.perf_counter()
        norm = normalize_text(text)
        if not norm:
            return EmotionResult(status="EMPTY", engine=self.name,
                                 elapsed_ms=_elapsed_ms(started))

        tokens = self._tokens(norm)
        # 否定词检测：按**分词 token** 判断，避免「不错」被误判成含否定词「不」
        has_negation = any(neg in tokens for neg in _NEGATIONS)

        strong_hits = {k: sum(1 for w in ws if w in norm) for k, ws in self._strong.items()}
        strong_hits = {k: v for k, v in strong_hits.items() if v > 0}
        if strong_hits:
            label = max(strong_hits, key=lambda k: strong_hits[k])
            conf = 0.45 if has_negation else 0.8
            return EmotionResult(label=label, confidence=conf, engine=self.name,
                                 status="SUCCEEDED",
                                 warnings=(["文本含否定词，置信度已下调"] if has_negation else []),
                                 elapsed_ms=_elapsed_ms(started))

        weak_hits = {k: sum(1 for w in ws if w in norm) for k, ws in self._weak.items()}
        weak_hits = {k: v for k, v in weak_hits.items() if v > 0}
        if weak_hits:
            label = max(weak_hits, key=lambda k: weak_hits[k])
            conf = 0.3 if has_negation else 0.5
            return EmotionResult(label=label, confidence=conf, engine=self.name,
                                 status="SUCCEEDED",
                                 warnings=(["文本含否定词，置信度已下调"] if has_negation else []),
                                 elapsed_ms=_elapsed_ms(started))

        return EmotionResult(label="neutral", confidence=None, engine=self.name,
                             status="SUCCEEDED", elapsed_ms=_elapsed_ms(started))


# ---------------------------------------------------------------------------
# Transformers 引擎（可选，情感极性二分类）
# ---------------------------------------------------------------------------
class TransformersEmotionEngine:
    """本地中文情感模型（Erlangshen-Roberta-110M-Sentiment）。

    ⚠️ 该模型本质是**情感极性二分类**（正面 / 负面），**不能**输出
    怒 / 惊等细粒度情绪——这是维度限制，调用方须如实标注。
    """

    name = "transformers"

    def __init__(self, model_dir: str | os.PathLike[str] | None = None) -> None:
        self.model_dir = Path(model_dir) if model_dir else Path(
            os.environ.get("EMOTION_MODEL_DIR", str(DEFAULT_MODEL_DIR))
        )
        self._model: Any = None
        self._tokenizer: Any = None
        self._id2label: dict[int, str] = {}
        self._reason: str | None = None

    @staticmethod
    def _module_available() -> bool:
        return all(importlib.util.find_spec(m) for m in _OPTIONAL_MODULES)

    def available(self) -> bool:
        return self._load()

    @property
    def reason(self) -> str | None:
        return self._reason

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if not self._module_available():
            self._reason = "缺少 torch / transformers"
            return False
        if not (self.model_dir / "config.json").exists():
            self._reason = f"模型目录不存在或缺少 config.json：{self.model_dir}"
            return False
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir))
            self._model = AutoModelForSequenceClassification.from_pretrained(str(self.model_dir))
            self._model.eval()
            self._id2label = {int(k): str(v) for k, v in self._model.config.id2label.items()}
            self._torch = torch
            return True
        except Exception as exc:  # 权重损坏 / 版本不兼容都要降级
            self._reason = f"模型加载失败：{exc}"
            self._model = None
            return False

    def _label_for(self, idx: int) -> str | None:
        raw = self._id2label.get(idx, "").lower()
        if any(k in raw for k in ("pos", "good", "正面", "积极", "1")):
            return "happy"
        if any(k in raw for k in ("neg", "bad", "负面", "消极", "0")):
            return "sad"
        return None

    def recognize(self, text: str) -> EmotionResult:
        started = time.perf_counter()
        norm = normalize_text(text)
        if not norm:
            return EmotionResult(status="EMPTY", engine=self.name,
                                 elapsed_ms=_elapsed_ms(started))
        if not self._load():
            return EmotionResult(status="UNAVAILABLE", engine=self.name,
                                 warnings=[self._reason or "模型不可用"],
                                 elapsed_ms=_elapsed_ms(started))
        try:
            inputs = self._tokenizer(norm, return_tensors="pt", truncation=True, max_length=256)
            with self._torch.no_grad():
                logits = self._model(**inputs).logits
                probs = self._torch.softmax(logits, dim=-1)[0].tolist()
        except Exception as exc:
            return EmotionResult(status="UNAVAILABLE", engine=self.name,
                                 warnings=[f"推理失败：{exc}"],
                                 elapsed_ms=_elapsed_ms(started))

        order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top = order[0]
        label = self._label_for(top)
        if label is None:
            return EmotionResult(status="UNAVAILABLE", engine=self.name,
                                 warnings=[f"无法解析模型标签：{self._id2label}"],
                                 elapsed_ms=_elapsed_ms(started))
        scores = {}
        for i, p in enumerate(probs):
            mapped = self._label_for(i)
            if mapped:
                scores[mapped] = round(float(p), 4)
        return EmotionResult(label=label, confidence=round(float(probs[top]), 4),
                             scores=scores, engine=self.name, status="SUCCEEDED",
                             warnings=["模型为情感极性二分类，仅输出 happy/sad"],
                             elapsed_ms=_elapsed_ms(started))


# ---------------------------------------------------------------------------
# 组合引擎：强词优先 → 模型极性 → 弱词 → 中性
# ---------------------------------------------------------------------------
class CompositeEmotionEngine:
    """默认引擎：词典强词优先，模型极性兜底，弱词再兜底，最后 neutral。

    这样做的理由：模型是二分类，单独用它无法识别怒/惊；强词命中更可信，
    故优先；模型只在无强词时提供极性判断。
    """

    name = "composite"

    def __init__(self, lexicon: LexiconEmotionEngine | None = None,
                 model: TransformersEmotionEngine | None = None) -> None:
        self.lexicon = lexicon or LexiconEmotionEngine()
        self.model = model or TransformersEmotionEngine()

    def recognize(self, text: str) -> EmotionResult:
        started = time.perf_counter()
        norm = normalize_text(text)
        if not norm:
            return EmotionResult(status="EMPTY", engine=self.name,
                                 elapsed_ms=_elapsed_ms(started))

        # 1) 词典强词
        strong = self.lexicon.recognize(norm)
        if strong.status == "SUCCEEDED" and strong.confidence == 0.8:
            return replace(strong, engine=f"{self.name}+lexicon", elapsed_ms=_elapsed_ms(started))

        # 2) 模型极性
        if self.model.available():
            model_res = self.model.recognize(norm)
            if model_res.status == "SUCCEEDED" and model_res.confidence is not None:
                merged = EmotionResult(
                    label=model_res.label,
                    confidence=model_res.confidence,
                    scores=model_res.scores,
                    engine=f"{self.name}+model",
                    status="SUCCEEDED",
                    warnings=list(model_res.warnings),
                    elapsed_ms=_elapsed_ms(started),
                )
                return merged

        # 3) 词典（弱词 / 中性）
        if strong.status == "SUCCEEDED":
            return replace(strong, engine=f"{self.name}+lexicon", elapsed_ms=_elapsed_ms(started))
        return EmotionResult(label="neutral", confidence=None, engine=self.name,
                             status="SUCCEEDED", elapsed_ms=_elapsed_ms(started))


# ---------------------------------------------------------------------------
# 引擎解析（懒加载，可重置）
# ---------------------------------------------------------------------------
_engine: CompositeEmotionEngine | None = None
_engine_reason: str | None = None


def reset_engine() -> None:
    """测试用：清掉单例。"""
    global _engine, _engine_reason
    _engine = None
    _engine_reason = None


def resolve_engine() -> tuple[CompositeEmotionEngine | None, str | None]:
    """返回 (引擎, 原因)。引擎始终构造（词典永远可用），仅记录模型可用性。"""
    global _engine, _engine_reason
    if _engine is None:
        model = TransformersEmotionEngine()
        model_ok = model.available()
        _engine_reason = None if model_ok else (model.reason or "模型不可用")
        _engine = CompositeEmotionEngine(model=model)
    return _engine, _engine_reason


def recognize(text: str, *, engine: CompositeEmotionEngine | None = None,
              max_text: int = DEFAULT_MAX_TEXT) -> EmotionResult:
    """识别一条文本的情绪。空文本 → EMPTY；引擎不可用 → UNAVAILABLE。"""
    started = time.perf_counter()
    if engine is not None:
        resolved, reason = engine, None
    else:
        resolved, reason = resolve_engine()
    if resolved is None:
        return EmotionResult(status="UNAVAILABLE", engine="none",
                             warnings=[reason or "情绪引擎不可用"],
                             elapsed_ms=_elapsed_ms(started))
    clipped = truncate_text(normalize_text(text), max_text)
    result = resolved.recognize(clipped)
    if result.status == "SUCCEEDED" and reason and not result.warnings:
        result.warnings.append(f"模型不可用，已降级词典：{reason}")
    return result


def get_emotion_info() -> dict[str, Any]:
    """供 `/api/nn/emotion-info` 使用。"""
    engine, reason = resolve_engine()
    model = engine.model if engine else None
    return {
        "available": True,
        "engine": engine.name if engine else "none",
        "labels": list(EMOTION_LABELS),
        "model_dir": str(getattr(model, "model_dir", None)) if model else None,
        "model_available": bool(model and model.available()),
        "model_reason": reason,
        "model_dimension": "情感极性二分类（仅 happy/sad，维度限制）",
        "lexicon_labels": list(_STRONG_LEXICON.keys()),
        "warnings": ([f"模型不可用：{reason}"] if reason else []),
    }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
