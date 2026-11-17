"""TTS 统一服务：VoxCPM2 / F5-TTS 可插拔 Provider + 运行时探测 + 诚实降级。

红线（与 agent/tools/speech.py 的 ASR 约定一致）：
- 依赖未安装、权重缺失、模型加载失败时，探测结果给出**具体原因**，
  合成接口返回 503，绝不返回占位音频、也绝不静默换成别的音色或别的 Provider。
- Provider 的重依赖（torch / voxcpm / f5_tts）只在真正合成时导入，
  探测只用 ``importlib.util.find_spec``，不触发大模块加载。

音频编码只用标准库 ``wave`` + ``array``：Provider 返回 [-1, 1] 浮点采样，
这里统一编码成 16-bit 单声道 PCM WAV，因此不额外引入 soundfile 依赖。
"""

from __future__ import annotations

import array
import asyncio
import importlib.util
import io
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.config import settings
from ..core.exceptions import AIServiceException

_REPO_ROOT = Path(__file__).resolve().parents[3]

# 推理 Provider 的注册表。测试通过替换它注入假 Provider。
_PROVIDER_FACTORIES: dict[str, type["TtsProvider"]] = {}

# Provider 实例进程级缓存：模型加载代价高，跨请求复用同一个实例。
_PROVIDER_INSTANCES: dict[str, "TtsProvider"] = {}

# auto 模式下的优选顺序：F5-TTS（有参考音频时最像目标声线，1.9GB 显存、热态 3s）
# → Edge 神经语音（无需本地权重，最甜）→ 百度在线音源兜底。
# VoxCPM2 排在最后：实测默认音色是男声、热态 31s、峰值 5.3GB，且在本机 Python 3.14 +
# torch 2.14 上约半数加载会 0xC0000005 崩进程，只能由 TTS_PROVIDER=voxcpm2 显式启用。
# piper-plus 排最末：音色固定、以"音素级时间戳"见长，建议按需显式启用，
# 不抢占现有默认音色（Edge / F5-TTS 的听感更贴合桌宠形象）。
# edge/baidu 的 probe 都是实测 + 10 分钟缓存，不可用会被跳过。
_AUTO_ORDER = ("f5tts", "edge", "baidu", "voxcpm2", "piperplus")


class TtsUnavailable(AIServiceException):
    """没有可用的 TTS 能力：503 + 明确原因，调用方据此回落浏览器语音。"""

    def __init__(self, message: str, code: str = "TTS_UNAVAILABLE"):
        super().__init__(message, code=code, http_status=503)


class TtsConfigInvalid(TtsUnavailable):
    def __init__(self, message: str):
        super().__init__(message, code="TTS_CONFIG_INVALID")


class TtsRequestInvalid(AIServiceException):
    """请求本身不合法（文本过长 / 音色不存在）：400。"""

    def __init__(self, message: str, code: str = "TTS_INVALID_REQUEST"):
        super().__init__(message, code=code, http_status=400)


class TtsSynthesisFailed(AIServiceException):
    """模型可用但本次合成失败：502，附带真实错误摘要。"""

    def __init__(self, message: str):
        super().__init__(message, code="TTS_SYNTHESIS_FAILED", http_status=502)


@dataclass(frozen=True)
class VoicePreset:
    """音色预设：参考音频 + 其转写文本（VoxCPM2 音色克隆 / F5-TTS 参考声线共用）。"""

    name: str
    audio: str = ""
    text: str = ""
    description: str = ""

    def audio_path(self) -> Path | None:
        """参考音频的绝对路径；未配置或文件不存在时返回 None（由 Provider 如实报错）。"""
        if not self.audio.strip():
            return None
        path = Path(self.audio.strip())
        return path if path.is_absolute() else _REPO_ROOT / path


@dataclass
class ProbeResult:
    available: bool
    reason: str = ""
    detail: dict[str, Any] | None = None


def _module_available(module_name: str) -> bool:
    """只查模块是否可导入，不执行模块顶层代码（避免加载 torch）。"""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def load_voice_presets(raw: str | None = None) -> dict[str, VoicePreset]:
    """解析 TTS_VOICE_PRESETS（JSON 对象）。格式错误时抛 TtsConfigInvalid，不静默忽略。"""
    content = settings.tts_voice_presets if raw is None else raw
    try:
        parsed = json.loads(content) if content and content.strip() else {}
    except json.JSONDecodeError as exc:
        raise TtsConfigInvalid(
            f"TTS_VOICE_PRESETS 不是合法 JSON（第 {exc.lineno} 行第 {exc.colno} 列）：{exc.msg}"
        ) from None
    if not isinstance(parsed, dict):
        raise TtsConfigInvalid("TTS_VOICE_PRESETS 必须是 JSON 对象：音色名 → {audio,text,description}")

    presets: dict[str, VoicePreset] = {}
    for name, value in parsed.items():
        if isinstance(value, str):
            presets[str(name)] = VoicePreset(name=str(name), audio=value)
        elif isinstance(value, dict):
            presets[str(name)] = VoicePreset(
                name=str(name),
                audio=str(value.get("audio") or ""),
                text=str(value.get("text") or ""),
                description=str(value.get("description") or ""),
            )
        else:
            raise TtsConfigInvalid(f"TTS_VOICE_PRESETS.{name} 必须是字符串路径或对象")
    return presets


def encode_wav(samples: Any, sample_rate: int) -> bytes:
    """把 [-1, 1] 浮点采样编码成 16-bit 单声道 PCM WAV（仅标准库）。"""
    rate = int(sample_rate)
    if rate <= 0:
        raise ValueError(f"非法采样率：{sample_rate}")
    pcm = array.array("h", (int(max(-1.0, min(1.0, float(sample))) * 32767) for sample in samples))
    if sys.byteorder == "big":  # WAV 固定小端
        pcm.byteswap()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _resolve_device() -> str | None:
    """解析 tts_device。auto 时探测 torch+CUDA；返回 None 表示交给 Provider 自己决定。"""
    configured = (settings.tts_device or "auto").strip().lower()
    if configured in {"cuda", "cpu"}:
        return configured
    if configured not in {"", "auto"}:
        raise TtsConfigInvalid(f"不支持的 TTS_DEVICE: {configured}（可选 auto/cuda/cpu）")
    try:
        import torch  # noqa: PLC0415 - 只在需要选设备时导入

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001 - torch 缺失/损坏时退回 CPU 语义
        return None


class TtsProvider:
    """Provider 基类：探测（便宜）+ 懒加载合成（昂贵）。"""

    name = ""
    display_name = ""
    # 是否支持语速参数；不支持的 Provider 必须如实回报 speed_applied=false
    supports_speed = False
    # 合成结果的真实媒体类型：本地模型输出 WAV，在线音源直接回 MP3，不做转码
    media_type = "audio/wav"
    # 是否吃 TTS_VOICE_PRESETS 里的参考音频；单说话人模型（piper-plus）为 False，
    # 否则会把不属于它的预设名（如 xiaoyu）写进 meta，前端显示的"音色"就是假的
    supports_presets = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._load_error = ""

    def probe(self) -> ProbeResult:
        raise NotImplementedError

    def synthesize(self, text: str, preset: VoicePreset | None, speed: float) -> bytes:
        raise NotImplementedError

    def synthesize_with_timing(
        self, text: str, preset: VoicePreset | None, speed: float
    ) -> tuple[bytes, list[dict[str, Any]]]:
        """合成音频 + 词级时间戳（毫秒）。

        默认实现没有时间戳，如实回空数组：前端据此降级到"按字数匀速推断"的近似口型，
        绝不拿估算值冒充真实音素对齐。只有真正收到边界事件的 Provider 才覆盖本方法。
        """
        return self.synthesize(text, preset, speed), []

    def _failed(self, reason: str, detail: dict[str, Any] | None = None) -> ProbeResult:
        return ProbeResult(available=False, reason=reason, detail=detail or {})


class VoxCpm2Provider(TtsProvider):
    """VoxCPM2（``voxcpm`` 包）零样本 TTS：可选参考音频做音色克隆。"""

    name = "voxcpm2"
    display_name = "VoxCPM2"
    supports_speed = False
    _MODULE = "voxcpm"

    def probe(self) -> ProbeResult:
        detail = {
            "module": self._MODULE,
            "model_dir": settings.tts_voxcpm_model_dir,
            "loaded": self._loaded,
        }
        if not _module_available(self._MODULE):
            return self._failed(
                "未安装 voxcpm 依赖：pip install voxcpm（需 torch，约 2GB+ 显存占用）",
                detail,
            )
        if self._load_error:
            return self._failed(f"模型加载失败：{self._load_error}", detail)
        model_dir = settings.tts_voxcpm_model_dir.strip()
        if not model_dir:
            return self._failed(
                "未配置 TTS_VOXCPM_MODEL_DIR（本地权重目录或 HuggingFace 仓库 id）", detail
            )
        # 形如本地路径（含盘符/分隔符）时核验目录存在；HF 仓库 id 交给加载阶段校验
        if ("/" in model_dir or "\\" in model_dir or ":" in model_dir) and not Path(model_dir).exists():
            return self._failed(f"VoxCPM2 权重目录不存在：{model_dir}", detail)
        return ProbeResult(available=True, detail=detail)

    def synthesize(self, text: str, preset: VoicePreset | None, speed: float) -> bytes:
        model = self._ensure_model()
        kwargs: dict[str, Any] = {"text": text}
        if preset is not None:
            audio_path = preset.audio_path()
            if audio_path is None or not audio_path.is_file():
                raise TtsSynthesisFailed(
                    f"音色「{preset.name}」的参考音频不存在：{preset.audio or '（未配置）'}"
                )
            # VoxCPM2 的两条克隆路径（见 voxcpm.core.VoxCPM._generate）：
            # prompt_wav_path 必须与 prompt_text 同时给（续写式），只给音频会被上游
            # 以 ValueError 拒绝；没有转写文本时走 reference_wav_path 纯音色克隆。
            if preset.text.strip():
                kwargs["prompt_wav_path"] = str(audio_path)
                kwargs["prompt_text"] = preset.text.strip()
            else:
                kwargs["reference_wav_path"] = str(audio_path)
        try:
            wav = model.generate(**kwargs)
        except TypeError as exc:
            # 上游 API 变更时给出可排查的信息，而不是返回空音频
            raise TtsSynthesisFailed(f"voxcpm.generate 调用签名不匹配：{exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise TtsSynthesisFailed(f"VoxCPM2 合成失败：{exc}") from exc
        if wav is None or len(wav) == 0:
            raise TtsSynthesisFailed("VoxCPM2 返回空音频")
        return encode_wav(wav, self._sample_rate(model))

    @staticmethod
    def _sample_rate(model: Any) -> int:
        """采样率由 AudioVAE 决定（不是固定 16kHz），必须从已加载的模型读。"""
        rate = getattr(getattr(model, "tts_model", None), "sample_rate", None)
        try:
            rate = int(rate)
        except (TypeError, ValueError):
            raise TtsSynthesisFailed(
                f"无法从 VoxCPM2 模型读取采样率（sample_rate={rate!r}），拒绝输出错误音高的音频"
            ) from None
        if rate <= 0:
            raise TtsSynthesisFailed(f"VoxCPM2 返回非法采样率：{rate}")
        return rate

    def _ensure_model(self):
        with self._lock:
            if self._instance is not None:
                return self._instance
            try:
                from voxcpm import VoxCPM  # noqa: PLC0415 - 重依赖懒加载
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise TtsUnavailable(f"voxcpm 依赖导入失败：{exc}") from exc
            # 不加载去噪器：本服务从不传 denoise=True，而 ZipEnhancer 会额外拉
            # funasr/modelscope 权重并常驻显存，对干净参考音频没有收益。
            # 也不开 optimize(True 会 torch.compile + 预热)：本机 torch 2.14/cu126 +
            # Python 3.14 上实测直接 0xC0000005 访问违例崩进程，异常无法捕获。
            kwargs: dict[str, Any] = {"load_denoiser": False, "optimize": False}
            device = _resolve_device()
            if device:
                kwargs["device"] = device
            try:
                model = VoxCPM.from_pretrained(
                    settings.tts_voxcpm_model_dir.strip(), **kwargs
                )
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise TtsUnavailable(f"VoxCPM2 权重加载失败：{exc}") from exc
            self._instance = model
            self._loaded = True
            return model

    _instance: Any = None


_F5_WEIGHT_SUFFIXES = (".safetensors", ".pt", ".pth")


def _resolve_f5_ckpt(raw: str) -> str:
    """把 TTS_F5_MODEL_DIR 解析成 F5TTS(ckpt_file=...) 需要的那**一个权重文件**。

    F5TTS 的 ckpt_file 参数收的是文件路径，直接传目录会在 load_checkpoint 里按后缀
    判断成败；目录里有多份权重时也无法猜，只能如实报错而不是随便挑一个（挑错即换模型）。
    留空表示用上游默认（HF 上的 F5TTS_v1_Base）。
    """
    if not raw:
        return ""
    path = Path(raw)
    if path.is_file():
        return str(path)
    if not path.is_dir():
        raise TtsConfigInvalid(f"TTS_F5_MODEL_DIR 不存在：{raw}")
    candidates = sorted(
        item for item in path.iterdir()
        if item.is_file() and item.suffix.lower() in _F5_WEIGHT_SUFFIXES
    )
    if not candidates:
        raise TtsConfigInvalid(
            f"TTS_F5_MODEL_DIR 目录里没有权重文件（{', '.join(_F5_WEIGHT_SUFFIXES)}）：{raw}"
        )
    if len(candidates) > 1:
        names = "、".join(item.name for item in candidates)
        raise TtsConfigInvalid(
            f"TTS_F5_MODEL_DIR 目录里有多个权重文件，无法确定用哪一个：{names}；请把配置指向具体文件"
        )
    return str(candidates[0])


class F5TtsProvider(TtsProvider):
    """F5-TTS（``f5_tts.api.F5TTS``）：必须提供参考音频，按参考声线合成。"""

    name = "f5tts"
    display_name = "F5-TTS"
    supports_speed = True
    _MODULE = "f5_tts.api"

    def probe(self) -> ProbeResult:
        detail = {
            "module": self._MODULE,
            "model_dir": settings.tts_f5_model_dir,
            "loaded": self._loaded,
        }
        if not _module_available(self._MODULE):
            return self._failed("未安装 f5-tts 依赖：pip install f5-tts", detail)
        if self._load_error:
            return self._failed(f"模型加载失败：{self._load_error}", detail)
        try:
            presets = load_voice_presets()
        except TtsConfigInvalid as exc:
            return self._failed(str(exc.message), detail)
        usable = [
            preset for preset in presets.values()
            if preset.audio_path() is not None and preset.audio_path().is_file()
        ]
        if not usable:
            return self._failed(
                "F5-TTS 需要参考音频：在 TTS_VOICE_PRESETS 里至少配置一条存在的 audio", detail
            )
        detail["voices"] = [preset.name for preset in usable]
        return ProbeResult(available=True, detail=detail)

    def synthesize(self, text: str, preset: VoicePreset | None, speed: float) -> bytes:
        if preset is None:
            raise TtsUnavailable(
                "F5-TTS 必须指定音色预设（voice）：请从 /api/tts/status 的 voices 里选择"
            )
        audio_path = preset.audio_path()
        if audio_path is None or not audio_path.is_file():
            raise TtsSynthesisFailed(
                f"音色「{preset.name}」的参考音频不存在：{preset.audio or '（未配置）'}"
            )
        # F5 的 ref_text 为空时会自动跑 Whisper 转写（f5_tts.infer.utils_infer.
        # preprocess_ref_audio_text → transcribe），等于额外下载并常驻一个 ASR 模型。
        # 这里要求显式转写文本，避免一次播报偷偷拉起几百 MB 的权重。
        ref_text = preset.text.strip()
        if not ref_text:
            raise TtsConfigInvalid(
                f"音色「{preset.name}」缺少 text：F5-TTS 需要参考音频的逐字转写文本，"
                "请在 TTS_VOICE_PRESETS 里补上该音频对应的原文"
            )
        engine = self._ensure_engine()
        try:
            wav, sample_rate, _spectrogram = engine.infer(
                ref_file=str(audio_path),
                ref_text=ref_text,
                gen_text=text,
                speed=float(speed),
            )
        except TypeError as exc:
            raise TtsSynthesisFailed(f"F5TTS.infer 调用签名不匹配：{exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise TtsSynthesisFailed(f"F5-TTS 合成失败：{exc}") from exc
        if wav is None:
            # infer_process 在文本分块为空时返回 (None, rate, None)
            raise TtsSynthesisFailed("F5-TTS 没有生成任何音频批次（gen_text 分块为空）")
        samples = wav.detach().cpu().numpy().tolist() if hasattr(wav, "detach") else list(wav)
        if not samples:
            raise TtsSynthesisFailed("F5-TTS 返回空音频")
        return encode_wav(samples, int(sample_rate))

    def _ensure_engine(self):
        with self._lock:
            if self._engine is not None:
                return self._engine
            try:
                from f5_tts.api import F5TTS  # noqa: PLC0415 - 重依赖懒加载
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise TtsUnavailable(f"f5-tts 依赖导入失败：{exc}") from exc
            kwargs: dict[str, Any] = {}
            ckpt = _resolve_f5_ckpt(settings.tts_f5_model_dir.strip())
            if ckpt:
                kwargs["ckpt_file"] = ckpt
            vocoder_dir = settings.tts_f5_vocoder_dir.strip()
            if vocoder_dir:
                path = Path(vocoder_dir)
                missing = [
                    name for name in ("config.yaml", "pytorch_model.bin")
                    if not (path / name).is_file()
                ]
                if missing:
                    raise TtsConfigInvalid(
                        f"TTS_F5_VOCODER_DIR 缺少 {'、'.join(missing)}：{vocoder_dir}"
                    )
                kwargs["vocoder_local_path"] = str(path)
            device = _resolve_device()
            if device:
                kwargs["device"] = device
            try:
                engine = F5TTS(**kwargs)
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise TtsUnavailable(f"F5-TTS 权重加载失败：{exc}") from exc
            self._engine = engine
            self._loaded = True
            return engine

    _engine: Any = None


def _run_async_blocking(factory: Any, timeout: float = 30.0) -> Any:
    """同步执行一次性 async 逻辑（Edge 的 WebSocket 握手/合成）。

    ``asyncio.run`` 在已有运行中事件循环时（例如 synthesize 里的 provider 选择）会直接抛
    RuntimeError 并留下未 await 的 coroutine。这里检测到运行中的 loop 就换一条线程执行，
    两条路径都保证 coroutine 一定被消费。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = asyncio.run(factory())
        except BaseException as exc:  # noqa: BLE001 - 原样抛回调用线程
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("在线语音请求超时")
    if "error" in box:
        raise box["error"]
    return box.get("value")


_EDGE_TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"

# mstts:express-as 的 style 只接受简单的标识符；其它字符（引号/尖括号）会被拼进
# SSML 导致整条请求被拒，因此不合法时直接关掉风格，而不是原样透传。
_EDGE_STYLE_RE = re.compile(r"^[A-Za-z][A-Za-z-]{0,31}$")


def build_edge_ssml(
    text: str,
    *,
    voice: str,
    speed: float = 1.0,
    pitch_hz: int | None = None,
    rate_percent: int | None = None,
    style: str | None = None,
) -> str:
    """构造 Edge 朗读 SSML：甜度档位（音高上抬 + 语速偏移）+ 可选情感风格。

    甜度只作用于听感参数，不改变音色本身：音高上抬是"少女音"最有效的维度，
    语速轻快是"活泼"，风格（若音色支持）再补一层情绪。三档默认全部取
    settings，所以改 .env 就能调档，不需要改代码或调用方。
    """
    if pitch_hz is None:
        pitch_hz = settings.tts_edge_pitch_hz
    if rate_percent is None:
        rate_percent = settings.tts_edge_rate_percent
    if style is None:
        style = settings.tts_edge_style
    rate = round((float(speed or 1.0) - 1.0) * 100) + int(rate_percent)
    inner = (
        f"<prosody pitch='{int(pitch_hz):+d}Hz' rate='{rate:+d}%'>"
        f"{_escape_ssml(text)}</prosody>"
    )
    style_name = (style or "").strip()
    if _EDGE_STYLE_RE.match(style_name):
        inner = f"<mstts:express-as style='{style_name}'>{inner}</mstts:express-as>"
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        "xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='zh-CN'>"
        f"<voice name='{voice}'>{inner}</voice></speak>"
    )


def _edge_sec_ms_gec() -> str:
    """Edge 朗读服务的签名 token。

    2025 年下半年起服务端把 v1（"5 分钟对齐时间戳 + 令牌"的裸 SHA256）换成了
    v2：``<16 位 CS64>-<64 位 SHA256>`` 复合摘要，旧算法一律 403（实测如此）。
    该摘要实现约 150 行位运算且会随服务端策略调整，这里直接复用官方 edge-tts 的
    ``drm.generate_sec_ms_gec``，不在本项目里重复实现与维护。
    """
    from edge_tts.drm import DRM  # noqa: PLC0415 - 可选依赖
    return DRM.generate_sec_ms_gec()


class BaiduTtsProvider(TtsProvider):
    """百度在线朗读音源：HTTP GET 直接返回 MP3，无需 Key、无需本地权重。

    音色是固定的中文女声（年轻偏暖），比 Windows 本地音色（慧慧/瑶瑶）明显更「少女」；
    音高不可调，只能通过 spd 映射语速。探测会真的合成一个单字并缓存 10 分钟，
    这样 status 里报的可用性是实测结果而不是"应该能用"。
    """

    name = "baidu"
    display_name = "百度在线语音"
    supports_speed = True
    media_type = "audio/mpeg"
    _ENDPOINT = "https://fanyi.baidu.com/gettts"
    _PROBE_TTL = 600.0
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        super().__init__()
        self._probe_at = 0.0
        self._probe_result: ProbeResult | None = None

    def _fetch(self, text: str, spd: int) -> bytes:
        query = urllib.parse.urlencode(
            {"lan": "zh", "text": text, "spd": str(spd), "source": "web"}
        )
        request = urllib.request.Request(
            f"{self._ENDPOINT}?{query}",
            headers={"User-Agent": self._UA, "Referer": "https://fanyi.baidu.com/"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - 固定 https 端点
            return response.read()

    def probe(self) -> ProbeResult:
        now = time.monotonic()
        if self._probe_result is not None and now - self._probe_at < self._PROBE_TTL:
            return self._probe_result
        detail = {"endpoint": self._ENDPOINT}
        try:
            audio = self._fetch("好", 5)
        except Exception as exc:  # noqa: BLE001 - 网络异常只影响可用性判定
            self._probe_result = self._failed(f"百度在线语音不可达：{exc}", detail)
        else:
            self._probe_result = (
                ProbeResult(available=True, detail=detail)
                if audio
                else self._failed("百度在线语音返回空音频", detail)
            )
        self._probe_at = now
        return self._probe_result

    def synthesize(self, text: str, preset: VoicePreset | None, speed: float) -> bytes:
        # spd: 1~15，5 为正常语速
        spd = max(1, min(15, round(5 * float(speed or 1.0))))
        try:
            # 该接口把文本放在 query string 里，300 字直接拼会超长被拒，
            # 按标点切成 ≤120 字的小段逐段合成再拼 MP3（同编码同采样率，拼接可直接播）
            audio = b"".join(self._fetch(chunk, spd) for chunk in _split_for_online_tts(text))
        except Exception as exc:  # noqa: BLE001
            raise TtsSynthesisFailed(f"百度在线语音合成失败：{exc}") from exc
        if not audio:
            raise TtsSynthesisFailed("百度在线语音返回空音频")
        return audio


class EdgeTtsProvider(TtsProvider):
    """Edge 朗读服务（微软神经语音）：XiaoyiNeural 是目前最贴近「活泼少女」的免费音色。

    协议：WebSocket 先发 speech.config，再发 SSML；服务端回二进制音频帧 + ``Path:turn.end``。
    该端点会按来源 IP 做区域拦截（本机实测握手 403），所以 probe 做一次真实握手探测并
    缓存 10 分钟：不可用时 auto 模式直接跳到下一个 Provider，绝不假装能播。
    """

    name = "edge"
    display_name = "Edge 神经语音"
    supports_speed = True
    media_type = "audio/mpeg"
    _MODULE = "edge_tts"
    # 微软会周期性抬高门槛：版本串过旧会被握手直接 403（实测 130.0.2849.68 已失效，
    # 143.0.3650.75 可用）。版本号走 settings，升级只需改 .env 而不必改代码。
    _SEC_VERSION_PREFIX = "2-"
    _WS = "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
    _ORIGIN = "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold"
    _PROBE_TTL = 600.0

    def __init__(self) -> None:
        super().__init__()
        self._probe_at = 0.0
        self._probe_result: ProbeResult | None = None

    @property
    def _chromium(self) -> str:
        return (settings.tts_edge_version or "143.0.3650.75").strip()

    @property
    def _sec_version(self) -> str:
        """签名版本串（形如 2-143.0.3650.75）：装了 edge-tts 就以它的常量为准。"""
        try:
            from edge_tts.constants import SEC_MS_GEC_VERSION  # noqa: PLC0415

            if SEC_MS_GEC_VERSION:
                return SEC_MS_GEC_VERSION
        except Exception:  # noqa: BLE001 - 未安装时回落到配置
            pass
        return f"{self._SEC_VERSION_PREFIX}{self._chromium}"

    def _url(self) -> str:
        return (
            f"{self._WS}?TrustedClientToken={_EDGE_TRUSTED_CLIENT_TOKEN}"
            f"&Sec-MS-GEC={_edge_sec_ms_gec()}"
            f"&Sec-MS-GEC-Version={self._sec_version}"
        )

    def _headers(self) -> dict[str, str]:
        major = self._chromium.split(".")[0]
        return {
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Origin": self._ORIGIN,
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{self._chromium} Safari/537.36 Edg/{self._chromium}"
            ),
            "Sec-CH-UA": f'"Chromium";v="{major}", "Not_A Brand";v="24", "Microsoft Edge";v="{major}"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            # 服务端会校验 muid cookie：缺失同样是 403（与签名 v2 同批加的校验）
            "Cookie": f"muid={uuid.uuid4().hex.upper()};",
        }

    @staticmethod
    async def _connect(url: str, headers: dict[str, str]):
        import websockets  # noqa: PLC0415 - 可选依赖，缺失时由 probe 如实报告

        kwargs: dict[str, Any] = {"max_size": None, "open_timeout": 15}
        try:
            return await websockets.connect(url, additional_headers=headers, **kwargs)
        except TypeError:  # websockets < 13 用的是 extra_headers
            return await websockets.connect(url, extra_headers=headers, **kwargs)

    async def _probe_async(self) -> None:
        connection = await self._connect(self._url(), self._headers())
        await connection.close()

    async def _synthesize_async(
        self, text: str, speed: float
    ) -> tuple[bytes, list[dict[str, Any]]]:
        voice = (settings.tts_edge_voice or "zh-CN-XiaoyiNeural").strip()
        stamp = time.strftime(
            "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)", time.gmtime()
        )
        config = json.dumps(
            {
                "context": {
                    "synthesis": {
                        "audio": {
                            "metadataoptions": {
                                "sentenceBoundaryEnabled": "false",
                                "wordBoundaryEnabled": "true",
                            },
                            "outputFormat": "audio-24khz-48kbitrate-mono-mp3",
                        }
                    }
                }
            }
        )
        # 甜度档位（音高/语速/风格）由 build_edge_ssml 内部统一读 settings，
        # 这里只传调用方语速，避免两处重复取值导致口径漂移
        ssml = build_edge_ssml(text, voice=voice, speed=speed)
        audio = bytearray()
        timing: list[dict[str, Any]] = []
        connection = await self._connect(self._url(), self._headers())
        try:
            await connection.send(
                f"X-Timestamp:{stamp}\r\nContent-Type:application/json; charset=utf-8\r\n"
                f"Path:speech.config\r\n\r\n{config}"
            )
            await connection.send(
                f"X-RequestId:{uuid.uuid4().hex}\r\nContent-Type:application/ssml+xml\r\n"
                f"X-Timestamp:{stamp}\r\nPath:ssml\r\n\r\n{ssml}"
            )
            while True:
                message = await asyncio.wait_for(connection.recv(), timeout=30)
                if isinstance(message, bytes):
                    chunk = _edge_audio_chunk(message)
                    if chunk:
                        audio.extend(chunk)
                elif "Path:turn.end" in message:
                    break
                else:
                    # 文本帧里混着 speech.config 回执和 audio.metadata 两类消息，
                    # 只有后者带 WordBoundary；解析失败只丢时间戳，不影响音频
                    timing.extend(_edge_timing_frame(message))
        finally:
            await connection.close()
        return bytes(audio), timing

    def probe(self) -> ProbeResult:
        detail = {
            "voice": settings.tts_edge_voice,
            "module": self._MODULE,
            # 甜度档位如实上报，答辩/前端可核对实际生效的参数
            "pitch_hz": settings.tts_edge_pitch_hz,
            "rate_percent": settings.tts_edge_rate_percent,
            "style": settings.tts_edge_style or "",
        }
        if not _module_available(self._MODULE):
            return self._failed(
                "未安装 edge-tts 依赖：pip install edge-tts", detail
            )
        now = time.monotonic()
        if self._probe_result is not None and now - self._probe_at < self._PROBE_TTL:
            return self._probe_result
        try:
            _run_async_blocking(lambda: self._probe_async())
        except Exception as exc:  # noqa: BLE001 - 403/网络异常都归为不可用
            status = getattr(getattr(exc, "response", None), "status_code", None)
            reason = f"Edge 朗读服务握手失败（{status}）" if status else f"Edge 朗读服务不可达：{exc}"
            self._probe_result = self._failed(reason, detail)
        else:
            self._probe_result = ProbeResult(available=True, detail=detail)
        self._probe_at = now
        return self._probe_result

    def synthesize(self, text: str, preset: VoicePreset | None, speed: float) -> bytes:
        return self.synthesize_with_timing(text, preset, speed)[0]

    def synthesize_with_timing(
        self, text: str, preset: VoicePreset | None, speed: float
    ) -> tuple[bytes, list[dict[str, Any]]]:
        try:
            audio, timing = _run_async_blocking(
                lambda: self._synthesize_async(text, speed), timeout=60.0
            )
        except Exception as exc:  # noqa: BLE001
            raise TtsSynthesisFailed(f"Edge 神经语音合成失败：{exc}") from exc
        if not audio:
            raise TtsSynthesisFailed("Edge 神经语音返回空音频")
        return audio, timing


def _edge_timing_frame(message: str) -> list[dict[str, Any]]:
    """从 Edge 文本帧里取出 WordBoundary 词级时间戳（换算成毫秒）。

    帧形如 ``X-RequestId:...\\r\\nPath:audio.metadata\\r\\n\\r\\n{json}``，
    json 里 ``Metadata[i] = {Type: "WordBoundary", Data: {Offset, Duration, text: {Text}}}``；
    Offset/Duration 的单位是 100ns（1 ms = 10000）。任何解析异常都只丢时间戳、
    不影响音频——缺时间戳时前端会如实降级为近似口型。
    """
    separator = message.find("\r\n\r\n")
    if separator < 0:
        return []
    header, payload = message[:separator], message[separator + 4 :]
    if "Path:audio.metadata" not in header:
        return []
    try:
        metadata = json.loads(payload).get("Metadata") or []
    except (json.JSONDecodeError, AttributeError):
        return []
    result: list[dict[str, Any]] = []
    for item in metadata:
        if not isinstance(item, dict) or item.get("Type") != "WordBoundary":
            continue
        data = item.get("Data") or {}
        text = (data.get("text") or {}).get("Text") or ""
        try:
            offset_ms = int(round(float(data.get("Offset")) / 10000))
            duration_ms = int(round(float(data.get("Duration")) / 10000))
        except (TypeError, ValueError):
            continue
        if not text.strip() or duration_ms <= 0:
            continue
        result.append(
            {
                "text": str(text),
                "offset_ms": max(0, offset_ms),
                "duration_ms": duration_ms,
            }
        )
    return result


def _edge_audio_chunk(message: bytes) -> bytes:
    """从 Edge 的二进制帧里取出音频负载。

    新协议帧格式：``[2 字节大端头部长度][头部文本][音频本体]``，头部形如
    ``X-RequestId:...\\r\\nX-StreamId:...\\r\\nPath:audio\\r\\n``；
    老协议是 ``[头部包括 Path:audio]\\r\\n\\r\\n[音频]``。两种都兼容，避免服务端灰度期丢音频。
    """
    if len(message) > 2:
        header_length = int.from_bytes(message[:2], "big")
        if 0 < header_length < len(message) - 2:
            header = message[2 : 2 + header_length]
            if b"Path:audio" in header:
                return message[2 + header_length :]
    separator = message.find(b"\r\n\r\n")
    if separator >= 0 and b"Path:audio" in message[:separator]:
        return message[separator + 4 :]
    return b""


def _split_for_online_tts(text: str, limit: int = 120) -> list[str]:
    """把长文本按句末标点切成 ≤limit 字的小段（在线音源走 query string，长度敏感）。"""
    content = str(text or "").strip()
    if not content:
        return []
    if len(content) <= limit:
        return [content]
    chunks: list[str] = []
    buffer = ""
    for sentence in re.split(r"(?<=[。！？；!?;\n])", content):
        if not sentence:
            continue
        while len(sentence) > limit:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.append(sentence[:limit])
            sentence = sentence[limit:]
        if len(buffer) + len(sentence) <= limit:
            buffer += sentence
        else:
            chunks.append(buffer)
            buffer = sentence
    if buffer:
        chunks.append(buffer)
    return chunks


def _escape_ssml(text: str) -> str:
    """SSML 里 < > & 必须转义，否则整条文本会被服务端拒绝。"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------- Piper-Plus

# 中文音节以 tone1–4 收尾（piper-plus 的 multilingual 模型走 pypinyin，输出 IPA +
# 音调 token）；没有音调收尾的音素组不构成一个汉字音节，不参与字符对齐。
_PIPER_TONE_RE = re.compile(r"^tone\d$")

# 音素 → 五元音 viseme。中文韵母常被整体输出（aʊ / ueɪ / iɛn / uaɪ），
# 必须按长度降序做「最长匹配」，只查单字母表会把 uo / aʊ 判错。
_PIPER_VISEME_PATTERNS: tuple[tuple[str, str], ...] = (
    ("uaɪ", "aa"),
    ("aɪ", "aa"),
    ("aʊ", "aa"),
    ("ueɪ", "ee"),
    ("uən", "ee"),
    ("iɛn", "ee"),
    ("iɛ", "ee"),
    ("yɛ", "ee"),
    ("ia", "ih"),
    ("iŋ", "ih"),
    ("in", "ih"),
    ("aŋ", "aa"),
    ("an", "aa"),
    ("əŋ", "ee"),
    ("uŋ", "ou"),
    ("oʊ", "oh"),
    ("uo", "oh"),
    ("ou", "oh"),
    ("eɪ", "ee"),
    ("y_vowel", "ih"),
    ("ɻ̩", "ih"),
    ("ʐ̩", "ih"),
    ("ɿ", "ih"),
    ("ʅ", "ih"),
    ("ɨ", "ih"),
    ("ɚ", "aa"),
    ("a", "aa"),
    ("ɑ", "aa"),
    ("ʌ", "aa"),
    ("æ", "aa"),
    ("o", "oh"),
    ("ɔ", "oh"),
    ("ɒ", "oh"),
    ("ʊ", "oh"),
    ("u", "ou"),
    ("ʉ", "ou"),
    ("e", "ee"),
    ("ɛ", "ee"),
    ("ɤ", "ee"),
    ("ɜ", "ee"),
    ("ə", "ee"),
    ("ø", "ee"),
    ("œ", "ee"),
    ("i", "ih"),
    ("ɪ", "ih"),
    ("y", "ih"),
    ("j", "ih"),
    ("w", "ou"),
)


def _piper_viseme(token: str) -> str | None:
    """单个音素 → 五元音之一；纯辅音（无元音字符）返回 None。"""
    if _PIPER_TONE_RE.match(token):
        return None
    for pattern, viseme in _PIPER_VISEME_PATTERNS:
        if pattern in token:
            return viseme
    return None


def _piper_syllables(phonemes: list[Any]) -> list[dict[str, Any]]:
    """把音素时间戳按 toneN 收尾切成音节，并给出每个音节的主口型。

    尾部没有音调收尾的残余音素组直接丢弃：它通常是句末停顿/标点，
    计入音节会让「音节数 == 汉字数」的校验失真。
    """
    syllables: list[dict[str, Any]] = []
    current: list[Any] = []
    for item in phonemes:
        current.append(item)
        if _PIPER_TONE_RE.match(str(getattr(item, "phoneme", ""))):
            viseme: str | None = None
            for phone in current:
                viseme = _piper_viseme(str(getattr(phone, "phoneme", ""))) or viseme
            syllables.append(
                {
                    "start_ms": float(getattr(current[0], "start_ms", 0.0)),
                    "end_ms": float(getattr(current[-1], "end_ms", 0.0)),
                    "viseme": viseme,
                }
            )
            current = []
    return syllables


# 字母数字串内部允许出现这些连接符（A-07 / v1.2 / 10:30），整体算一个对齐单元
_PIPER_RUN_CONNECTORS = frozenset("-_.:/#,")


def _is_piper_cjk(char: str) -> bool:
    """汉字与假名：在中文/多语种模型里稳定对应一个音节，可逐字对齐。"""
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x3040 <= code <= 0x30FF
    )


def _piper_units(text: str) -> list[tuple[str, str]]:
    """把原文切成对齐单元：汉字逐字，字母数字串整体（保留 A-07 这类连接符）。"""
    units: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            run = "".join(buffer).rstrip("-_./:#,")
            if run:
                units.append(("run", run))
            buffer.clear()

    for char in str(text):
        if _is_piper_cjk(char):
            flush()
            units.append(("cjk", char))
        elif char.isalnum():
            buffer.append(char)
        elif char in _PIPER_RUN_CONNECTORS and buffer:
            buffer.append(char)
        else:
            flush()
    flush()
    return units


def _allocate_run_syllables(total: int, weights: list[int]) -> list[int]:
    """把可用音节数按字符数比例分给各字母数字串：每串至少 1 个，最大余额法收尾。"""
    count = len(weights)
    spare = total - count
    weight_sum = sum(weights) or count
    quotas = [1 + spare * weight / weight_sum for weight in weights]
    allocated = [int(quota) for quota in quotas]
    missing = total - sum(allocated)
    ranked = sorted(range(count), key=lambda index: quotas[index] - allocated[index], reverse=True)
    for index in ranked[: max(0, missing)]:
        allocated[index] += 1
    return allocated


_PIPER_CN_DIGITS = "零一二三四五六七八九"
_PIPER_CN_UNITS = ("", "十", "百", "千")
_PIPER_CN_BIG_UNITS = ("", "万", "亿", "万亿")
_PIPER_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)*")
_PIPER_DATE_RE = re.compile(r"(?<!\d)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)")
# 时刻：10:30 / 10:30:45。前后紧邻数字或冒号时不算（避免把端口 8080 或 1:100 当时间）
_PIPER_TIME_RE = re.compile(r"(?<![\d:])(\d{1,2})[:：](\d{2})(?:[:：](\d{2}))?(?![\d:])")


def _read_cn_group(group: int) -> str:
    """读四位以内的数字（0-9999），中间连续零只补一个「零」。"""
    text = ""
    pending_zero = False
    for position in range(3, -1, -1):
        digit = group // (10**position) % 10
        if digit == 0:
            pending_zero = bool(text)
            continue
        if pending_zero:
            text += "零"
            pending_zero = False
        text += _PIPER_CN_DIGITS[digit] + _PIPER_CN_UNITS[position]
    return text


def _read_cn_int(value: int) -> str:
    """整数 → 中文读法：92 → 九十二、1001 → 一千零一、10000 → 一万。"""
    if value == 0:
        return "零"
    groups: list[int] = []
    while value:
        groups.append(value % 10000)
        value //= 10000
    parts: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            # 整组为零：只有低位还有非零时才补一个「零」（一万零一，而不是一万零）
            if parts and any(groups[lower] for lower in range(index)):
                if not parts[-1].endswith("零"):
                    parts.append("零")
            continue
        prefix = "零" if parts and group < 1000 and not parts[-1].endswith("零") else ""
        parts.append(prefix + _read_cn_group(group) + _PIPER_CN_BIG_UNITS[index])
    text = "".join(parts)
    return text[1:] if text.startswith("一十") else text


def _read_cn_digits(value: str) -> str:
    return "".join(_PIPER_CN_DIGITS[int(char)] for char in value)


def _read_piper_number(number: str) -> str:
    """纯数字串 → 中文读法：小数逐位、多段编号逐段按位、前导零按位。"""
    number = number.replace(",", "")
    parts = number.split(".")
    if len(parts) > 2:
        return "点".join(_read_cn_digits(part) for part in parts)
    if len(parts) == 2:
        return _read_cn_int(int(parts[0])) + "点" + _read_cn_digits(parts[1])
    if len(number) > 1 and number.startswith("0"):
        return _read_cn_digits(number)
    return _read_cn_int(int(number))


def _read_cn_date(match: re.Match[str]) -> str:
    """2026-11-17 → 二零二六年十一月十七日；月/日超范围时保持原样交给数字规则。"""
    month, day = int(match.group(2)), int(match.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return match.group(0)
    return (
        f"{_read_cn_digits(match.group(1))}年"
        f"{_read_cn_int(month)}月{_read_cn_int(day)}日"
    )


def _read_cn_min_sec(value: int) -> str:
    """分钟/秒的读法：不足十位补「零」（5 → 零五），否则按数量读。"""
    if value < 10:
        return "零" + _PIPER_CN_DIGITS[value]
    return _read_cn_int(value)


def _read_cn_time(match: re.Match[str]) -> str:
    """10:30 → 十点三十分；10:00 → 十点整；10:30:45 → 十点三十分四十五秒。

    时分秒越界（``25:70``）时原样返回，交给后面的数字规则，不硬套时间读法。
    """
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3)) if match.group(3) else None
    if hour > 23 or minute > 59 or (second is not None and second > 59):
        return match.group(0)
    if second is None:
        if minute == 0:
            return f"{_read_cn_int(hour)}点整"
        return f"{_read_cn_int(hour)}点{_read_cn_min_sec(minute)}分"
    return (
        f"{_read_cn_int(hour)}点{_read_cn_min_sec(minute)}分"
        f"{_read_cn_min_sec(second)}秒"
    )


def _is_piper_run_char(char: str) -> bool:
    return bool(char) and (char in _PIPER_RUN_CONNECTORS or (char.isascii() and char.isalnum()))


# 货币符号 → 单位词（符号在数字前）。金额小数按点读，不做角/分拆分。
_PIPER_CURRENCY = {
    "¥": "元",
    "￥": "元",
    "$": "美元",
    "€": "欧元",
    "£": "英镑",
    "₩": "韩元",
}

# 单位后缀 → 中文读法。只收运维话术里高频且不歧义的单位；
# 单字母 V/W/s/m/h/t/g/L 也收，但要求右侧不再是字母数字（见 _piper_unit_at）。
_PIPER_UNIT_SUFFIXES = {
    "km/h": "公里每小时",
    "m/s": "米每秒",
    "TB/s": "太字节每秒",
    "GB/s": "吉字节每秒",
    "MB/s": "兆字节每秒",
    "KB/s": "千字节每秒",
    "Gbps": "吉比特每秒",
    "Mbps": "兆比特每秒",
    "kbps": "千比特每秒",
    "kWh": "千瓦时",
    "GHz": "吉赫兹",
    "MHz": "兆赫兹",
    "kHz": "千赫兹",
    "MPa": "兆帕",
    "kPa": "千帕",
    "kg": "公斤",
    "km": "千米",
    "cm": "厘米",
    "mm": "毫米",
    "nm": "纳米",
    "mg": "毫克",
    "ms": "毫秒",
    "min": "分钟",
    "TB": "太字节",
    "GB": "吉字节",
    "MB": "兆字节",
    "KB": "千字节",
    "kW": "千瓦",
    "kV": "千伏",
    "mA": "毫安",
    "mL": "毫升",
    "Pa": "帕",
    "Hz": "赫兹",
    "rpm": "转每分钟",
    "dB": "分贝",
    "px": "像素",
    "℃": "摄氏度",
    "°C": "摄氏度",
    "g": "克",
    "t": "吨",
    "m": "米",
    "s": "秒",
    "h": "小时",
    "W": "瓦",
    "V": "伏",
    "L": "升",
}

# 长单位优先（min 先于 m、MHz 先于 Hz），否则短单位会抢走长单位的首字母
_PIPER_UNIT_TABLE: tuple[tuple[str, str], ...] = tuple(
    sorted(_PIPER_UNIT_SUFFIXES.items(), key=lambda item: len(item[0]), reverse=True)
)


def _piper_unit_at(source: str, index: int, prev: str) -> tuple[str, int] | None:
    """数字右侧的单位：返回（中文读法, 原文字符数）；不是单位时返回 None。

    两个边界条件，缺一就会误伤型号/版本号：
    - 数字左侧必须不在字母数字串里（``A-07s`` 是型号，不是「零七秒」）；
    - 单位右侧必须不再是字母数字（否则 ``5min`` 会被 ``m`` 抢成「五米in」）。
    """
    if _is_piper_run_char(prev):
        return None
    for suffix, spoken in _PIPER_UNIT_TABLE:
        if not source.startswith(suffix, index):
            continue
        tail = index + len(suffix)
        if tail < len(source) and source[tail].isascii() and source[tail].isalnum():
            continue
        return spoken, len(suffix)
    return None


def _normalize_piper_numbers(text: str) -> str:
    """把 ASCII 数字改写成中文读法：模型会直接丢弃数字，不改写等于漏念。

    实测 ``温度07度`` 的音频只读「温度度」。改写规则：
    - 独立数字按数量读：``92`` → 九十二、``0.35`` → 零点三五、``1001`` → 一千零一；
    - 千分位按整段数量读：``1,024`` → 一千零二十四；
    - 日期按年月日读：``2026-11-17`` → 二零二六年十一月十七日；
    - 时刻按时分读：``10:30`` → 十点三十分、``10:00`` → 十点整、``10:30:45`` → 十点三十分四十五秒；
    - 货币按单位词读：``¥5`` → 五元、``$12.50`` → 十二点五美元（金额尾零去掉，不拆角分）；
    - 单位按中文读：``5kg`` → 五公斤、``30ms`` → 三十毫秒、``3.5kW`` → 三点五千瓦；
    - 前导零按位读：``07`` → 零七；多段编号逐段读：``192.168.1.1`` → 一九二点一六八点一点一；
    - 字母数字串内逐位读：``A-07`` → A-零七；
    - 紧跟百分号加「百分之」，前导负号读「负」。
    """
    source = _PIPER_TIME_RE.sub(_read_cn_time, _PIPER_DATE_RE.sub(_read_cn_date, str(text)))
    result: list[str] = []
    cursor = 0
    for match in _PIPER_NUMBER_RE.finditer(source):
        start, end = match.span()
        number = match.group(0)
        sign = ""
        remove_from = start
        if start > 0 and source[start - 1] == "-":
            before_sign = source[start - 2] if start >= 2 else ""
            if not _is_piper_run_char(before_sign):
                sign = "负"
                remove_from = start - 1
        unit = _piper_unit_at(source, end, source[remove_from - 1] if remove_from else "")
        currency = ""
        if remove_from > 0 and source[remove_from - 1] in _PIPER_CURRENCY:
            currency = _PIPER_CURRENCY[source[remove_from - 1]]
            remove_from -= 1
        if currency and "." in number:
            # 12.50 元读「十二点五元」，不读「十二点五零元」
            number = number.rstrip("0").rstrip(".")
        inside_run = _is_piper_run_char(source[start - 1] if start else "") or _is_piper_run_char(
            source[end] if end < len(source) else ""
        )
        if inside_run and "." not in number and unit is None:
            # 带单位的数字必须按数量读（120MB → 一百二十兆字节），
            # 逐位读法只留给型号/编号串（A-07 → A-零七）
            spoken = _read_cn_digits(number)
        else:
            spoken = _read_piper_number(number)
        percent = source[end : end + 1] in {"%", "％"}
        result.append(source[cursor:remove_from])
        result.append(
            ("百分之" if percent else "") + sign + spoken + (currency or (unit[0] if unit else ""))
        )
        if percent:
            cursor = end + 1
        elif unit:
            cursor = end + unit[1]
        else:
            cursor = end
    result.append(source[cursor:])
    return "".join(result)


def _piper_timing_entry(label: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    """一组音节 → 一条前端契约条目（毫秒，口型取组内第一个真实韵母）。"""
    start_ms = max(0, int(round(group[0]["start_ms"])))
    end_ms = max(start_ms + 1, int(round(group[-1]["end_ms"])))
    entry: dict[str, Any] = {
        "text": label,
        "offset_ms": start_ms,
        "duration_ms": end_ms - start_ms,
    }
    viseme = next((item["viseme"] for item in group if item["viseme"]), None)
    if viseme:
        entry["viseme"] = viseme
    return entry


def piper_timing_entries(text: str, timing: Any) -> list[dict[str, Any]]:
    """把音素时间戳折算成前端契约：中文逐字、字母数字串整体。

    输出 ``[{text, offset_ms, duration_ms, viseme}]``（毫秒）。规则：
    - 汉字/假名各占一个音节，拿到**逐字精确**的起止与真实韵母；
    - 字母数字串（``A-07`` / ``Kubernetes``）的音节数不固定，整串共用一个时间段，
      串内由前端均分——这是「整串近似」，不冒充逐字；
    - 这套模型的 phonemizer 会直接丢弃 ASCII 数字（实测 ``07`` 不发声），
      此时不为无声字符编造时间，只输出汉字的条目；
    - 没有汉字锚点、音节数少于汉字数、或字母数字串的发音归属无法判定时回空数组，
      由前端如实降级，绝不硬凑时间戳。
    """
    syllables = _piper_syllables(getattr(timing, "phonemes", None) or [])
    units = _piper_units(text)
    cjk_units = [unit for unit in units if unit[0] == "cjk"]
    run_units = [unit for unit in units if unit[0] == "run"]
    if not syllables or not cjk_units or len(syllables) < len(cjk_units):
        return []

    spare = len(syllables) - len(cjk_units)
    if run_units:
        if spare and spare < len(run_units):
            # 有字母数字串没发声，但无法确定是哪一串：不猜
            return []
        run_counts = (
            _allocate_run_syllables(
                spare,
                [sum(1 for char in value if char.isalnum()) or 1 for _, value in run_units],
            )
            if spare
            else [0] * len(run_units)
        )
    elif spare:
        return []

    entries: list[dict[str, Any]] = []
    cursor = 0
    run_index = 0
    for kind, value in units:
        if kind == "cjk":
            entries.append(_piper_timing_entry(value, syllables[cursor : cursor + 1]))
            cursor += 1
        else:
            count = run_counts[run_index]
            run_index += 1
            if count <= 0:
                continue
            entries.append(_piper_timing_entry(value, syllables[cursor : cursor + count]))
            cursor += count
    return entries


class PiperPlusProvider(TtsProvider):
    """piper-plus（Piper 的 MIT 分支）：本地 ONNX VITS，CPU 可实时，且带音素级时间戳。

    模型来源必须锁到 piper-plus 自家 release：上游 rhasspy/piper-voices 的中文模型
    config 是 ``phoneme_type: espeak``，piper-plus 2.x 只支持
    ``openjtalk / bilingual / multilingual``，加载会直接 ``ValueError``（已实测）。
    只有导出 ``durations`` 输出的模型才给得出时间戳，否则回空数组由前端降级。
    """

    name = "piperplus"
    display_name = "Piper-Plus（本地音素对齐）"
    # piper 用 length_scale 控制快慢（越大越慢），可如实应用调用方语速
    supports_speed = True
    media_type = "audio/wav"
    # 单说话人固定音色：没有参考音频/音色切换，不能套用 voice presets
    supports_presets = False
    _MODULE = "piper_plus"

    def __init__(self) -> None:
        super().__init__()
        self._voice: Any = None

    def probe(self) -> ProbeResult:
        detail = {
            "module": self._MODULE,
            "model": settings.tts_piper_model,
            "config": settings.tts_piper_config,
            "loaded": self._loaded,
        }
        if not _module_available(self._MODULE):
            return self._failed(
                '未安装 piper-plus 依赖：pip install "piper-plus[cpu]"', detail
            )
        model_path = settings.tts_piper_model.strip()
        if not model_path:
            return self._failed(
                "未配置 TTS_PIPER_MODEL（需 piper-plus 自家 release 的 .onnx 模型）", detail
            )
        if not Path(model_path).is_file():
            return self._failed(f"Piper-Plus 模型文件不存在：{model_path}", detail)
        config_path = settings.tts_piper_config.strip()
        if config_path and not Path(config_path).is_file():
            return self._failed(f"Piper-Plus 模型配置不存在：{config_path}", detail)
        if self._load_error:
            return self._failed(f"模型加载失败：{self._load_error}", detail)
        return ProbeResult(available=True, detail=detail)

    def _ensure_voice(self) -> Any:
        with self._lock:
            if self._voice is not None:
                return self._voice
            try:
                from piper_plus import PiperVoice  # noqa: PLC0415 - 可选依赖懒加载
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise TtsUnavailable(f"piper-plus 依赖导入失败：{exc}") from exc
            model_path = settings.tts_piper_model.strip()
            config_path = settings.tts_piper_config.strip() or None
            try:
                voice = PiperVoice.load(model_path, config_path=config_path)
            except Exception as exc:  # noqa: BLE001 - 模型不兼容/权重损坏都如实上报
                self._load_error = str(exc)
                raise TtsUnavailable(f"Piper-Plus 模型加载失败：{exc}") from exc
            self._voice = voice
            self._loaded = True
            return voice

    def synthesize(self, text: str, preset: VoicePreset | None, speed: float) -> bytes:
        return self.synthesize_with_timing(text, preset, speed)[0]

    def synthesize_with_timing(
        self, text: str, preset: VoicePreset | None, speed: float
    ) -> tuple[bytes, list[dict[str, Any]]]:
        voice = self._ensure_voice()
        # length_scale 与语速成反比：speed=1.2 → 0.833（每个音素占更少帧）
        length_scale = 1.0 / float(speed) if speed and speed > 0 else 1.0
        # 模型 phonemizer 会丢弃 ASCII 数字：先改写成中文读法再合成。
        # 时间戳仍按原文对齐——数字串本来就走「整串近似」，多出来的音节由它吸收。
        spoken = _normalize_piper_numbers(text)
        try:
            audio, timing = voice.synthesize_with_timing(spoken, length_scale=length_scale)
        except Exception as exc:  # noqa: BLE001
            raise TtsSynthesisFailed(f"Piper-Plus 合成失败：{exc}") from exc
        if not audio:
            raise TtsSynthesisFailed("Piper-Plus 返回空音频")
        return audio, piper_timing_entries(text, timing)


_PROVIDER_FACTORIES.update(
    {
        VoxCpm2Provider.name: VoxCpm2Provider,
        F5TtsProvider.name: F5TtsProvider,
        EdgeTtsProvider.name: EdgeTtsProvider,
        BaiduTtsProvider.name: BaiduTtsProvider,
        PiperPlusProvider.name: PiperPlusProvider,
    }
)


def _provider_instance(name: str) -> TtsProvider:
    instance = _PROVIDER_INSTANCES.get(name)
    if instance is None:
        factory = _PROVIDER_FACTORIES[name]
        instance = factory()
        _PROVIDER_INSTANCES[name] = instance
    return instance


class TtsService:
    """TTS 编排：选 Provider、校验文本、线程池内合成、统一 WAV 输出。"""

    def __init__(self, provider_name: str | None = None) -> None:
        # 显式传入（测试/定向调用）优先；否则每次调用时读 settings，
        # 避免模块级单例在导入时把配置快照死。
        self._explicit = provider_name
        # 同一时刻只跑一个合成任务：消费级显卡（8GB）放不下两份权重
        self._semaphore = asyncio.Semaphore(1)

    @property
    def requested(self) -> str:
        return (self._explicit or settings.tts_provider or "auto").strip().lower()

    def _select(self) -> tuple[str | None, str]:
        """返回 (选中的 provider, 不可用原因)。"""
        requested = self.requested
        if requested == "none":
            return None, "TTS 已显式关闭（TTS_PROVIDER=none）"
        if requested == "auto":
            reasons: list[str] = []
            for name in _AUTO_ORDER:
                probe = _provider_instance(name).probe()
                if probe.available:
                    return name, ""
                reasons.append(f"{name}: {probe.reason}")
            return None, "没有可用的本地 TTS：" + "；".join(reasons)
        if requested not in _PROVIDER_FACTORIES:
            supported = "/".join(sorted(_PROVIDER_FACTORIES))
            return None, f"不支持的 TTS_PROVIDER: {requested}（可选 auto/{supported}/none）"
        probe = _provider_instance(requested).probe()
        if not probe.available:
            return None, probe.reason
        return requested, ""

    def status(self) -> dict[str, Any]:
        """各 Provider 的真实可用性 + 选中结果；探测失败也只是原因字段，不抛异常。"""
        providers = []
        for name in sorted(_PROVIDER_FACTORIES):
            probe = _provider_instance(name).probe()
            providers.append(
                {
                    "name": name,
                    "display_name": _PROVIDER_FACTORIES[name].display_name,
                    "available": probe.available,
                    "reason": probe.reason,
                    "detail": probe.detail or {},
                }
            )

        config_error = ""
        voices: list[dict[str, Any]] = []
        try:
            for preset in load_voice_presets().values():
                audio_path = preset.audio_path()
                voices.append(
                    {
                        "name": preset.name,
                        "description": preset.description,
                        "has_reference": bool(audio_path and audio_path.is_file()),
                    }
                )
        except TtsConfigInvalid as exc:
            config_error = exc.message

        selected, reason = self._select()
        if config_error:
            reason = f"{reason}；{config_error}" if reason else config_error
        result = {
            "requested": self.requested,
            "provider": selected,
            "available": selected is not None,
            "reason": reason,
            "providers": providers,
            "voices": voices,
        }
        # 预热状态：仅本地模型（f5tts/voxcpm2）才有意义；在线音源 probe 里已测通
        if selected in ("f5tts", "voxcpm2") or selected is None:
            result["preheat"] = tts_preheat.status_dict()
        return result

    async def synthesize(
        self, text: str, *, voice: str | None = None, speed: float = 1.0
    ) -> tuple[bytes, dict[str, Any]]:
        content = (text or "").strip()
        if not content:
            raise TtsRequestInvalid("text 不能为空", code="TTS_TEXT_EMPTY")
        if len(content) > settings.tts_max_chars:
            raise TtsRequestInvalid(
                f"文本过长：{len(content)} 字，上限 {settings.tts_max_chars} 字",
                code="TTS_TEXT_TOO_LONG",
            )

        provider_name, reason = self._select()
        if provider_name is None:
            raise TtsUnavailable(reason)

        presets = load_voice_presets()
        preset: VoicePreset | None = None
        if voice:
            preset = presets.get(voice)
            if preset is None:
                available = "、".join(presets) or "（未配置任何音色）"
                raise TtsRequestInvalid(
                    f"音色「{voice}」不存在，可用音色：{available}",
                    code="TTS_VOICE_NOT_FOUND",
                )
        elif len(presets) == 1:
            # 只配置了一条音色时直接用它：桌宠不需要前端硬编码音色名，
            # 也避免 F5-TTS（必须带参考音频）因未传 voice 而无谓失败。
            preset = next(iter(presets.values()))

        provider = _provider_instance(provider_name)
        if not provider.supports_presets:
            preset = None
        total = settings.tts_timeout_sec
        async with self._semaphore:
            try:
                audio, timing = await asyncio.wait_for(
                    asyncio.to_thread(provider.synthesize_with_timing, content, preset, speed),
                    timeout=total,
                )
            except asyncio.TimeoutError:
                raise TtsSynthesisFailed(
                    f"{provider.display_name} 合成超时（>{total:.0f}s），首次运行可能仍在加载权重"
                ) from None

        return audio, {
            "provider": provider.name,
            "display_name": provider.display_name,
            "media_type": provider.media_type,
            "voice": preset.name if preset else "",
            "speed_applied": provider.supports_speed and abs(speed - 1.0) > 1e-6,
            "chars": len(content),
            # 词级时间戳（毫秒）；没有边界事件的 Provider 回空数组，前端据此降级
            "timing": timing,
        }


def reset_provider_cache() -> None:
    """测试用：清空进程级 Provider 缓存（含已加载模型与加载失败状态）。"""
    _PROVIDER_INSTANCES.clear()


# ============================================================
# 启动预热（PERF-09）：服务就绪后后台预加载本地 TTS 权重
# ------------------------------------------------------------
# 冷启动时 F5-TTS 权重加载需 ~66s（实测：torch import 4s + 权重上卡 3s +
# vocos/vocab 准备 30s + 首次推理 4s + 收尾 25s）。若等用户首次播报才触发，
# 会导致前端静默 1 分钟以上，体验极差。
#
# 设计约束（重要）：
# 1) 预热必须在 lifespan yield **之后**用 asyncio.create_task 启动，
#    不能同步 await —— 否则 uvicorn 端口绑定被阻塞，前端连不上。
#    （经验教训：同类 FastAPI 冷启动预热曾因同步阻塞导致 /health 拒绝连接）
# 2) 预热只调 _ensure_engine() 加载权重，不跑完整 synthesize ——
#    前者只需 ~40s，后者额外 ~25s，且预热本身不该产生"假播报"。
# 3) 预热是 best-effort：失败不降级服务，首次合成会自动走正常懒加载。
# 4) 预热状态通过 /api/tts/status 暴露，前端据此决定是等待还是提示。
# ============================================================

_PREHEAT_IDLE = "idle"
_PREHEAT_RUNNING = "running"
_PREHEAT_DONE = "done"
_PREHEAT_FAILED = "failed"


class TtsPreheatCoordinator:
    """后台预热协调器：追踪一次预热任务的状态。"""

    def __init__(self) -> None:
        self.state = _PREHEAT_IDLE
        self.provider: str | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.error: str = ""
        self._lock = threading.Lock()

    @property
    def elapsed(self) -> float | None:
        """已耗时（秒）。运行中取当前时刻，完成后取总耗时。"""
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at is not None else time.time()
        return round(end - self.started_at, 1)

    def status_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "provider": self.provider,
            "elapsed": self.elapsed,
            "error": self.error,
        }

    async def start(self) -> None:
        """后台线程里触发权重加载 + 一次 dummy 推理。best-effort：失败只记状态，不抛异常。

        预热分两步：
        1) _ensure_engine() —— 加载主权重 + vocos 声码器（≈36s，驻留 1847MiB）
        2) dummy infer —— 用 1 字文本跑一次完整推理（≈2s，把推理 workspace 提前扩张到缓存池）
           这样首次合成时显存已是稳态 2770MiB，不会再冲 3326MiB 峰值。
        """
        with self._lock:
            if self.state in (_PREHEAT_RUNNING, _PREHEAT_DONE):
                return  # 已在跑或已完成，不重复
            self.state = _PREHEAT_RUNNING
            self.started_at = time.time()
            self.finished_at = None
            self.error = ""

        try:
            # 用与 TtsService 相同的选择逻辑决定预热哪个 provider
            svc = TtsService()
            provider_name, reason = svc._select()
            if provider_name is None:
                self._finish(_PREHEAT_FAILED, f"无可预热的 provider：{reason}")
                return

            self.provider = provider_name
            provider = _provider_instance(provider_name)

            if provider_name == "f5tts":
                # Step 1: 加载权重（主模型 + vocos）
                await asyncio.to_thread(provider._ensure_engine)

                # Step 2: dummy infer —— 跑一次完整推理，把 workspace 提前扩张
                # 选 1 字"好"：触发完整推理链路但耗时最短（≈1.86s）
                try:
                    presets = load_voice_presets()
                    preset = next(iter(presets.values()), None)
                    if preset is not None:
                        engine = provider._engine
                        audio_path = preset.audio_path()
                        if audio_path is not None and audio_path.is_file():
                            await asyncio.to_thread(
                                engine.infer,
                                ref_file=str(audio_path),
                                ref_text=preset.text.strip(),
                                gen_text="好",
                                speed=1.0,
                            )
                            # 释放 dummy wav 引用（engine.infer 返回的 tensor 会留在 GPU）
                            import gc as _gc

                            _gc.collect()
                            try:
                                import torch

                                if torch.cuda.is_available():
                                    torch.cuda.empty_cache()
                            except Exception:  # noqa: BLE001 - 清理失败不影响主流程
                                pass
                except Exception as dummy_exc:  # noqa: BLE001 - dummy infer 失败不应算预热整体失败
                    # dummy infer 只是优化峰值，失败可忽略；主权重已加载，服务仍可用
                    import logging as _logging

                    _logging.getLogger("tts.preheat").warning(
                        "F5-TTS dummy infer 跳过（不影响主权重已加载）：%s", dummy_exc
                    )

            elif provider_name == "voxcpm2":
                # VoxCPM2 没有单独的声码器加载阶段，_ensure_model 已覆盖全部
                await asyncio.to_thread(provider._ensure_model)
                # VoxCPM2 推理极慢（≈31s/句），不值得跑 dummy；跳过

            # Edge/baidu 是在线音源，probe 已测通，不需要额外预热

            self._finish(_PREHEAT_DONE)
        except Exception as exc:  # noqa: BLE001 - 预热失败不应炸掉整个服务
            self._finish(_PREHEAT_FAILED, str(exc))

    def _finish(self, state: str, error: str = "") -> None:
        with self._lock:
            self.state = state
            self.finished_at = time.time()
            self.error = error


# 进程内单例，由 main.py lifespan 触发
tts_preheat = TtsPreheatCoordinator()


# 进程内单例：Provider 缓存依赖它，每个请求新建实例会丢掉已加载模型。
tts_service = TtsService()
