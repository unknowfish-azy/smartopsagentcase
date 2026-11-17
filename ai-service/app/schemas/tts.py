from typing import Any

from pydantic import BaseModel, Field, field_validator


class TtsSynthesizeRequest(BaseModel):

    """合成请求：文本必填，音色/语速可选。

    文本长度上限由服务端配置（TTS_MAX_CHARS）动态校验，这里不写死 max_length，
    以便超长时返回带具体上限的 400，而不是笼统的 422。
    """

    text: str = Field(min_length=1)

    voice: str | None = None

    speed: float = Field(default=1.0, ge=0.5, le=2.0)

    # 需要词级时间戳（口型对齐）时置 true：响应改为 JSON（含 base64 音频 + timing），
    # 默认 false 保持二进制音频直传，不改变既有调用方
    timing: bool = False

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, value):

        if not isinstance(value, str):

            raise ValueError("text 必须是字符串")

        return value.strip()

    @field_validator("voice", mode="before")
    @classmethod
    def _normalize_voice(cls, value):

        if value is None:

            return None

        text = str(value).strip()

        return text or None


class TtsTimingWord(BaseModel):

    """一个词/字在音频里的起止时间（毫秒），来自 Provider 的真实边界事件。"""

    text: str

    offset_ms: int = Field(ge=0)

    duration_ms: int = Field(gt=0)

    # 可选：Provider 能给出真实韵母时回传五元音之一（aa/ih/ou/ee/oh）。
    # 有该字段说明是音素级对齐；缺省表示只有词/字边界，口型由前端近似映射。
    viseme: str | None = None


class TtsSynthesizeTimedResponse(BaseModel):

    """请求 timing=true 时的响应：base64 音频 + 词级时间戳。

    timing 为空数组表示该 Provider 不提供边界事件（不是对齐失败），
    前端必须如实降级为近似口型，不能假装精确。
    """

    audio_base64: str

    media_type: str

    provider: str

    voice: str = ""

    speed_applied: bool = False

    timing: list[TtsTimingWord] = Field(default_factory=list)


class TtsProviderStatus(BaseModel):

    name: str

    display_name: str

    available: bool

    reason: str = ""

    detail: dict[str, Any] = Field(default_factory=dict)


class TtsVoiceStatus(BaseModel):

    name: str

    description: str = ""

    has_reference: bool = False


class TtsStatusResponse(BaseModel):

    """TTS 真实可用性：available=false 时 reason 写明原因，前端据此回落浏览器语音。"""

    requested: str

    provider: str | None = None

    available: bool

    reason: str = ""

    providers: list[TtsProviderStatus] = Field(default_factory=list)

    voices: list[TtsVoiceStatus] = Field(default_factory=list)

    """
    后台预热状态（仅本地模型 f5tts/voxcpm2 有值；在线音源 probe 已测通无需预热）。
    state: idle/running/done/failed —— running 时前端可显示"正在加载语音模型..."
    elapsed: 运行中为已耗时，完成后为总耗时，idle 时为 null
    error: 失败时的原因，空字符串表示成功或进行中
    """
    preheat: dict[str, Any] | None = None
