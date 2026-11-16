"""
语音识别工具（speech_to_text）。

可插拔转写栈（按优先级，均为运行时探测，不强制依赖）：
1. vosk           —— 离线自由转写（轻量，推荐）
2. faster-whisper —— 离线自由转写（质量更高，依赖较重）
3. whisper        —— 离线自由转写
4. DTW 命令词基线 —— 本仓内置训练型模型（受限命令集，见 agent/asr/dtw_baseline）
5. 确定性降级     —— 全部不可用时不伪造文本，返回结构化说明

红线：任何路径都不得编造识别结果；降级必须显式标注 mode。
"""

import tempfile
from pathlib import Path


def _detect_backend():
    """探测可用的第三方 ASR 后端，返回 (name, loader) 或 (None, None)。"""
    for name, module_name, build in (
        ("vosk", "vosk", _build_vosk),
        ("faster-whisper", "faster_whisper", _build_faster_whisper),
        ("whisper", "whisper", _build_whisper),
    ):
        try:
            __import__(module_name)
            return name, build
        except Exception:
            continue
    return None, None


def _build_vosk():
    from vosk import Model, KaldiRecognizer  # noqa: PLC0415

    def run(wav_path, language):
        import wave as _wave  # noqa: PLC0415

        model = Model(lang=language)
        with _wave.open(str(wav_path), "rb") as reader:
            rec = KaldiRecognizer(model, reader.getframerate())
            rec.SetWords(False)
            chunks = []
            while True:
                data = reader.readframes(4000)
                if not data:
                    break
                if rec.AcceptWaveform(data):
                    chunks.append(rec.Result())
            chunks.append(rec.FinalResult())
        import json as _json  # noqa: PLC0415

        return "".join(
            (_json.loads(part).get("text") or "") for part in chunks if part
        ).strip()

    return run


def _build_faster_whisper():
    from faster_whisper import WhisperModel  # noqa: PLC0415

    def run(wav_path, language):
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(wav_path), language=language)
        return "".join(seg.text for seg in segments).strip()

    return run


def _build_whisper():
    import whisper  # noqa: PLC0415

    def run(wav_path, language):
        model = whisper.load_model("base")
        result = model.transcribe(str(wav_path), language=language)
        return (result.get("text") or "").strip()

    return run


def _bytes_to_wav(audio_bytes, tmp_dir):
    """把前端上传的原始字节写入临时 WAV（由调用方保证为 16bit PCM WAV）。"""
    path = Path(tmp_dir) / "speech_input.wav"
    path.write_bytes(audio_bytes)
    return path


def _wav_duration_seconds(path):
    import wave as _wave  # noqa: PLC0415

    try:
        with _wave.open(str(path), "rb") as reader:
            frames = reader.getnframes()
            rate = reader.getframerate() or 1
            return round(frames / rate, 2)
    except Exception:
        return None


class SpeechToTextTool:

    name = "speech.to_text"

    description = (
        "把音频（16bit PCM WAV）转写为文本；优先 vosk/faster-whisper/whisper，"
        "其次 DTW 命令词基线，全部不可用时确定性降级，不伪造转写内容"
    )

    risk_level = "LOW"

    requires_approval = False

    def __init__(self, templates_path=None, language="zh"):
        self.language = language
        self.templates_path = templates_path
        self._backend_name, self._backend_run = _detect_backend()

    def _recognize_dtw(self, wav_path):
        """内置 DTW 命令词基线；模板缺失或音频不兼容时返回 None（交给降级）。"""
        try:
            from ..asr import DtwCommandRecognizer  # noqa: PLC0415

            if not self.templates_path or not Path(self.templates_path).exists():
                return None
            recognizer = DtwCommandRecognizer.load(self.templates_path)
            if recognizer.dataset_mode == "synthetic":
                # 合成自检模板禁止用于真实语音——不输出"识别结果"，防止伪造
                return {
                    "transcript": "",
                    "mode": "dtw-synthetic-templates",
                    "confidence": 0.0,
                    "detail": {
                        "message": (
                            "已安装的 DTW 模板来自 --synthetic 管线自检数据，"
                            "禁止用于真实语音。请在普通 Windows 终端重新运行 "
                            "scripts/build_asr_dataset.py（真实 TTS）与 "
                            "scripts/train_asr_baseline.py 生成真实模板。"
                        )
                    },
                }
            from ..asr import extract_features, load_wav_mono  # noqa: PLC0415

            features = extract_features(load_wav_mono(wav_path))
            hit = recognizer.recognize(features)
            if hit is None:
                return None
            return {
                "transcript": hit["label"],
                "mode": "dtw-command",
                "confidence": round(min(1.0, max(0.0, hit["margin"] / 10.0)), 2),
                "detail": {
                    "distance": hit["distance"],
                    "runner_up": hit["runner_up"],
                    "note": "受限命令词分类结果，自由听写请安装 vosk/whisper",
                },
            }
        except Exception as exc:  # 结构化失败，不伪造
            return {
                "transcript": "",
                "mode": "dtw-error",
                "confidence": 0.0,
                "detail": {"error": str(exc)},
            }

    def execute(
        self,
        audio_path: str = "",
        audio_bytes: bytes | None = None,
        language: str = "",
    ):
        lang = language or self.language
        tmp_dir = None
        try:
            if audio_bytes:
                tmp_dir = tempfile.mkdtemp(prefix="smartops-asr-")
                wav_path = _bytes_to_wav(audio_bytes, tmp_dir)
            elif audio_path:
                wav_path = Path(audio_path)
            else:
                return {
                    "transcript": "",
                    "mode": "invalid-input",
                    "confidence": 0.0,
                    "detail": {"message": "需要 audio_path 或 audio_bytes 之一"},
                }
            if not wav_path.exists():
                return {
                    "transcript": "",
                    "mode": "invalid-input",
                    "confidence": 0.0,
                    "detail": {"message": f"音频文件不存在: {wav_path}"},
                }

            duration = _wav_duration_seconds(wav_path)

            if self._backend_run is not None:
                try:
                    text = self._backend_run(wav_path, lang)
                    return {
                        "transcript": text,
                        "mode": f"free-form:{self._backend_name}",
                        "confidence": None,
                        "detail": {"duration_seconds": duration, "language": lang},
                    }
                except Exception as exc:
                    # 真实后端失败也走降级链，但如实记录原因
                    degraded_reason = f"backend {self._backend_name} 失败: {exc}"
            else:
                degraded_reason = "无已安装的第三方 ASR 后端（vosk/faster-whisper/whisper）"

            hit = self._recognize_dtw(wav_path)
            if hit is not None:
                # _recognize_dtw 返回 dict（dtw-command / 合成拒绝 / dtw-error）都
                # 是明确的识别结论，直接透出；仅模板缺失（None）才落到 unavailable。
                hit.setdefault("detail", {})
                if hit["mode"] == "dtw-command":
                    hit["detail"]["duration_seconds"] = duration
                    hit["detail"]["downgraded_from"] = degraded_reason
                return hit

            return {
                "transcript": "",
                "mode": "unavailable",
                "confidence": 0.0,
                "detail": {
                    "duration_seconds": duration,
                    "message": (
                        "当前环境没有可用的语音识别后端，且无 DTW 命令词模板。"
                        "自由转写请安装 vosk（pip install vosk + zh 模型）或 whisper；"
                        "命令词识别请先运行 scripts/build_asr_dataset.py 与 "
                        "scripts/train_asr_baseline.py 生成模板。"
                    ),
                    "reason": degraded_reason,
                },
            }
        finally:
            if tmp_dir:
                import shutil  # noqa: PLC0415

                shutil.rmtree(tmp_dir, ignore_errors=True)
