"""
构建 ASR 冻结数据集（dev + holdout 双集合，对齐 M02 红线口径）。

三种模式：
- 默认（zipvoice，真实语音）：复用本项目演示视频的离线 ZipVoice TTS 栈
  （output/video-kit/v2/gen_narration.py 同款：sherpa-onnx + Emilia 声音克隆），
  合成 10 条运维命令的真实中文语音。零网络、零密钥，与省赛视频同源同声。
- --sapi（真实语音备用）：Windows SAPI TTS（COM 经 PowerShell -EncodedCommand）。
  约束沙箱会拦截 COM，普通 Windows 终端可用。
- --synthetic（管线自检）：纯 stdlib 生成每类一条独立"声纹"扫频信号，
  证明 build → train → eval 全链路数学正确；**指标不得当作真实语音结果引用**。

产物：SmartOps-Dataset/asr/{dev,holdout}/*.wav + manifest.jsonl
红线：数据集与划分一旦生成即为冻结快照；评测必须同时报 dev 与 holdout。
"""

import argparse
import base64
import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO / "SmartOps-Dataset" / "asr"

# 10 条运维命令词（label = 命令文本本身）
COMMANDS = [
    "打开知识库",
    "查询告警",
    "重启服务",
    "查看日志",
    "执行巡检",
    "备份数据库",
    "查看仪表盘",
    "停止任务",
    "生成报告",
    "回滚变更",
]

DEV_VARIANTS = 6    # 训练用变体数（每命令）
HOLDOUT_VARIANTS = 3  # 留出集变体数（每命令）
SR = 8000


def _write_wav(path, samples):
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max(1e-9, max(abs(s) for s in samples))
    pcm = [max(-32767, min(32767, int(s / peak * 28000))) for s in samples]
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SR)
        writer.writeframes(struct.pack(f"<{len(pcm)}h", *pcm))


def _synthetic_samples(label_index, variant, seconds=1.2):
    """每类一条独立扫频"声纹"：start/end 频率由类索引决定，变体加抖动与谐波。"""
    rng_seed = (label_index * 977 + variant * 131) % 10000
    jitter = lambda: ((rng_seed * 1103515245 + 12345) % 97 - 48) / 48.0  # noqa: E731
    f_start = 180 + label_index * 55 + jitter() * 12
    f_end = 700 + label_index * 45 + jitter() * 12
    n = int(SR * seconds)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = f_start + (f_end - f_start) * t
        phase += 2 * math.pi * freq / SR
        envelope = min(1.0, 8 * t) * min(1.0, 8 * (1 - t))
        value = (
            math.sin(phase)
            + 0.35 * math.sin(2 * phase + jitter() * 0.3)
            + 0.12 * jitter() / 8.0
        )
        out.append(value * envelope)
    return out


def _sapi_samples(text, rate):
    """真实模式：PowerShell SAPI COM 合成（-EncodedCommand 对中文安全），
    输出临时 16k WAV，随后由调用方统一重采样写入。"""
    import tempfile  # noqa: PLC0415

    tmp_wav = Path(tempfile.mkdtemp(prefix="smartops-tts-")) / "clip.wav"
    ps = (
        "$v = New-Object -ComObject SAPI.SpVoice;"
        "$v.Rate = %d;"
        "$fs = New-Object -ComObject SAPI.SpFileStream;"
        "$fs.Format.Type = 34;"
        "$fs.Open('%s', 3);"
        "$v.AudioOutputStream = $fs;"
        "$v.Speak('%s');"
        "$fs.Close();$v.AudioOutputStream = $null"
    ) % (rate, str(tmp_wav).replace("'", "''"), text.replace("'", ""))
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0 or not tmp_wav.exists():
        raise RuntimeError(
            f"SAPI TTS 合成失败（returncode={proc.returncode}）。"
            "约束环境可改用 --synthetic 做管线自检；真实语音请在普通 Windows 终端运行。"
        )
    return tmp_wav


def _zipvoice_synth(texts):
    """复用项目演示视频的离线 ZipVoice TTS，批量合成真实中文语音。

    返回 [(text, samples@24k), ...]；失败抛 RuntimeError（不伪造）。
    """
    import os as _os  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415
    import sherpa_onnx as so  # noqa: PLC0415

    old = Path("D:/EVvideo/out")
    if not old.exists():
        raise RuntimeError(f"ZipVoice 资源目录不存在: {old}")
    runtime_bin = next(old.glob("runtime/sherpa-onnx-*/bin"), None)
    if runtime_bin is None or hasattr(_os, "add_dll_directory") is False:
        raise RuntimeError("ZipVoice 运行时 DLL 目录不可用")
    _os.add_dll_directory(str(runtime_bin))
    _os.environ["PATH"] = str(runtime_bin) + _os.pathsep + _os.environ.get("PATH", "")
    model_dir = old / "models" / "sherpa-onnx-zipvoice-distill-int8-zh-en-emilia"
    cfg = so.OfflineTtsZipvoiceModelConfig(
        tokens=str(model_dir / "tokens.txt"),
        encoder=str(model_dir / "encoder.int8.onnx"),
        decoder=str(model_dir / "decoder.int8.onnx"),
        data_dir=str(model_dir / "espeak-ng-data"),
        lexicon=str(model_dir / "lexicon.txt"),
        vocoder=str(old / "models" / "vocos_24khz.onnx"),
    )
    tts = so.OfflineTts(
        so.OfflineTtsConfig(
            model=so.OfflineTtsModelConfig(zipvoice=cfg, num_threads=4, debug=False),
            max_num_sentences=1,
        )
    )
    ref_path = REPO / "output" / "video-kit" / "v2" / "voice" / "refLong.wav"
    ref_txt = (
        REPO / "output" / "video-kit" / "v2" / "voice" / "refLong.txt"
    ).read_text(encoding="utf-8").strip()
    with wave.open(str(ref_path), "rb") as reader:
        prompt = np.frombuffer(reader.readframes(reader.getnframes()), dtype="<i2").astype(
            np.float32
        ) / 32768.0
        ref_sr = reader.getframerate()
    results = []
    for text in texts:
        # speed 轻微变化模拟说话差异；num_steps=8 与视频同款质量档
        speed = 1.0
        r = tts.generate(text, ref_txt, prompt, ref_sr, speed=speed, num_steps=8)
        results.append((text, np.asarray(r.samples, dtype=np.float32)))
    return results


def build(mode, dev_variants=DEV_VARIANTS, holdout_variants=HOLDOUT_VARIANTS):
    if DATASET_DIR.exists():
        import shutil  # noqa: PLC0415

        shutil.rmtree(DATASET_DIR)
    manifest = []
    real_tmp_files = []

    # zipvoice 模式：逐条合成 + 立即落盘（避免长时间任务把 90 条音频全压在内存）
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    zipvoice_pending = []
    if mode == "zipvoice":
        for index, text in enumerate(COMMANDS):
            for split, count in (("dev", dev_variants), ("holdout", holdout_variants)):
                for variant in range(count):
                    zipvoice_pending.append((index, text, split, variant))
        print(
            f"ZipVoice 离线合成 {len(zipvoice_pending)} 条真实语音"
            "（复用省赛视频同款 TTS，逐条落盘）...",
            flush=True,
        )

    zipvoice_iter = iter(zipvoice_pending) if mode == "zipvoice" else None
    zipvoice_batch = []

    def _zipvoice_one(index, text, split, variant):
        """每次调用合成一条；模型只加载一次（由 _zipvoice_batch_flush 复用）。"""
        return _zipvoice_synth([text])[0][1]

    def _zipvoice_batch_flush():
        """批量合成一组 (index,text,split,variant) 并落盘，模型加载一次。"""
        if not zipvoice_batch:
            return
        texts = [item[1] for item in zipvoice_batch]
        results = _zipvoice_synth(texts)
        for (index, text, split, variant), (_t, samples) in zip(zipvoice_batch, results):
            rel_path = Path(split) / f"{text}__{split}_{variant:02d}.wav"
            _write_wav(DATASET_DIR / rel_path, samples)
            print(f"  [{index+1}/{len(COMMANDS)}] {text} {split}_{variant:02d}", flush=True)
        zipvoice_batch.clear()

    for index, text in enumerate(COMMANDS):
        for split, count, rate_pool in (
            ("dev", dev_variants, (-1, 0, 1)),
            ("holdout", holdout_variants, (-2, 2, 3)),
        ):
            for variant in range(count):
                name = f"{text}__{split}_{variant:02d}.wav"
                rel_path = Path(split) / name
                out_path = DATASET_DIR / rel_path
                if mode == "synthetic":
                    samples = _synthetic_samples(index, variant)
                    _write_wav(out_path, samples)
                elif mode == "zipvoice":
                    # 每条命令的所有变体攒成一批，一次加载模型合成后落盘
                    zipvoice_batch.append((index, text, split, variant))
                    if variant == count - 1 and split == "holdout":
                        _zipvoice_batch_flush()
                else:  # sapi
                    rate = rate_pool[variant % len(rate_pool)]
                    tmp_wav = _sapi_samples(text, rate)
                    real_tmp_files.append(tmp_wav)
                    from agent.asr import load_wav_mono  # noqa: PLC0415

                    _write_wav(out_path, load_wav_mono(tmp_wav))
                manifest.append(
                    {
                        "split": split,
                        "label": text,
                        "text": text,
                        "path": str(rel_path).replace("\\", "/"),
                        "mode": mode,
                    }
                )
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = DATASET_DIR / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as writer:
        for row in manifest:
            writer.write(json.dumps(row, ensure_ascii=False) + "\n")
    for tmp in real_tmp_files:
        try:
            tmp.unlink()
            tmp.parent.rmdir()
        except OSError:
            pass
    counts = {}
    for row in manifest:
        counts[row["split"]] = counts.get(row["split"], 0) + 1
    print(f"数据集构建完成（mode={mode}）: {counts['dev']} dev / {counts['holdout']} holdout")
    print(f"清单: {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="构建 ASR 冻结数据集")
    parser.add_argument(
        "--mode",
        choices=("zipvoice", "sapi", "synthetic"),
        default="zipvoice",
        help="zipvoice=项目离线 TTS 真实语音(默认)；sapi=Windows COM；synthetic=管线自检",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="等价于 --mode synthetic（保留兼容）",
    )
    parser.add_argument("--dev-variants", type=int, default=DEV_VARIANTS)
    parser.add_argument("--holdout-variants", type=int, default=HOLDOUT_VARIANTS)
    args = parser.parse_args()
    mode = "synthetic" if args.synthetic else args.mode
    build(mode, args.dev_variants, args.holdout_variants)
    return 0


if __name__ == "__main__":
    sys.exit(main())
