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
# edge/baidu 的 probe 都是实测 + 10 分钟缓存，不可用会被跳过。
_AUTO_ORDER = ("f5tts", "edge", "baidu", "voxcpm2")


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

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._load_error = ""

    def probe(self) -> ProbeResult:
        raise NotImplementedError

    def synthesize(self, text: str, preset: VoicePreset | None, speed: float) -> bytes:
        raise NotImplementedError

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

    async def _synthesize_async(self, text: str, speed: float) -> bytes:
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
        finally:
            await connection.close()
        return bytes(audio)

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
        try:
            audio = _run_async_blocking(lambda: self._synthesize_async(text, speed), timeout=60.0)
        except Exception as exc:  # noqa: BLE001
            raise TtsSynthesisFailed(f"Edge 神经语音合成失败：{exc}") from exc
        if not audio:
            raise TtsSynthesisFailed("Edge 神经语音返回空音频")
        return audio


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


_PROVIDER_FACTORIES.update(
    {
        VoxCpm2Provider.name: VoxCpm2Provider,
        F5TtsProvider.name: F5TtsProvider,
        EdgeTtsProvider.name: EdgeTtsProvider,
        BaiduTtsProvider.name: BaiduTtsProvider,
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
        total = settings.tts_timeout_sec
        async with self._semaphore:
            try:
                audio = await asyncio.wait_for(
                    asyncio.to_thread(provider.synthesize, content, preset, speed),
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
