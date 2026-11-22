"""
评测 ASR 基线（dev + holdout 双集合，M02 红线口径）。

两条被测链路：
  --backend dtw            受限命令词分类（agent/asr/dtw_baseline.py）
  --backend faster-whisper 离线自由听写（faster_whisper），对同一命令集算准确率

红线：只报 dev 属于"选择性呈现"——本脚本强制同时输出两个集合；
holdout 若从未参与训练，其准确率才代表真实泛化。

faster-whisper 的度量口径（与 DTW 不同，必须分别说明）：
- accuracy  = 归一化后**完全命中命令词**的比例（与 DTW 可比的主指标）
- cer       = 字符错误率（编辑距离 / 参考长度，跨切分平均）
- 转写文本原样保留在 per_row，便于人工核查

产物：reports/t-asr-<日期>/eval_summary.json（DTW 与自由听写同文件不同 backend 字段，不互相覆盖）
"""

import argparse
import json
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.asr import DtwCommandRecognizer, extract_features, load_wav_mono  # noqa: E402

DATASET_DIR = REPO / "SmartOps-Dataset" / "asr"


def _rows(split):
    out = []
    for line in (DATASET_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["split"] == split:
                out.append(row)
    return out


def _normalize(text):
    """中文命令词判定用：统一兼容形式并去掉空白与标点。

    whisper 会给命令词带上句读（如「打开知识库。」），参考文本不带；不归一化
    会把这类等价输出判成失配。NFKC 先折叠全角/兼容字符，再按 Unicode 类别
    剔除标点（P*）与分隔符（Z*，含全角空格）。
    """
    cleaned = unicodedata.normalize("NFKC", (text or "").strip())
    return "".join(
        ch for ch in cleaned if not unicodedata.category(ch).startswith(("P", "Z"))
    )


def _output_path(out_dir, backend, model=None):
    """产物文件名按 backend（与 model 规格）区分，避免不同规格互相覆盖。

    DTW 与自由听写的结论不可混用；同一 backend 换模型规格（base/medium/...）
    结论也不同，必须各自留文件。
    """
    if backend == "dtw":
        return Path(out_dir) / "eval_summary.json"
    suffix = f"-{backend}" + (f"-{model}" if model else "")
    return Path(out_dir) / f"eval_summary{suffix}.json"


def _load_mono_16k(path, target_rate=16000):
    """读取 WAV 并重采样到 16kHz float32。

    冻结集是 ZipVoice TTS 的 **8kHz** 产物；whisper 系模型要求 16kHz，
    直接喂 8k 会触发语言误判并产出幻觉文本（实测："你不认识…"/"This is the end of
    the video."）。这里做零依赖线性插值重采样，不引入 scipy/soundfile 之外的新依赖。
    """
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


def evaluate_split_faster_whisper(model, split, beam_size):
    rows = _rows(split)
    correct = 0
    per_label = {}
    per_row = []
    total_chars = 0
    total_errors = 0
    empty_count = 0
    started = time.time()
    for row in rows:
        audio = _load_mono_16k(DATASET_DIR / row["path"])
        segments, info = model.transcribe(audio, language="zh", beam_size=beam_size)
        text = "".join(seg.text for seg in segments).strip()
        if not text:
            empty_count += 1
        ref = row.get("text") or row["label"]
        ok = _normalize(text) == _normalize(ref)
        correct += ok
        total_chars += len(_normalize(ref)) or 1
        total_errors += _edit_distance(_normalize(text), _normalize(ref))
        stats = per_label.setdefault(row["label"], {"n": 0, "correct": 0})
        stats["n"] += 1
        stats["correct"] += ok
        per_row.append({
            "sample": row["path"],
            "ref": ref,
            "hyp": text,
            "detected_language": info.language,
            "correct": ok,
        })
    elapsed = time.time() - started
    return {
        "split": split,
        "n": len(rows),
        "correct": correct,
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "cer": round(total_errors / total_chars, 4) if total_chars else None,
        "empty_rate": round(empty_count / len(rows), 4) if rows else 0.0,
        "eval_seconds": round(elapsed, 1),
        "per_label": per_label,
        "per_row": per_row,
    }


def _edit_distance(a, b):
    """纯 stdlib Levenshtein（cer 用），避免新增依赖。"""
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


def evaluate_split_dtw(recognizer, split):
    rows = _rows(split)
    correct = 0
    distances = []
    per_label = {}
    started = time.time()
    for row in rows:
        features = extract_features(load_wav_mono(DATASET_DIR / row["path"]))
        hit = recognizer.recognize(features)
        predicted = hit["label"] if hit else ""
        ok = predicted == row["label"]
        correct += ok
        if hit:
            distances.append(hit["distance"])
        stats = per_label.setdefault(row["label"], {"n": 0, "correct": 0})
        stats["n"] += 1
        stats["correct"] += ok
    elapsed = time.time() - started
    return {
        "split": split,
        "n": len(rows),
        "correct": correct,
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "avg_distance": round(sum(distances) / len(distances), 4) if distances else None,
        "eval_seconds": round(elapsed, 1),
        "per_label": per_label,
    }


def main():
    parser = argparse.ArgumentParser(description="评测 ASR 基线（dev+holdout 双集合）")
    parser.add_argument("--backend", choices=["dtw", "faster-whisper"], default="dtw")
    parser.add_argument("--templates", default=str(REPO / "agent" / "asr" / "templates.json"))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--model", default="base", help="faster-whisper 模型规格")
    parser.add_argument("--beam-size", type=int, default=5)
    args = parser.parse_args()

    modes = sorted(
        {
            json.loads(line).get("mode", "unknown")
            for line in (DATASET_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    )

    if args.backend == "faster-whisper":
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415
        except ImportError:
            raise SystemExit(
                "未安装 faster-whisper：pip install faster-whisper"
                "（模型需联网下载；官方不通时设 HF_ENDPOINT=https://hf-mirror.com）"
            )
        model = WhisperModel(args.model, device="cpu", compute_type="int8")
        model_name = f"faster-whisper-{args.model}"
        evaluate = lambda split: evaluate_split_faster_whisper(model, split, args.beam_size)  # noqa: E731
    else:
        recognizer = DtwCommandRecognizer.load(args.templates)
        model_name = recognizer.MODEL_VERSION
        evaluate = lambda split: evaluate_split_dtw(recognizer, split)  # noqa: E731

    results = [evaluate("dev"), evaluate("holdout")]
    summary = {
        "date": str(date.today()),
        "backend": args.backend,
        "model": model_name,
        "templates_path": args.templates if args.backend == "dtw" else None,
        "dataset_mode": modes[0] if len(modes) == 1 else modes,
        "note": (
            "dev 参与训练（DTW 中位模板），holdout 独立。"
            "若数据集为 --synthetic 自检模式，指标仅代表管线正确性，不代表真实语音。"
            "faster-whisper 是自由听写，accuracy 指归一化后完全命中命令词，cer 为字符错误率；"
            "两者与 DTW 的 accuracy 同口径可比，但 DTW 只覆盖受限命令集。"
        ),
        "results": results,
    }
    out_dir = Path(args.output_dir) if args.output_dir else REPO / "reports" / f"t-asr-{date.today()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _output_path(out_dir, args.backend, args.model if args.backend != "dtw" else None)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== ASR 评测（backend={args.backend}, model={model_name}）===")
    for result in results:
        extra = f" cer={result['cer']}" if result.get("cer") is not None else (
            f" 平均距离={result['avg_distance']}" if result.get("avg_distance") is not None else ""
        )
        print(
            f"[{result['split']}] n={result['n']} 正确={result['correct']} "
            f"准确率={result['accuracy']:.2%}{extra} 耗时={result['eval_seconds']}s"
        )
    print(f"明细: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
