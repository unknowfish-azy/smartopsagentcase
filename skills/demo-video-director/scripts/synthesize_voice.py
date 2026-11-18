# -*- coding: utf-8 -*-
"""按 storyboard 逐镜生成旁白：F5-TTS 声线克隆或 edge-tts。"""

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def run(command):
    result = subprocess.run([str(part) for part in command],
                            stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])


def compress_pauses(path, max_pause=0.32, threshold_ratio=0.02):
    """把超过 max_pause 的静音压到 max_pause，保留句读与呼吸。"""
    with wave.open(str(path), "rb") as reader:
        params = reader.getparams()
        raw = reader.readframes(reader.getnframes())
    if params.sampwidth not in (2, 4):
        return False
    dtype = np.int16 if params.sampwidth == 2 else np.int32
    samples = np.frombuffer(raw, dtype=dtype)
    channels = params.nchannels
    if channels > 1:
        samples = samples.reshape(-1, channels)
        mono = samples.mean(axis=1)
    else:
        mono = samples
    if mono.size == 0:
        return False
    window = max(1, params.framerate // 100)
    pad = (-mono.size) % window
    padded = np.pad(mono, (0, pad), mode="constant")
    frames = padded.reshape(-1, window)
    energy = np.abs(frames).mean(axis=1)
    threshold = max(float(energy.mean()) * threshold_ratio, 180.0)
    silent = energy < threshold

    keep = np.ones(padded.size, dtype=bool)
    max_frames = max(1, int(max_pause * 100))
    index = 0
    while index < silent.size:
        if not silent[index]:
            index += 1
            continue
        end = index
        while end < silent.size and silent[end]:
            end += 1
        if end - index > max_frames:
            keep[index * window + max_frames * window:end * window] = False
        index = end

    trimmed = padded[keep][:mono.size]
    if trimmed.size == 0 or trimmed.size == mono.size:
        return False
    if channels > 1:
        trimmed = np.repeat(trimmed, channels)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(params.nchannels)
        writer.setsampwidth(params.sampwidth)
        writer.setframerate(params.framerate)
        writer.writeframes(trimmed.astype(dtype).tobytes())
    return True


def synthesize_edge(text, out, voice, rate, ffmpeg):
    try:
        import edge_tts
    except ImportError:
        raise SystemExit("缺少 edge-tts：pip install edge-tts")
    with tempfile.TemporaryDirectory() as temp:
        mp3 = Path(temp) / "line.mp3"
        asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(mp3)))
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", mp3,
             "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", out])


class F5Engine:
    def __init__(self, args):
        if args.f5_path:
            sys.path.insert(0, str(Path(args.f5_path).resolve()))
        try:
            from f5_tts.api import F5TTS
        except ImportError:
            raise SystemExit("缺少 F5-TTS，请先安装 f5-tts 或用 --engine edge")
        kwargs = {"model": args.f5_model, "device": args.device}
        if args.ckpt:
            kwargs["ckpt_file"] = str(Path(args.ckpt).resolve())
        if args.vocab:
            kwargs["vocab_file"] = str(Path(args.vocab).resolve())
        if args.vocoder:
            kwargs["vocoder_name"] = args.vocoder
        self.engine = F5TTS(**kwargs)
        self.ref_audio = str(Path(args.ref_audio).resolve())
        self.ref_text = args.ref_text
        self.speed = args.speed

    def synthesize(self, text, out):
        self.engine.infer(
            ref_file=self.ref_audio,
            ref_text=self.ref_text,
            gen_text=text,
            file_wave=str(out),
            speed=self.speed,
            nfe_step=32,
            cfg_strength=2.0,
            sway_sampling_coef=-1,
            remove_silence=False,
        )


def main():
    parser = argparse.ArgumentParser(description="按 storyboard 生成逐镜旁白")
    parser.add_argument("--storyboard", default="storyboard.json")
    parser.add_argument("--out", help="输出目录，默认 <work>/voice/lines")
    parser.add_argument("--engine", choices=["f5", "edge", "none"], default="edge")
    parser.add_argument("--only", help="逗号分隔的镜头编号")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--speed", type=float, default=1.2, help="F5 合成语速，默认 1.2")
    parser.add_argument("--trim-pauses", action="store_true",
                        help="把超过 320ms 的静音压短，保留句读")
    parser.add_argument("--ref-audio", help="F5 参考音频，10–20 秒")
    parser.add_argument("--ref-text", help="参考音频逐字文本")
    parser.add_argument("--ckpt", help="F5 模型 ckpt")
    parser.add_argument("--vocab", help="F5 vocab 文件")
    parser.add_argument("--vocoder", help="F5 vocoder 名称或路径，如 vocos")
    parser.add_argument("--f5-path", help="额外加入 PYTHONPATH 的 F5 仓库目录")
    parser.add_argument("--f5-model", default="F5TTS_v1_Base")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--voice", default="zh-CN-YunxiNeural")
    parser.add_argument("--rate", default="+0%")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    storyboard_path = Path(args.storyboard).resolve()
    storyboard = load_json(storyboard_path)
    work = storyboard_path.parent
    out_dir = Path(args.out).resolve() if args.out else work / "voice" / "lines"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir.parent / "voice-report.json"
    only = {item.strip() for item in args.only.split(",")} if args.only else None

    shots = [shot for shot in storyboard["shots"]
             if not only or shot["id"] in only]
    if args.engine == "f5" and (not args.ref_audio or not args.ref_text):
        parser.error("--engine f5 需要 --ref-audio 与 --ref-text")
    if not shutil.which(args.ffmpeg):
        parser.error("PATH 中未找到 ffmpeg")

    engine = F5Engine(args) if args.engine == "f5" else None
    report = []
    missing = []
    for shot in shots:
        text = shot.get("spoken") or shot.get("text")
        if not text:
            continue
        out = out_dir / f"{shot['id']}.wav"
        if out.exists() and not args.overwrite:
            report.append({"id": shot["id"], "status": "kept", "path": str(out)})
            print(f"[{shot['id']}] 已存在，跳过", flush=True)
            continue
        if args.engine == "none":
            missing.append(shot["id"])
            report.append({"id": shot["id"], "status": "missing", "path": str(out)})
            continue
        print(f"[{shot['id']}] 合成 {len(text)} 字…", flush=True)
        if args.engine == "f5":
            engine.synthesize(text, out)
        else:
            synthesize_edge(text, out, args.voice, args.rate, args.ffmpeg)
        if args.trim_pauses:
            compress_pauses(out)
        report.append({"id": shot["id"], "status": "created", "path": str(out),
                       "chars": len(text)})
        print(f"[{shot['id']}] 完成 {out}", flush=True)

    report_path.write_text(json.dumps({
        "engine": args.engine,
        "speed": args.speed,
        "trim_pauses": args.trim_pauses,
        "lines": report,
        "missing": missing,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"配音报告：{report_path}", flush=True)
    if missing:
        raise SystemExit("缺少旁白：" + ", ".join(missing))


if __name__ == "__main__":
    main()
