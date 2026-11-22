"""scripts/eval_asr.py 守卫测试。

红线：dev 与 holdout 必须成对出现（只报 dev 属选择性呈现）；两个 backend 的
结论文件必须分离；中文命令词判定前必须归一化标点，但不能把失配洗成命中。
本文件不加载真实 whisper/vosk，全部用假模型与临时 WAV，保证快速可重复。
"""

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from scripts import eval_asr


def _write_wav(path: Path, samples, rate: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(np.asarray(samples, dtype="<i2").tobytes())


def test_normalize_strips_whitespace_and_punctuation():
    assert eval_asr._normalize(" 打开知识库。 ") == "打开知识库"
    assert eval_asr._normalize("打开 知识库，") == "打开知识库"
    assert eval_asr._normalize("查询告警！") == "查询告警"
    assert eval_asr._normalize("") == ""
    assert eval_asr._normalize(None) == ""


def test_normalize_does_not_erase_distinct_labels():
    assert eval_asr._normalize("打开知识库") != eval_asr._normalize("查询告警")


def test_edit_distance_basics():
    assert eval_asr._edit_distance("", "") == 0
    assert eval_asr._edit_distance("abc", "") == 3
    assert eval_asr._edit_distance("", "abc") == 3
    assert eval_asr._edit_distance("打开知识库", "打开知识库") == 0
    assert eval_asr._edit_distance("打开知识库", "打开知识库啊") == 1


def test_load_mono_16k_resamples_to_16k_float32(tmp_path):
    rate = 8000
    samples = (np.sin(np.linspace(0.0, 8 * np.pi, rate)) * 10000).astype("<i2")
    path = tmp_path / "a.wav"
    _write_wav(path, samples, rate)

    out = eval_asr._load_mono_16k(path)

    assert out.dtype == np.float32
    assert len(out) == 16000
    assert float(np.abs(out).max()) <= 1.0


def test_load_mono_16k_downmixes_multichannel(tmp_path):
    left = np.full(8000, 8000, dtype=np.int16)
    right = np.full(8000, -8000, dtype=np.int16)
    stereo = np.empty(16000, dtype=np.int16)
    stereo[0::2] = left
    stereo[1::2] = right
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(stereo.tobytes())

    out = eval_asr._load_mono_16k(path)

    assert len(out) == 16000
    assert float(np.abs(out).max()) == pytest.approx(0.0, abs=1e-6)


def test_load_mono_16k_rejects_non_16bit(tmp_path):
    path = tmp_path / "weak.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(1)
        writer.setframerate(8000)
        writer.writeframes(b"\x00" * 100)

    with pytest.raises(ValueError):
        eval_asr._load_mono_16k(path)


def _seed_manifest(root: Path, rows):
    (root / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class _Segment:
    def __init__(self, text):
        self.text = text


class _Info:
    language = "zh"


class _FakeModel:
    """按顺序回放预设转写文本的假 whisper。"""

    def __init__(self, texts):
        self._texts = list(texts)

    def transcribe(self, audio, language, beam_size):
        return [_Segment(self._texts.pop(0))], _Info()


def test_rows_returns_only_requested_split(monkeypatch, tmp_path):
    _seed_manifest(
        tmp_path,
        [
            {"split": "dev", "label": "打开知识库", "text": "打开知识库", "path": "dev/a.wav", "mode": "zipvoice"},
            {"split": "holdout", "label": "查询告警", "text": "查询告警", "path": "holdout/b.wav", "mode": "zipvoice"},
        ],
    )
    monkeypatch.setattr(eval_asr, "DATASET_DIR", tmp_path)

    assert [row["label"] for row in eval_asr._rows("dev")] == ["打开知识库"]
    assert [row["label"] for row in eval_asr._rows("holdout")] == ["查询告警"]


def test_faster_whisper_scoring_counts_cer_and_empty(monkeypatch, tmp_path):
    _seed_manifest(
        tmp_path,
        [
            {"split": "dev", "label": "打开知识库", "text": "打开知识库", "path": "dev/a.wav", "mode": "zipvoice"},
            {"split": "dev", "label": "查询告警", "text": "查询告警", "path": "dev/b.wav", "mode": "zipvoice"},
        ],
    )
    monkeypatch.setattr(eval_asr, "DATASET_DIR", tmp_path)
    monkeypatch.setattr(eval_asr, "_load_mono_16k", lambda path: np.zeros(16000, dtype=np.float32))
    model = _FakeModel(["打开知识库。", ""])

    result = eval_asr.evaluate_split_faster_whisper(model, "dev", beam_size=5)

    assert result["n"] == 2
    assert result["correct"] == 1
    assert result["accuracy"] == 0.5
    assert result["empty_rate"] == 0.5
    assert result["cer"] == pytest.approx(4 / 9, abs=1e-3)
    assert result["per_label"]["打开知识库"]["correct"] == 1
    assert result["per_label"]["查询告警"]["correct"] == 0
    assert [row["correct"] for row in result["per_row"]] == [True, False]


def test_faster_whisper_keeps_raw_hypothesis_for_audit(monkeypatch, tmp_path):
    _seed_manifest(
        tmp_path,
        [{"split": "dev", "label": "重启服务", "text": "重启服务", "path": "dev/a.wav", "mode": "zipvoice"}],
    )
    monkeypatch.setattr(eval_asr, "DATASET_DIR", tmp_path)
    monkeypatch.setattr(eval_asr, "_load_mono_16k", lambda path: np.zeros(16000, dtype=np.float32))
    model = _FakeModel(["你不认识你不认识你不认识"])

    result = eval_asr.evaluate_split_faster_whisper(model, "dev", beam_size=5)

    assert result["per_row"][0]["hyp"] == "你不认识你不认识你不认识"
    assert result["per_row"][0]["detected_language"] == "zh"


def test_dtw_scoring_uses_label_match(monkeypatch, tmp_path):
    _seed_manifest(
        tmp_path,
        [
            {"split": "dev", "label": "打开知识库", "text": "打开知识库", "path": "dev/a.wav", "mode": "zipvoice"},
            {"split": "dev", "label": "查询告警", "text": "查询告警", "path": "dev/b.wav", "mode": "zipvoice"},
        ],
    )
    monkeypatch.setattr(eval_asr, "DATASET_DIR", tmp_path)
    monkeypatch.setattr(eval_asr, "load_wav_mono", lambda path: object())
    monkeypatch.setattr(eval_asr, "extract_features", lambda samples: object())

    class _Recognizer:
        def __init__(self):
            self._calls = 0

        def recognize(self, features):
            self._calls += 1
            return {"label": "打开知识库" if self._calls == 1 else "查询告警", "distance": 1.0}

    result = eval_asr.evaluate_split_dtw(_Recognizer(), "dev")

    assert result["n"] == 2
    assert result["correct"] == 2
    assert result["accuracy"] == 1.0
    assert result["avg_distance"] == 1.0


def test_output_path_separates_backends(tmp_path):
    assert eval_asr._output_path(tmp_path, "dtw") == tmp_path / "eval_summary.json"
    assert (
        eval_asr._output_path(tmp_path, "faster-whisper")
        == tmp_path / "eval_summary-faster-whisper.json"
    )


def test_frozen_dataset_manifest_keeps_both_splits():
    manifest = eval_asr.DATASET_DIR / "manifest.jsonl"
    if not manifest.exists():
        pytest.skip("冻结数据集未随仓库分发")
    rows = [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert {row["split"] for row in rows} == {"dev", "holdout"}
    assert len(rows) == 90
    assert all(row["mode"] == "zipvoice" for row in rows)
    assert all(row["text"] == row["label"] for row in rows)
