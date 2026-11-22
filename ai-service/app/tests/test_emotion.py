"""NN-06 情绪识别输入测试（P2-8 收口）。

分两层：
1. **纯函数 / 词典 / 降级契约**（不加载模型、不联网）：归一化、截断、词表判定、
   引擎不可用时返回 UNAVAILABLE 而不是伪造；
2. **真实模型冒烟**（`importorskip` + 权重目录存在才跑）：没装/没权重就跳过，
   绝不用合成结果冒充引擎可用。
"""

from __future__ import annotations

import pytest

from app.emotion import engine as em
from app.emotion.engine import (
    EmotionResult,
    LexiconEmotionEngine,
    TransformersEmotionEngine,
)


# ---------------------------------------------------------------- 纯函数

def test_normalize_text_折叠空白并去零宽():
    assert em.normalize_text(" 今天  告警\u200b ") == "今天 告警"


def test_normalize_text_空输入返回空():
    assert em.normalize_text("") == ""
    assert em.normalize_text(None) == ""  # type: ignore[arg-type]


def test_truncate_text_超长截断且limit为0不截断():
    assert em.truncate_text("abcdefghij", 5) == "abcde"
    assert em.truncate_text("abcdefghij", 0) == "abcdefghij"


# ---------------------------------------------------------------- 词典引擎

def test_词典_强词命中给高置信度():
    r = LexiconEmotionEngine().recognize("今天告警全恢复了，真开心")
    assert r.status == "SUCCEEDED"
    assert r.label == "happy"
    assert r.confidence == 0.8


def test_词典_弱词命中给低置信度():
    r = LexiconEmotionEngine().recognize("这个结果不错")
    assert r.label == "happy"
    assert r.confidence == 0.5


def test_词典_无命中返回neutral():
    r = LexiconEmotionEngine().recognize("今天星期几")
    assert r.label == "neutral"
    assert r.confidence is None


def test_词典_否定词下调置信度并给警示():
    r = LexiconEmotionEngine().recognize("我不开心")
    assert r.label == "happy"  # 词面命中，但置信度下调（不做复杂极性翻转）
    assert r.confidence == 0.45
    assert any("否定" in w for w in r.warnings)


def test_词典_空文本返回EMPTY():
    r = LexiconEmotionEngine().recognize("   ")
    assert r.status == "EMPTY"


# ------------------------------------------------------------ 模型标签映射

def test_模型标签映射_positive到happy_negative到sad():
    engine = TransformersEmotionEngine()
    engine._id2label = {0: "Negative", 1: "Positive"}
    assert engine._label_for(1) == "happy"
    assert engine._label_for(0) == "sad"


def test_模型标签映射_无法解析返回none():
    engine = TransformersEmotionEngine()
    engine._id2label = {0: "weird"}
    assert engine._label_for(0) is None


# ---------------------------------------------------------------- 组合引擎

class _StubModel:
    """桩模型：只回一个固定极性结果。"""

    name = "stub-model"

    def __init__(self, label="sad", confidence=0.9, available=True):
        self._label = label
        self._conf = confidence
        self._available = available

    def available(self):
        return self._available

    def recognize(self, text):
        if not self._available:
            return EmotionResult(status="UNAVAILABLE", engine=self.name,
                                 warnings=["桩：模型不可用"])
        return EmotionResult(label=self._label, confidence=self._conf,
                             engine=self.name, status="SUCCEEDED")


class _StubLexicon:
    name = "stub-lexicon"

    def __init__(self, label="neutral", confidence=None):
        self._label = label
        self._conf = confidence

    def recognize(self, text):
        if self._label == "EMPTY":
            return EmotionResult(status="EMPTY", engine=self.name)
        return EmotionResult(label=self._label, confidence=self._conf,
                             engine=self.name, status="SUCCEEDED")


def test_组合_强词优先于模型():
    # 词典命中强词（confidence=0.8）时，即使模型给 sad 也应以词典为准
    composite = em.CompositeEmotionEngine(
        lexicon=LexiconEmotionEngine(), model=_StubModel(label="sad", confidence=0.9)
    )
    r = composite.recognize("真开心")  # 强词
    assert r.label == "happy"
    assert r.engine == "composite+lexicon"


def test_组合_无强词时用模型极性():
    composite = em.CompositeEmotionEngine(
        lexicon=_StubLexicon(label="neutral"), model=_StubModel(label="happy", confidence=0.77)
    )
    r = composite.recognize("今天天气不错")
    assert r.label == "happy"
    assert r.confidence == 0.77
    assert r.engine == "composite+model"


def test_组合_模型不可用时降级词典():
    composite = em.CompositeEmotionEngine(
        lexicon=LexiconEmotionEngine(), model=_StubModel(available=False)
    )
    r = composite.recognize("有点难过")  # 强词，走词典
    assert r.status == "SUCCEEDED"
    assert r.label == "sad"


def test_组合_空文本返回EMPTY():
    composite = em.CompositeEmotionEngine(
        lexicon=_StubLexicon(label="EMPTY"), model=_StubModel()
    )
    assert composite.recognize("  ").status == "EMPTY"


# ------------------------------------------------------------ recognize 契约

def test_recognize_空文本返回EMPTY():
    assert em.recognize("   ").status == "EMPTY"


def test_recognize_引擎不可用返回UNAVAILABLE且不伪造(monkeypatch):
    monkeypatch.setattr(em, "resolve_engine", lambda: (None, "缺少可选依赖"))
    r = em.recognize("今天很开心")
    assert r.status == "UNAVAILABLE"
    assert r.label == "neutral"
    assert r.confidence is None
    assert any("缺少可选依赖" in w for w in r.warnings)


def test_recognize_注入引擎时不走resolve(monkeypatch):
    stub = _StubLexicon(label="angry", confidence=0.6)
    called = {"n": 0}

    def _boom():
        called["n"] += 1
        raise AssertionError("不应调用 resolve_engine")

    monkeypatch.setattr(em, "resolve_engine", _boom)
    r = em.recognize("真生气", engine=em.CompositeEmotionEngine(lexicon=stub, model=_StubModel(available=False)))
    assert r.label == "angry"
    assert called["n"] == 0


# ---------------------------------------------------------------- 端点

def test_emotion端点_返回契约(client, monkeypatch):
    stub = em.CompositeEmotionEngine(
        lexicon=_StubLexicon(label="happy", confidence=0.66), model=_StubModel(available=False)
    )
    monkeypatch.setattr(em, "resolve_engine", lambda: (stub, "桩：模型不可用"))

    body = client.post("/api/nn/emotion", json={"text": "今天很开心"}).json()
    assert body["available"] is True
    assert body["label"] == "happy"
    assert body["confidence"] == 0.66
    assert body["engine"] == "composite+lexicon"
    assert body["status"] == "SUCCEEDED"


def test_emotion端点_引擎不可用回传UNAVAILABLE且不伪造(client, monkeypatch):
    monkeypatch.setattr(em, "resolve_engine", lambda: (None, "缺少可选依赖"))
    body = client.post("/api/nn/emotion", json={"text": "今天很开心"}).json()
    assert body["available"] is False
    assert body["ok"] is False
    assert body["status"] == "UNAVAILABLE"
    assert body["label"] == "neutral"
    assert body["confidence"] is None
    assert body["reason"]


def test_emotion端点_空文本400(client):
    assert client.post("/api/nn/emotion", json={"text": ""}).status_code == 422


def test_emotion端点_超长文本按max_text截断(client, monkeypatch):
    seen = {}

    class _Recording:
        name = "rec"

        def recognize(self, text):
            seen["text"] = text
            return EmotionResult(label="neutral", engine=self.name, status="SUCCEEDED")

    stub = em.CompositeEmotionEngine(lexicon=_Recording(), model=_StubModel(available=False))
    monkeypatch.setattr(em, "resolve_engine", lambda: (stub, None))

    client.post("/api/nn/emotion", json={"text": "a" * 500, "max_text": 10})
    assert seen["text"] == "a" * 10


def test_emotion_info端点可访问(client, monkeypatch):
    stub = em.CompositeEmotionEngine(lexicon=_StubLexicon(), model=_StubModel(available=False))
    monkeypatch.setattr(em, "resolve_engine", lambda: (stub, "桩原因"))
    body = client.get("/api/nn/emotion-info").json()
    assert body["available"] is True
    assert "happy" in body["labels"]
    assert "model_dimension" in body


# ------------------------------------------------------------ 真实模型冒烟

def test_真实模型识别中文情感():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    if not (em.DEFAULT_MODEL_DIR / "config.json").exists():
        pytest.skip(f"模型权重缺失：{em.DEFAULT_MODEL_DIR}")
    em.reset_engine()

    r = em.recognize("这次演练非常成功，大家都很高兴")
    assert r.status == "SUCCEEDED"
    assert r.label in em.EMOTION_LABELS
    # 强词「高兴」会走词典；这里额外验证模型路径可用
    info = em.get_emotion_info()
    assert info["model_available"] is True


def test_真实模型_无强词走极性二分类():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    if not (em.DEFAULT_MODEL_DIR / "config.json").exists():
        pytest.skip(f"模型权重缺失：{em.DEFAULT_MODEL_DIR}")
    em.reset_engine()

    engine = TransformersEmotionEngine()
    assert engine.available() is True
    r = engine.recognize("今天的天气还算可以")
    assert r.status == "SUCCEEDED"
    assert r.label in ("happy", "sad")
    assert any("二分类" in w for w in r.warnings)
