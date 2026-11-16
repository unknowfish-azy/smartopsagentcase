"""
speech_to_text 工具与 DTW 命令词基线的单测。

覆盖：
- load_wav_mono / extract_features 的纯函数行为（合成 WAV）
- DTW 训练→识别→保存→加载 回环
- 工具的确定性降级路径（无后端、无模板、无效输入）
- 合成自检模板必须被工具拒绝（防伪造红线）
"""

import struct
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest  # noqa: E402

from agent.asr import (  # noqa: E402
    DtwCommandRecognizer,
    extract_features,
    load_wav_mono,
)
from agent.tools import SpeechToTextTool, ToolRegistry  # noqa: E402


def _write_chirp_wav(path, f_start, f_end, seconds=1.0, sr=8000, seed=0):
    """生成确定性扫频 WAV：不同 (f_start, f_end) 即不同"命令"。"""
    n = int(sr * seconds)
    frames = []
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = f_start + (f_end - f_start) * t + (seed % 7) * 0.5
        phase += 2 * 3.141592653589793 * freq / sr
        envelope = min(1.0, 8 * t) * min(1.0, 8 * (1 - t))
        value = math_sine(phase) * envelope
        frames.append(int(value * 20000))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sr)
        writer.writeframes(struct.pack(f"<{len(frames)}h", *frames))


def math_sine(x):
    import math

    return math.sin(x)


def _build_dataset(tmp_path, commands=("alpha", "beta", "gamma")):
    """构造小型合成数据集：dev 3 变体 / holdout 2 变体。"""
    root = tmp_path / "asr"
    manifest = []
    for index, label in enumerate(commands):
        for split, count, base_seed in (("dev", 3, 10), ("holdout", 2, 60)):
            for variant in range(count):
                rel = f"{split}/{label}__{split}_{variant}.wav"
                _write_chirp_wav(
                    root / rel,
                    f_start=180 + index * 120,
                    f_end=700 + index * 90,
                    seed=base_seed + variant,
                )
                manifest.append(
                    {
                        "split": split,
                        "label": label,
                        "text": label,
                        "path": rel,
                    }
                )
    import json

    (root / "manifest.jsonl").write_text(
        "\n".join(json.dumps(row) for row in manifest), encoding="utf-8"
    )
    return root


def test_load_wav_and_features_shape(tmp_path):
    wav = tmp_path / "a.wav"
    _write_chirp_wav(wav, 200, 800)
    samples = load_wav_mono(wav)
    assert len(samples) > 1000
    assert max(abs(s) for s in samples) <= 1.0
    features = extract_features(samples)
    assert features and all(len(row) == 10 for row in features)


def test_dtw_train_recognize_roundtrip(tmp_path):
    root = _build_dataset(tmp_path)
    import json

    dev = {}
    for line in (root / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["split"] == "dev":
            dev.setdefault(row["label"], []).append(
                extract_features(load_wav_mono(root / row["path"]))
            )
    recognizer = DtwCommandRecognizer().train(dev, dataset_mode="sapi")
    assert set(recognizer.templates) == {"alpha", "beta", "gamma"}

    model_path = tmp_path / "templates.json"
    recognizer.save(model_path)
    loaded = DtwCommandRecognizer.load(model_path)
    assert loaded.dataset_mode == "sapi"

    holdout = [
        json.loads(line)
        for line in (root / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["split"] == "holdout"
    ]
    correct = 0
    for row in holdout:
        hit = loaded.recognize(extract_features(load_wav_mono(root / row["path"])))
        assert hit is not None and hit["margin"] >= 0
        correct += hit["label"] == row["label"]
    assert correct == len(holdout)


def test_tool_invalid_input_degrades():
    tool = SpeechToTextTool(templates_path="/nonexistent/templates.json")
    result = tool.execute()
    assert result["mode"] == "invalid-input"
    assert result["transcript"] == ""


def test_tool_missing_file_degrades():
    tool = SpeechToTextTool(templates_path="/nonexistent/templates.json")
    result = tool.execute(audio_path="/nonexistent/clip.wav")
    assert result["mode"] == "invalid-input"


def test_tool_synthetic_templates_refused(tmp_path):
    """红线回归：合成自检模板必须被拒，不得输出"识别结果"。"""
    root = _build_dataset(tmp_path)
    import json

    dev = {}
    for line in (root / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["split"] == "dev":
            dev.setdefault(row["label"], []).append(
                extract_features(load_wav_mono(root / row["path"]))
            )
    templates = tmp_path / "templates.json"
    DtwCommandRecognizer().train(dev, dataset_mode="synthetic").save(templates)

    tool = SpeechToTextTool(templates_path=str(templates))
    sample = root / "holdout"
    wav = sorted(sample.glob("*.wav"))[0]
    result = tool.execute(audio_path=str(wav))
    assert result["mode"] == "dtw-synthetic-templates"
    assert result["transcript"] == ""


def test_tool_real_templates_recognize(tmp_path):
    """真实口径模板（dataset_mode=sapi）下，工具应能给出命令词结果。"""
    root = _build_dataset(tmp_path)
    import json

    dev = {}
    for line in (root / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["split"] == "dev":
            dev.setdefault(row["label"], []).append(
                extract_features(load_wav_mono(root / row["path"]))
            )
    templates = tmp_path / "templates.json"
    DtwCommandRecognizer().train(dev, dataset_mode="sapi").save(templates)

    tool = SpeechToTextTool(templates_path=str(templates))
    wav = sorted((root / "holdout").glob("*.wav"))[0]
    result = tool.execute(audio_path=str(wav))
    assert result["mode"] == "dtw-command"
    assert result["transcript"] in {"alpha", "beta", "gamma"}
    assert 0.0 <= (result["confidence"] or 0.0) <= 1.0


def test_tool_registered_in_registry():
    registry = ToolRegistry()
    registry.register(SpeechToTextTool())
    assert registry.get("speech.to_text") is not None
    assert registry.get("speech.to_text").risk_level == "LOW"


@pytest.mark.parametrize(
    "wav_kwargs",
    [{"f_start": 100, "f_end": 100}, {"f_start": 4000, "f_end": 3900}],
)
def test_constant_and_high_tones_feature_valid(tmp_path, wav_kwargs):
    wav = tmp_path / "tone.wav"
    _write_chirp_wav(wav, **wav_kwargs)
    features = extract_features(load_wav_mono(wav))
    assert all(all(v == v and abs(v) < 1e6 for v in row) for row in features)
