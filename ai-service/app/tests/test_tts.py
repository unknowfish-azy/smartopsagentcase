"""TTS 接口单测：Provider 探测、诚实降级、音色/文本校验与 WAV 输出。"""

import base64
import io
import json
import wave
from types import SimpleNamespace

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


class _FailingProvider(_FakeProvider):
    """探测可用但合成必失败：用于验证后端自动换下一个 Provider。"""

    name = "broken"
    display_name = "Broken TTS"

    def synthesize(self, text, preset, speed):
        raise tts_module.TtsSynthesisFailed("模拟合成失败")


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


def test_synthesize_首选失败后自动换下一个可用Provider(client, auth_headers, monkeypatch):
    """显式指定 broken 时，探测可用但合成失败，应自动由后面的 fake 兜底。"""
    from app.core.config import settings

    monkeypatch.setattr(tts_module, "_AUTO_ORDER", ("broken", "fake"))
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "broken", _FailingProvider)
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "fake", _FakeProvider)
    monkeypatch.setattr(settings, "tts_provider", "broken")
    reset_provider_cache()

    response = client.post(
        "/api/tts/synthesize", json={"text": "你好"}, headers=auth_headers()
    )

    assert response.status_code == 200
    # 实际发音的是兜底 Provider，响应头如实回传，不能让前端以为还是 broken
    assert response.headers["x-tts-provider"] == "fake"


def test_synthesize_全部Provider失败时报出各自原因(client, auth_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(tts_module, "_AUTO_ORDER", ("broken",))
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "broken", _FailingProvider)
    monkeypatch.setattr(settings, "tts_provider", "broken")
    reset_provider_cache()

    response = client.post(
        "/api/tts/synthesize", json={"text": "你好"}, headers=auth_headers()
    )

    assert response.status_code == 502
    assert "Broken TTS" in response.json()["message"]


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


def test_single_speaker_provider_不使用音色预设(client, auth_headers, fake_provider, monkeypatch):
    """piper-plus 这类单说话人 Provider 不套预设，否则 meta 会报出不属于它的音色名。"""
    from app.core.config import settings

    monkeypatch.setattr(fake_provider, "supports_presets", False)
    monkeypatch.setattr(
        settings,
        "tts_voice_presets",
        json.dumps({"sweet_girl": {"audio": "assets/tts/sweet.wav", "text": "参考原文"}}),
    )

    response = client.post(
        "/api/tts/synthesize",
        json={"text": "你好"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.headers["x-tts-voice"] == ""
    assert fake_provider.calls[0]["voice"] is None


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


class _TimingProvider(_FakeProvider):
    """带真实词级时间戳的假 Provider（模拟 Edge WordBoundary）。"""

    name = "timing"

    def __init__(self) -> None:
        super().__init__()
        self.timing = [
            {"text": "你好", "offset_ms": 0, "duration_ms": 400},
            {"text": "世界", "offset_ms": 600, "duration_ms": 500},
        ]

    def synthesize_with_timing(self, text, preset, speed):
        audio = self.synthesize(text, preset, speed)
        return audio, self.timing


@pytest.fixture
def timing_provider(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_provider", "timing")
    monkeypatch.setitem(tts_module._PROVIDER_FACTORIES, "timing", _TimingProvider)
    reset_provider_cache()
    return tts_module._provider_instance("timing")


def test_edge_timing_frame_把_word_boundary_换算成毫秒():
    frame = (
        "X-RequestId:abc\r\nContent-Type:application/json; charset=utf-8\r\n"
        "Path:audio.metadata\r\n\r\n"
        + json.dumps(
            {
                "Metadata": [
                    {
                        "Type": "WordBoundary",
                        "Data": {
                            "Offset": 12_500_000,  # 1250ms
                            "Duration": 4_000_000,  # 400ms
                            "text": {"Text": "你好", "Length": 2, "BoundaryType": "WordBoundary"},
                        },
                    },
                    {"Type": "SessionEnd", "Data": {}},
                ]
            },
            ensure_ascii=False,
        )
    )

    assert tts_module._edge_timing_frame(frame) == [
        {"text": "你好", "offset_ms": 1250, "duration_ms": 400}
    ]


def test_edge_timing_frame_忽略非元数据帧与坏_JSON():
    assert tts_module._edge_timing_frame("Path:turn.start\r\n\r\n{}") == []
    assert tts_module._edge_timing_frame("Path:audio.metadata\r\n\r\n{not json") == []


def test_synthesize_with_timing_默认回空数组_不伪造时间戳(fake_provider):
    audio, timing = fake_provider.synthesize_with_timing("你好", None, 1.0)

    assert audio[:4] == b"RIFF"
    assert timing == []


def test_synthesize_timing_true_时返回_json_含_base64_音频(
    client, auth_headers, timing_provider
):
    response = client.post(
        "/api/tts/synthesize",
        json={"text": "你好世界", "timing": True},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["media_type"] == "audio/wav"
    assert payload["provider"] == "timing"
    assert payload["timing"] == timing_provider.timing
    audio = base64.b64decode(payload["audio_base64"])
    assert audio[:4] == b"RIFF"
    # 二进制客户端不受影响：默认仍回原始音频
    assert response.headers["x-tts-provider"] == "timing"


def test_synthesize_timing_false_保持二进制音频(client, auth_headers, timing_provider):
    response = client.post(
        "/api/tts/synthesize",
        json={"text": "你好世界"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"


# ---------------------------------------------------------------- Piper-Plus


def _piper_timing(*phones):
    """按 piper_plus.TimingResult 的结构造时间戳（phone = (音素, 起, 止)）。"""
    return SimpleNamespace(
        phonemes=[
            SimpleNamespace(phoneme=name, start_ms=start, end_ms=end)
            for name, start, end in phones
        ]
    )


def test_piper_viseme_按韵母最长匹配_音调令牌不参与():
    assert tts_module._piper_viseme("aʊ") == "aa"
    assert tts_module._piper_viseme("ueɪ") == "ee"
    assert tts_module._piper_viseme("uo") == "oh"
    assert tts_module._piper_viseme("ɻ̩") == "ih"
    # 舌尖元音（次/十）与儿化元音（二）
    assert tts_module._piper_viseme("ɨ") == "ih"
    assert tts_module._piper_viseme("ɚ") == "aa"
    # 纯辅音与音调令牌都不产生口型
    assert tts_module._piper_viseme("tʂ") is None
    assert tts_module._piper_viseme("tone2") is None


def test_piper_timing_entries_按音节对齐并给出真实韵母():
    """音节以 toneN 收尾切分，每个汉字拿到自己的起止时间与韵母口型。"""
    timing = _piper_timing(
        ("n", 46.4, 60.0),
        ("i", 60.0, 110.0),
        ("tone2", 110.0, 127.7),
        ("x", 232.2, 260.0),
        ("aʊ", 260.0, 380.0),
        ("tone3", 380.0, 394.7),
    )

    entries = tts_module.piper_timing_entries("你好。", timing)

    assert entries == [
        {"text": "你", "offset_ms": 46, "duration_ms": 82, "viseme": "ih"},
        {"text": "好", "offset_ms": 232, "duration_ms": 163, "viseme": "aa"},
    ]


def test_piper_timing_entries_字母数字未被发音时只出汉字条目():
    """ASCII 数字会被 phonemizer 丢弃：宁可为无声字符跳过，也不编造时间。"""
    timing = _piper_timing(
        ("p", 0.0, 10.0),
        ("aŋ", 10.0, 40.0),
        ("tone4", 40.0, 50.0),
        ("tʂ", 50.0, 60.0),
        ("an", 60.0, 90.0),
        ("tone4", 90.0, 100.0),
        ("tɕʰ", 100.0, 110.0),
        ("y_vowel", 110.0, 140.0),
        ("tone1", 140.0, 150.0),
    )

    entries = tts_module.piper_timing_entries("泵站A区", timing)

    assert [entry["text"] for entry in entries] == ["泵", "站", "区"]
    assert [entry["offset_ms"] for entry in entries] == [0, 50, 100]


def test_piper_timing_entries_字母数字串整串对齐():
    """A-07 这类串音节数不固定：整串共用一段时间，不冒充逐字。"""
    timing = _piper_timing(
        ("f", 0.0, 10.0),
        ("u", 10.0, 60.0),
        ("tone2", 60.0, 80.0),
        ("u", 80.0, 90.0),
        ("tone4", 90.0, 110.0),
        ("tɕʰ", 110.0, 120.0),
        ("i", 120.0, 170.0),
        ("tone4", 170.0, 190.0),
        ("eɪ", 190.0, 220.0),
        ("tone1", 220.0, 240.0),
        ("t", 240.0, 250.0),
        ("ɤ", 250.0, 300.0),
        ("tone5", 300.0, 320.0),
    )

    entries = tts_module.piper_timing_entries("服务器A-07的", timing)

    assert [entry["text"] for entry in entries] == ["服", "务", "器", "A-07", "的"]
    assert entries[3] == {"text": "A-07", "offset_ms": 190, "duration_ms": 50, "viseme": "ee"}


def test_piper_timing_entries_字母数字串按字符数分配多音节():
    """一串字母数字对应多个音节时，整串时间段覆盖这些音节。"""
    timing = _piper_timing(
        ("uən", 0.0, 60.0),
        ("tone1", 60.0, 100.0),
        ("t", 100.0, 110.0),
        ("u", 110.0, 150.0),
        ("tone4", 150.0, 200.0),
        ("l", 200.0, 210.0),
        ("iŋ", 210.0, 260.0),
        ("tone2", 260.0, 300.0),
        ("tɕʰ", 300.0, 310.0),
        ("i", 310.0, 360.0),
        ("tone1", 360.0, 400.0),
        ("t", 400.0, 410.0),
        ("u", 410.0, 450.0),
        ("tone4", 450.0, 500.0),
    )

    entries = tts_module.piper_timing_entries("温度07度", timing)

    assert [entry["text"] for entry in entries] == ["温", "度", "07", "度"]
    assert entries[2] == {"text": "07", "offset_ms": 200, "duration_ms": 200, "viseme": "ih"}


def test_piper_timing_entries_无法判定哪串被发音时回空():
    """两个字母数字串只分到 1 个音节：无法判断归属，回空让前端降级。"""
    timing = _piper_timing(
        ("kʰ", 0.0, 10.0),
        ("an", 10.0, 90.0),
        ("tone4", 90.0, 100.0),
        ("eɪ", 100.0, 140.0),
        ("tone1", 140.0, 160.0),
    )

    assert tts_module.piper_timing_entries("A看B", timing) == []


def test_piper_timing_entries_无音调令牌时不猜音节():
    """英文模型不给 toneN：无法可靠切分音节，如实回空。"""
    timing = _piper_timing(("h", 0.0, 10.0), ("ə", 10.0, 30.0), ("l", 30.0, 40.0))

    assert tts_module.piper_timing_entries("hello", timing) == []


def test_read_cn_int_按十百千万亿读():
    cases = {
        0: "零",
        10: "十",
        12: "十二",
        92: "九十二",
        105: "一百零五",
        1001: "一千零一",
        10000: "一万",
        10010: "一万零一十",
        100000001: "一亿零一",
        200: "二百",
        2000: "两千",
        2001: "两千零一",
        20000: "两万",
    }

    for value, expected in cases.items():
        assert tts_module._read_cn_int(value) == expected


def test_normalize_piper_numbers_覆盖告警常见数字形态():
    """模型会丢弃 ASCII 数字：合成前必须改写成中文读法，否则数值直接漏念。"""
    normalize = tts_module._normalize_piper_numbers

    assert normalize("温度92度") == "温度九十二度"
    assert normalize("压力0.35兆帕") == "压力零点三五兆帕"
    assert normalize("编号07") == "编号零七"
    assert normalize("编号1001") == "编号一千零一"
    assert normalize("增长98%") == "增长百分之九十八"
    assert normalize("温度-5度") == "温度负五度"
    # 数量口语化：千位及以上的 2 读「两」
    assert normalize("共2000台") == "共两千台"
    assert normalize("数量200台") == "数量二百台"
    assert normalize("服务器A-07") == "服务器A-零七"
    assert normalize("地址192.168.1.1") == "地址一九二点一六八点一点一"
    assert normalize("共1,024台") == "共一千零二十四台"
    assert normalize("2026-11-17 到期") == "二零二六年十一月十七日 到期"
    # 不是日期的连字符数字（范围）逐位读，不硬套年月日
    assert normalize("范围1000-2000") == "范围一零零零-二零零零"
    # 已含中文读法的文本保持原样（幂等）
    assert normalize("温度九十二度") == "温度九十二度"


def test_normalize_piper_numbers_时刻按时分读():
    """10:30 不能逐位读成「一零:三零」：运维话术里时刻出现频率很高。"""
    normalize = tts_module._normalize_piper_numbers

    assert normalize("会议10:30开始") == "会议十点三十分开始"
    assert normalize("巡检09:05出发") == "巡检九点零五分出发"
    assert normalize("18:00 下班") == "十八点整 下班"
    assert normalize("日志时间 10:30:45") == "日志时间 十点三十分四十五秒"
    # 全角冒号同样识别
    assert normalize("23：59 截止") == "二十三点五十九分 截止"
    # 时分秒越界不算时刻：退回逐位读法，不静默丢数字
    assert normalize("比例25:70") == "比例二五:七零"


def test_normalize_piper_numbers_端口与比例不当时刻():
    """URL 端口、1:100 这类不是时刻：冒号紧邻数字时不能按「点」读。"""
    normalize = tts_module._normalize_piper_numbers

    assert normalize("http://10.0.0.1:8080") == "http://一零点零点零点一:八零八零"
    assert normalize("比例1:100") == "比例一:一零零"


def test_normalize_piper_numbers_货币与单位换算():
    """货币符号与单位后缀都要读成中文词，而不是让模型念字母。"""
    normalize = tts_module._normalize_piper_numbers

    assert normalize("金额¥5") == "金额五元"
    assert normalize("报价￥1,024") == "报价一千零二十四元"
    assert normalize("费用$12.50") == "费用十二美元五十美分"
    assert normalize("运费€30") == "运费三十欧元"
    assert normalize("费用€0.50") == "费用五十欧分"
    assert normalize("费用£5.50") == "费用五英镑五十便士"
    assert normalize("费用$0.05") == "费用五美分"
    # 人民币按元/角/分读，其他有辅币的币种按主币+辅币读
    assert normalize("金额¥5.50") == "金额五元五角"
    assert normalize("金额¥5.05") == "金额五元零五分"
    assert normalize("金额¥0.50") == "金额五角"
    assert normalize("金额¥5.00") == "金额五元"
    assert normalize("金额¥1,024.50") == "金额一千零二十四元五角"
    assert normalize("重量5kg") == "重量五公斤"
    assert normalize("包体积120MB") == "包体积一百二十兆字节"
    assert normalize("带宽100Mbps") == "带宽一百兆比特每秒"
    assert normalize("延迟30ms") == "延迟三十毫秒"
    assert normalize("超时5min") == "超时五分钟"
    assert normalize("电压220V") == "电压二百二十伏"
    assert normalize("功耗3.5kW") == "功耗三点五千瓦"
    assert normalize("温度-5℃") == "温度负五摄氏度"
    assert normalize("转速3000rpm") == "转速三千转每分钟"
    assert normalize("布线100m") == "布线一百米"
    # 像素与磁盘吞吐：单位带斜杠时整体匹配，不能只吃掉 GB 留下 /s
    assert normalize("间距5px") == "间距五像素"
    assert normalize("写入5GB/s") == "写入五吉字节每秒"
    assert normalize("读取500MB/s") == "读取五百兆字节每秒"
    # 补齐监控/硬件常见单位：长单位优先（kWh 先于 Wh、mAh 先于 mA、°C 先于 °）
    assert normalize("帧率60fps") == "帧率六十帧每秒"
    assert normalize("吞吐2000rps") == "吞吐两千请求每秒"
    assert normalize("电量5000mAh") == "电量五千毫安时"
    assert normalize("电量2.5kWh") == "电量二点五千瓦时"
    assert normalize("亮度300cd") == "亮度三百坎德拉"
    assert normalize("阻值4.7kΩ") == "阻值四点七千欧"
    assert normalize("倾角45°") == "倾角四十五度"
    assert normalize("温度25°C") == "温度二十五摄氏度"
    # 倒装单位：改成中文前置语序，不读成「五百每秒查询数」
    assert normalize("分辨率300dpi") == "分辨率每英寸三百点"
    assert normalize("吞吐500QPS") == "吞吐每秒五百次查询"
    assert normalize("磁盘1200IOPS") == "磁盘每秒一千二百次读写"
    # 带中文量级的倒装写法：量级词要保留（5000万 → 五千万）
    assert normalize("峰值5000万QPS") == "峰值每秒五千万次查询"
    assert normalize("峰值1.5万QPS") == "峰值每秒一点五万次查询"
    assert normalize("上传3亿QPS") == "上传每秒三亿次查询"
    # 带空格的写法：5000 万 QPS
    assert normalize("峰值 5000 万 QPS") == "峰值 每秒五千万次查询"
    assert normalize("峰值5000 万 QPS，已恢复") == "峰值每秒五千万次查询，已恢复"
    # 单位在前的语序：先把单位挪到数字后面再统一读，避免直接念出 QPS 三个字母
    assert normalize("QPS 5000万") == "每秒五千万次查询"
    assert normalize("QPS峰值 5000 万") == "峰值每秒五千万次查询"
    # UI / 告警文案里的真实写法：冒号、括号注释、中间夹副词
    assert normalize("QPS：5000万") == "每秒五千万次查询"
    assert normalize("QPS: 5000万") == "每秒五千万次查询"
    assert normalize("QPS（每秒查询数）5000万") == "每秒五千万次查询"
    assert normalize("QPS 已达 5000 万") == "每秒五千万次查询"
    # 未穷举在词表里的中间词与括号包裹的数字，同样不能把 QPS 留给模型念
    assert normalize("QPS高达5000万") == "每秒五千万次查询"
    assert normalize("QPS（5000万）") == "每秒五千万次查询"
    assert normalize("每秒查询数（QPS）5000万") == "每秒查询数五千万"
    assert normalize("25℃") == "二十五摄氏度"
    # 全角输入（中文文档常见）先归一化再匹配
    assert normalize("峰值５０００万ＱＰＳ") == "峰值每秒五千万次查询"
    assert normalize("图片img300dpis") == "图片img三零零dpis"


def test_normalize_piper_numbers_单位不误伤型号与版本():
    """单位识别必须带边界条件，否则型号、版本号会被读成时间/长度。"""
    normalize = tts_module._normalize_piper_numbers

    # 数字左侧在字母数字串里：A-07s 是型号，不是「零七秒」
    assert normalize("服务器A-07s") == "服务器A-零七s"
    # 单位右侧还接字母：5kgf 不整体换算，kg 后面不是边界
    assert normalize("载荷5kgf") == "载荷五kgf"
    # 版本号/多段编号不受影响
    assert normalize("v1.2.3") == "v一点二点三"


def test_piper_units_千分位与日期各算一个数字串():
    """对齐单元与数字规则保持一致：1,024 和日期都只占一个整串。"""
    assert tts_module._piper_units("共1,024台") == [
        ("cjk", "共"),
        ("run", "1,024"),
        ("cjk", "台"),
    ]
    assert tts_module._piper_units("2026-11-17") == [("run", "2026-11-17")]
    assert tts_module._piper_units("会议10:30开始") == [
        ("cjk", "会"),
        ("cjk", "议"),
        ("run", "10:30"),
        ("cjk", "开"),
        ("cjk", "始"),
    ]


def test_piper_synthesize_合成前把数字改写成中文(monkeypatch):
    """Provider 必须把改写后的文本交给模型，同时仍按原文对齐时间戳。"""
    class _FakePiperVoice:
        def __init__(self) -> None:
            self.seen: list[str] = []

        def synthesize_with_timing(self, text, length_scale=1.0):
            self.seen.append(text)
            return encode_wav([0.0] * 160, 16000), None

    voice = _FakePiperVoice()
    provider = tts_module.PiperPlusProvider()
    monkeypatch.setattr(provider, "_ensure_voice", lambda: voice)

    audio, timing = provider.synthesize_with_timing("服务器A-07温度92度", None, 1.0)

    assert voice.seen == ["服务器A-零七温度九十二度"]
    assert timing == []
    assert audio[:4] == b"RIFF"


def test_piper_probe_未配置模型时如实报原因(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_piper_model", "")
    monkeypatch.setattr(tts_module, "_module_available", lambda name: True)
    provider = tts_module.PiperPlusProvider()

    result = provider.probe()

    assert result.available is False
    assert "TTS_PIPER_MODEL" in result.reason


def test_piper_probe_模型文件不存在时如实报原因(monkeypatch, tmp_path):
    from app.core.config import settings

    missing = tmp_path / "not-there.onnx"
    monkeypatch.setattr(settings, "tts_piper_model", str(missing))
    monkeypatch.setattr(settings, "tts_piper_config", "")
    monkeypatch.setattr(tts_module, "_module_available", lambda name: True)

    result = tts_module.PiperPlusProvider().probe()

    assert result.available is False
    assert "不存在" in result.reason


class _FakePiperVoice:
    """只记录调用参数并回固定音频/时间戳的假模型。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def synthesize_with_timing(self, text, **kwargs):
        self.calls.append({"text": text, **kwargs})
        timing = _piper_timing(
            ("n", 0.0, 20.0),
            ("i", 20.0, 80.0),
            ("tone2", 80.0, 100.0),
        )
        return encode_wav([0.0] * 160, 16000), timing


def test_piper_synthesize_把语速换算成_length_scale(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_piper_model", "model.onnx")
    provider = tts_module.PiperPlusProvider()
    voice = _FakePiperVoice()
    monkeypatch.setattr(provider, "_ensure_voice", lambda: voice)

    audio, timing = provider.synthesize_with_timing("你", None, 1.25)

    assert audio[:4] == b"RIFF"
    assert voice.calls == [{"text": "你", "length_scale": 1 / 1.25}]
    assert timing == [{"text": "你", "offset_ms": 0, "duration_ms": 100, "viseme": "ih"}]


def test_ffmpeg_shared_dir_未配置时不注册(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_ffmpeg_shared_dir", "")
    monkeypatch.setattr(tts_module, "_FFMPEG_DLL_DIR_REGISTERED", "")

    assert tts_module._register_ffmpeg_shared_dlls() == ""
    assert tts_module._FFMPEG_DLL_DIR_REGISTERED == ""


def test_ffmpeg_shared_dir_目录不存在时如实报配置错误(monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_ffmpeg_shared_dir", str(tmp_path / "missing"))
    monkeypatch.setattr(tts_module, "_FFMPEG_DLL_DIR_REGISTERED", "")

    with pytest.raises(tts_module.TtsUnavailable) as failure:
        tts_module._register_ffmpeg_shared_dlls()

    assert "TTS_FFMPEG_SHARED_DIR" in str(failure.value.message)


def test_ffmpeg_shared_dir_注册后进入_PATH且只注册一次(monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tts_ffmpeg_shared_dir", str(tmp_path))
    monkeypatch.setattr(tts_module, "_FFMPEG_DLL_DIR_REGISTERED", "")
    monkeypatch.setenv("PATH", "C:\\Windows")

    first = tts_module._register_ffmpeg_shared_dlls()
    second = tts_module._register_ffmpeg_shared_dlls()

    assert first == second == str(tmp_path)
    # 目录被前置到 PATH（pydub 调 ffmpeg.exe 用），且不重复追加
    assert tts_module.os.environ["PATH"].split(tts_module.os.pathsep)[0] == str(tmp_path)
    assert tts_module.os.environ["PATH"].count(str(tmp_path)) == 1
