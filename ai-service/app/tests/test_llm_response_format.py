"""DS-04 回归：response_format 透传 + 未传时行为与旧版等价。

llm.py 是本批唯一有风险的改动点，这里用纯函数断言守住等价性，不依赖网络与模型。
"""

import json

from app.services.decision_schema import DECISION_SCHEMA
from app.services.llm import LLMService


def test_ollama_payload_unchanged_when_response_format_absent():
    legacy = LLMService._payload("p", "s", stream=False, model="m")
    explicit_none = LLMService._payload(
        "p", "s", stream=False, model="m", response_format=None
    )
    assert "format" not in legacy
    assert explicit_none == legacy


def test_ollama_payload_carries_format_when_given():
    payload = LLMService._payload(
        "p", "s", stream=False, model="m", response_format=DECISION_SCHEMA
    )
    assert payload["format"] == DECISION_SCHEMA


def test_openai_payload_unchanged_when_response_format_absent():
    legacy = LLMService._openai_payload("p", "s", stream=False, model="m")
    explicit_none = LLMService._openai_payload(
        "p", "s", stream=False, model="m", response_format=None
    )
    assert "response_format" not in legacy
    assert explicit_none == legacy


def test_openai_payload_passes_response_format():
    payload = LLMService._openai_payload(
        "p", "s", stream=False, model="m", response_format=DECISION_SCHEMA
    )
    assert payload["response_format"] == DECISION_SCHEMA


def test_mock_returns_schema_compliant_json():
    raw = LLMService._mock_generate("q", response_format=DECISION_SCHEMA)
    data = json.loads(raw)
    assert set(DECISION_SCHEMA["required"]) <= set(data)
    assert data["verdict"] in DECISION_SCHEMA["properties"]["verdict"]["enum"]
    assert set(data["next_probe"]) >= {"decision", "reason"}


def test_mock_keeps_legacy_text_without_schema():
    assert "模拟回答" in LLMService._mock_generate("问题")


def test_mock_only_echoes_user_question_not_prompt_scaffold():
    """mock 不能把提示词模板当回答：桌宠会逐句念出来（浏览器联调已复现）。"""
    prompt = (
        "请回答下面的用户问题。\n\n"
        "要求：\n- 优先使用知识库证据。\n\n"
        "知识库证据：\n当前没有检索到可用知识证据。\n\n"
        "用户问题：\n<user_input>\n你好，介绍一下你自己\n</user_input>"
    )
    text = LLMService._mock_generate(prompt)
    assert "你问的是：你好，介绍一下你自己" in text
    for scaffold in ("要求：", "知识库证据：", "<user_input>", "优先使用知识库证据"):
        assert scaffold not in text


def test_mock_question_falls_back_to_question_marker():
    text = LLMService._mock_generate("上下文\n\n用户问题：集群为什么变慢")
    assert "集群为什么变慢" in text
    assert "上下文" not in text
