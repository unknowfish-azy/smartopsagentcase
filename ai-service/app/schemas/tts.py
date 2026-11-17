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
