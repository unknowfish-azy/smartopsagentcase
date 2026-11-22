"""scripts/build_asr_dataset.py 守卫测试。

覆盖两处正确性修复：
1. 采样率必须按来源落盘——ZipVoice 输出 24kHz，写死 8k 会把音频拉伸 3 倍；
2. 三种模式都必须写 manifest——早期版本只在 sapi 分支 append，重建后清单为空。

不触真实 TTS：zipvoice/sapi 走 monkeypatch，synthetic 用真实纯 stdlib 生成。
"""

import json
import wave
from pathlib import Path

import numpy as np
import pytest

from scripts import build_asr_dataset as bld


def _read_rate(path: Path) -> int:
    with wave.open(str(path), "rb") as reader:
        return reader.getframerate()


def _read_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as reader:
        return reader.getnframes() / reader.getframerate()


def test_write_wav_defaults_to_8k_for_synthetic_and_sapi(tmp_path):
    path = tmp_path / "a.wav"
    bld._write_wav(path, np.zeros(800, dtype=np.float32))

    assert _read_rate(path) == 8000
    assert _read_duration(path) == pytest.approx(0.1, abs=1e-6)


def test_write_wav_honours_source_sample_rate(tmp_path):
    """ZipVoice 的 24k 样本必须按 24k 落盘，否则时长被拉长 3 倍。"""
    samples = np.zeros(2400, dtype=np.float32)
    path = tmp_path / "z.wav"

    bld._write_wav(path, samples, 24000)

    assert _read_rate(path) == 24000
    assert _read_duration(path) == pytest.approx(0.1, abs=1e-6)


def test_build_synthetic_writes_complete_manifest(monkeypatch, tmp_path):
    ds = tmp_path / "ds"
    monkeypatch.setattr(bld, "DATASET_DIR", ds)

    rows = bld.build("synthetic", dev_variants=2, holdout_variants=1)

    assert len(rows) == 10 * 3
    manifest = [
        json.loads(line)
        for line in (ds / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(manifest) == len(rows)
    assert {row["split"] for row in manifest} == {"dev", "holdout"}
    assert all(row["mode"] == "synthetic" for row in manifest)
    assert all(_read_rate(ds / row["path"]) == 8000 for row in manifest)


def test_zipvoice_synth_rejects_missing_reference(tmp_path):
    """参考音缺失必须显式失败，不得静默用默认值或伪造语音。"""
    with pytest.raises(RuntimeError, match="参考音不存在"):
        bld._zipvoice_synth(
            ["打开知识库"],
            ref_wav=tmp_path / "nope.wav",
            ref_txt=tmp_path / "nope.txt",
        )


def test_build_zipvoice_records_manifest_and_keeps_24k(monkeypatch, tmp_path):
    ds = tmp_path / "ds"
    monkeypatch.setattr(bld, "DATASET_DIR", ds)
    synthesized = []

    def fake_synth(texts, ref_wav=None, ref_txt=None):
        out = []
        for text in texts:
            synthesized.append(text)
            out.append((text, np.zeros(2400, dtype=np.float32), 24000))
        return out

    monkeypatch.setattr(bld, "_zipvoice_synth", fake_synth)

    rows = bld.build("zipvoice", dev_variants=2, holdout_variants=1)

    assert len(rows) == 10 * 3
    assert len(synthesized) == 10 * 3
    manifest = [
        json.loads(line)
        for line in (ds / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(manifest) == len(rows)
    assert all(row["mode"] == "zipvoice" for row in manifest)
    assert all(_read_rate(ds / row["path"]) == 24000 for row in manifest)
    assert all(_read_duration(ds / row["path"]) == pytest.approx(0.1, abs=1e-6) for row in manifest)


def test_build_sapi_records_manifest(monkeypatch, tmp_path):
    ds = tmp_path / "ds"
    monkeypatch.setattr(bld, "DATASET_DIR", ds)
    source = tmp_path / "sapi-source.wav"
    with wave.open(str(source), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(np.zeros(1600, dtype="<i2").tobytes())
    monkeypatch.setattr(bld, "_sapi_samples", lambda text, rate: source)

    rows = bld.build("sapi", dev_variants=1, holdout_variants=1)

    assert len(rows) == 10 * 2
    manifest = [
        json.loads(line)
        for line in (ds / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(manifest) == len(rows)
    assert all(row["mode"] == "sapi" for row in manifest)
    assert all(_read_rate(ds / row["path"]) == 8000 for row in manifest)
