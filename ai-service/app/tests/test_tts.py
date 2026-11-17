"""TTS 接口单测：Provider 探测、诚实降级、音色/文本校验与 WAV 输出。"""

import io
import json
import wave

import pytest

from app.services import tts as tts_module
from app.services.tts import TtsProvider, encode_wav, reset_provider_cache


class _FakeProvider(TtsProvider):
    """可用的假 Provider：不加载任何模型，只记录调用参数。"""

    name = "fake"
    display_name = "Fake TTS"
    supports_speed = True

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    def probe(self):
        return tts_module.ProbeResult(available=True, detail={"module": "fake"})

    def synthesize(self, text, preset, speed):
        self.calls.append(
            {"text": text, "voice": preset.name if preset else None, "speed": speed}
        )
        # 0.1 秒静音（16kHz）
        return encode_wav([0.0] * 1600, 16000)


class _UnavailableProvider(TtsProvider):
    name = "missing"
    display_name = "Missing TTS"

    def probe(self):
        return tts_module.ProbeResult(available=False, reason="未安装依赖（测试桩）")

    def synthesize(self, text, preset, speed):  # pragma: no cover - 不应被调用
        raise AssertionError("不可用 Provider 不应被调用")


@pytest.fixture(autouse=True)
def reset_tts_state(monkeypatch):
    """每个用例从干净状态开始：清 Provider 缓存 + 固定默认配置。"""
    reset_provider_cache()
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_provider", "auto")
    monkeypatch.setattr(settings, "tts_max_chars", 100)
    monkeypatch.setattr(settings, "tts_timeout_sec", 5.0)
    monkeypatch.setattr(settings, "tts_voxcpm_model_dir", "")
    monkeypatch.setattr(settings, "tts_f5_model_dir", "")
    monkeypatch.setattr(settings, "tts_voice_presets", "{}")
    yield
    reset_provider_cache()


@pytest.fixture
def fake_provider(monkeypatch):
    """把假 Provider 注册为 auto 首选，并返回其唯一实例。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_provider", "fake")
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "fake", _FakeProvider)
    reset_provider_cache()
    return tts_module._provider_instance("fake")


def test_status_reports_auto_providers_without_installing_models(client, auth_headers, monkeypatch):
    """auto 模式下真实探测两个 Provider：本机未安装时如实给出原因，不是假装可用。"""
    # 固定 auto 只覆盖本轮接入的两个本地 Provider：registry 后续可能新增在线音源，
    # 那些音源的可用性依赖网络，不应影响本用例的断言。
    monkeypatch.setattr(tts_module, "_AUTO_ORDER", ("voxcpm2", "f5tts"))
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "voxcpm2", _UnavailableProvider)
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "f5tts", _UnavailableProvider)
    reset_provider_cache()

    response = client.get("/api/tts/status", headers=auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["provider"] is None
    assert "未安装依赖" in data["reason"]
    assert {item["name"] for item in data["providers"]} >= {"voxcpm2", "f5tts"}
    assert all(
        item["available"] is False
        for item in data["providers"]
        if item["name"] in {"voxcpm2", "f5tts"}
    )


def test_status_when_provider_disabled(client, auth_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_provider", "none")

    data = client.get("/api/tts/status", headers=auth_headers()).json()

    assert data["available"] is False
    assert data["provider"] is None
    assert "关闭" in data["reason"]


def test_status_requires_run_token(client):
    response = client.get("/api/tts/status")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "RUN_TOKEN_REQUIRED"


def test_synthesize_requires_run_token(client, fake_provider):
    response = client.post("/api/tts/synthesize", json={"text": "你好"})

    assert response.status_code == 401


def test_synthesize_returns_wav_and_meta(client, auth_headers, fake_provider):
    response = client.post(
        "/api/tts/synthesize",
        json={"text": "  你好，小鱼  ", "speed": 1.25},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-tts-provider"] == "fake"
    assert response.headers["x-tts-speed-applied"] == "true"
    assert response.content[:4] == b"RIFF"
    with wave.open(io.BytesIO(response.content), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == 16000
        assert reader.getnframes() == 1600
    # 文本已 trim 后传入 Provider
    assert fake_provider.calls == [{"text": "你好，小鱼", "voice": None, "speed": 1.25}]


def test_synthesize_503_when_no_provider(client, auth_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_provider", "none")

    response = client.post(
        "/api/tts/synthesize", json={"text": "你好"}, headers=auth_headers()
    )

    assert response.status_code == 503
    assert response.json()["code"] == "TTS_UNAVAILABLE"


def test_synthesize_rejects_overlong_text(client, auth_headers, fake_provider, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_max_chars", 4)

    response = client.post(
        "/api/tts/synthesize", json={"text": "一二三四五"}, headers=auth_headers()
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "TTS_TEXT_TOO_LONG"
    assert "上限 4" in payload["message"]
    assert fake_provider.calls == []


def test_synthesize_rejects_unknown_voice(client, auth_headers, fake_provider):
    response = client.post(
        "/api/tts/synthesize",
        json={"text": "你好", "voice": "nobody"},
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "TTS_VOICE_NOT_FOUND"


def test_synthesize_uses_voice_preset(client, auth_headers, fake_provider, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(
        settings,
        "tts_voice_presets",
        json.dumps({"sweet_girl": {"audio": "assets/tts/sweet.wav", "text": "参考原文"}}),
    )

    response = client.post(
        "/api/tts/synthesize",
        json={"text": "你好", "voice": "sweet_girl"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.headers["x-tts-voice"] == "sweet_girl"
    assert fake_provider.calls[0]["voice"] == "sweet_girl"


def test_single_preset_used_when_voice_omitted(client, auth_headers, fake_provider, monkeypatch):
    """只配置一条音色时自动选用：前端不必硬编码音色名（F5-TTS 也必须有参考音频）。"""
    from app.core.config import settings

    monkeypatch.setattr(
        settings,
        "tts_voice_presets",
        json.dumps({"sweet_girl": {"audio": "assets/tts/sweet.wav", "text": "参考原文"}}),
    )

    response = client.post(
        "/api/tts/synthesize", json={"text": "你好"}, headers=auth_headers()
    )

    assert response.status_code == 200
    assert fake_provider.calls[0]["voice"] == "sweet_girl"


def test_status_surfaces_invalid_preset_json(client, auth_headers, fake_provider):
    from app.core.config import settings

    settings.tts_voice_presets = "{not json"  # 故意破坏，验证不吞错
    try:
        data = client.get("/api/tts/status", headers=auth_headers()).json()
        assert "TTS_VOICE_PRESETS" in data["reason"]
        assert data["voices"] == []
    finally:
        settings.tts_voice_presets = "{}"


# ---------------------------------------------------------------- Edge 甜度档位


def test_edge_ssml_默认档位包含音高与语速偏移():
    """甜度档位默认值：音高 +18Hz（约两个半音）、语速 +10%（轻快不急促）。"""
    ssml = tts_module.build_edge_ssml("你好呀", voice="zh-CN-XiaoyiNeural")

    assert "pitch='+18Hz'" in ssml
    assert "rate='+10%'" in ssml
    assert "zh-CN-XiaoyiNeural" in ssml
    # 默认不开情感风格：并非所有音色都支持，强加会被服务端拒绝
    assert "mstts:express-as" not in ssml


def test_edge_ssml_语速参数与甜度档位叠加():
    """调用方显式放慢/加快时，甜度语速偏移仍叠加，而不是被覆盖。"""
    slow = tts_module.build_edge_ssml(
        "好", voice="v", speed=0.8, pitch_hz=10, rate_percent=4
    )
    fast = tts_module.build_edge_ssml("好", voice="v", speed=1.2)

    assert "pitch='+10Hz'" in slow
    assert "rate='-16%'" in slow  # -20 + 4
    assert "rate='+30%'" in fast  # +20 + 10


def test_edge_ssml_风格仅在合法标识符时启用_防止SSML注入():
    """style 会被拼进 SSML：只接受简单标识符，其余一律忽略而非原样透传。"""
    ok = tts_module.build_edge_ssml("好", voice="v", style="cheerful")
    assert "<mstts:express-as style='cheerful'>" in ok
    assert "xmlns:mstts=" in ok

    injected = tts_module.build_edge_ssml("好", voice="v", style="'/><script>alert(1)</script>")
    assert "script" not in injected
    assert "alert" not in injected


def test_edge_ssml_文本转义避免破坏文档结构():
    ssml = tts_module.build_edge_ssml("a<b & c>d", voice="v")

    assert "a&lt;b &amp; c&gt;d" in ssml
    assert "<b" not in ssml


def test_synthesize_503_on_invalid_preset_json(client, auth_headers, fake_provider):
    from app.core.config import settings

    settings.tts_voice_presets = "{not json"
    try:
        response = client.post(
            "/api/tts/synthesize", json={"text": "你好"}, headers=auth_headers()
        )
        assert response.status_code == 503
        assert response.json()["code"] == "TTS_CONFIG_INVALID"
    finally:
        settings.tts_voice_presets = "{}"


def test_encode_wav_clips_out_of_range_samples():
    audio = encode_wav([2.0, -2.0, 0.0], 8000)

    with wave.open(io.BytesIO(audio), "rb") as reader:
        frames = reader.readframes(reader.getnframes())

    # 溢出被钳制到 ±32767，而不是回绕成噪声
    assert frames[:2] == b"\xff\x7f"
    assert frames[2:4] == b"\x01\x80"
    assert frames[4:6] == b"\x00\x00"


def test_auto_prefers_first_available_provider(monkeypatch):
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "voxcpm2", _UnavailableProvider)
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "f5tts", _FakeProvider)
    reset_provider_cache()

    assert tts_module.TtsService().status()["provider"] == "f5tts"
