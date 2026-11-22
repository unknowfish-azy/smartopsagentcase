"""真实人声语料评测（补充合成冻结集之外的真实数据证据）。

与 `eval_asr.py` 的区别：
- `eval_asr.py` 面向**命令词冻结集**（dev/holdout 双集合、DTW 与自由听写）；
- 本脚本面向**外部真实人声索引**（如 `voice_index.json` 的 `cues` 列表），
  只做自由听写，输出 CER / 完全命中率，用于证明「真实语音上模型的真实水平」。

红线：
- 只报索引里真实存在的条目；缺失文件跳过并计数，不伪造文本。
- 索引自带文本即参考真值；本脚本不生成、不改动参考文本。
- 音频统一重采样到 16k（whisper 系要求），重采样不改变参考文本。

用法：
    HF_ENDPOINT=https://hf-mirror.com py scripts/eval_asr_real.py --model medium
"""

import argparse
import json
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_index(index_path, fmt):
    """读取真实人声索引，返回 [{file, text}]。支持 cues 列表与顶层列表两种。"""
    raw = json.loads(Path(index_path).read_text(encoding="utf-8"))
    if fmt == "cues":
        if not isinstance(raw, dict) or "cues" not in raw:
            raise SystemExit(f"索引里没有 cues 字段: {index_path}")
        entries = raw["cues"]
    else:
        if not isinstance(raw, list):
            raise SystemExit(f"--index-format list 需要顶层数组: {index_path}")
        entries = raw
    rows = []
    for item in entries:
        file_name = item.get("file")
        text = item.get("text")
        if file_name and text:
            rows.append({"file": file_name, "text": text})
    return rows


def _load_mono_16k(path, target_rate=16000):
    """读取 WAV，转单声道并线性重采样到 16kHz float32。"""
    import wave as _wave  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    with _wave.open(str(path), "rb") as reader:
        rate = reader.getframerate() or target_rate
        channels = reader.getnchannels()
        width = reader.getsampwidth()
        frames = reader.readframes(reader.getnframes())
    if width != 2:
        raise ValueError(f"仅支持 16bit PCM WAV，实际 width={width}: {path}")
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    data /= 32768.0
    if rate != target_rate:
        src = np.linspace(0.0, 1.0, num=len(data))
        dst = np.linspace(0.0, 1.0, num=max(1, int(len(data) * target_rate / rate)))
        data = np.interp(dst, src, data).astype(np.float32)
    return data


def _normalize(text):
    cleaned = unicodedata.normalize("NFKC", (text or "").strip())
    return "".join(
        ch for ch in cleaned if not unicodedata.category(ch).startswith(("P", "Z"))
    )


def _edit_distance(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def evaluate(model, voice_dir, rows, beam_size):
    total_errors = 0
    total_chars = 0
    hits = 0
    missing = 0
    per_row = []
    started = time.time()
    for row in rows:
        path = Path(voice_dir) / row["file"]
        if not path.exists():
            missing += 1
            continue
        audio = _load_mono_16k(path)
        segments, _info = model.transcribe(audio, language="zh", beam_size=beam_size)
        hyp = "".join(seg.text for seg in segments).strip()
        ref = _normalize(row["text"])
        hyp_n = _normalize(hyp)
        errors = _edit_distance(hyp_n, ref)
        total_errors += errors
        total_chars += len(ref) or 1
        hits += hyp_n == ref
        per_row.append({
            "file": row["file"],
            "ref": row["text"],
            "hyp": hyp,
            "cer": round(errors / (len(ref) or 1), 4),
            "correct": hyp_n == ref,
        })
    elapsed = time.time() - started
    scored = len(per_row)
    return {
        "n": scored,
        "missing_files": missing,
        "hits": hits,
        "hit_rate": round(hits / scored, 4) if scored else 0.0,
        "mean_cer": round(total_errors / total_chars, 4) if total_chars else None,
        "eval_seconds": round(elapsed, 1),
        "per_row": per_row,
    }


def main():
    parser = argparse.ArgumentParser(description="真实人声语料评测")
    parser.add_argument("--voice-dir", required=True, help="音频所在目录")
    parser.add_argument("--index", required=True, help="索引 JSON（含 file/text）")
    parser.add_argument("--index-format", choices=["cues", "list"], default="cues")
    parser.add_argument("--model", default="base", help="faster-whisper 模型规格")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
    except ImportError:
        raise SystemExit("未安装 faster-whisper：pip install faster-whisper")

    rows = _load_index(args.index, args.index_format)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    result = evaluate(model, args.voice_dir, rows, args.beam_size)

    summary = {
        "date": str(date.today()),
        "backend": "faster-whisper",
        "model": f"faster-whisper-{args.model}",
        "voice_dir": str(args.voice_dir),
        "index": str(args.index),
        "index_entries": len(rows),
        **result,
    }
    out_dir = Path(args.output_dir) if args.output_dir else REPO / "reports" / f"t-asr-real-{date.today()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "eval_summary-real.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== 真实人声评测（model={args.model}, n={result['n']}）===")
    print(f"完全命中={result['hits']} 命中率={result['hit_rate']:.2%} 平均CER={result['mean_cer']}")
    if result["missing_files"]:
        print(f"缺失文件={result['missing_files']}")
    print(f"明细: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
