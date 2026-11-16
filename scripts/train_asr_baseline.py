"""
训练 ASR DTW 命令词基线。

读取 SmartOps-Dataset/asr/manifest.jsonl 的 dev 划分，逐条提取特征并训练
中位模板，落盘 agent/asr/templates.json（工具运行时默认加载）。

红线：只用 dev 划分训练；holdout 绝不参与训练。
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.asr import DtwCommandRecognizer, extract_features, load_wav_mono  # noqa: E402

DATASET_DIR = REPO / "SmartOps-Dataset" / "asr"
TEMPLATE_PATH = REPO / "agent" / "asr" / "templates.json"


def load_split(split):
    samples = {}
    modes = set()
    manifest = DATASET_DIR / "manifest.jsonl"
    if not manifest.exists():
        raise FileNotFoundError(f"未找到数据集清单: {manifest}，请先运行 scripts/build_asr_dataset.py")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["split"] != split:
            continue
        modes.add(row.get("mode", "unknown"))
        wav = DATASET_DIR / row["path"]
        samples.setdefault(row["label"], []).append(
            extract_features(load_wav_mono(wav))
        )
    return samples, modes


def main():
    parser = argparse.ArgumentParser(description="训练 DTW 命令词基线")
    parser.add_argument("--output", default=str(TEMPLATE_PATH))
    args = parser.parse_args()

    started = time.time()
    dev, modes = load_split("dev")
    if not dev:
        print("dev 划分为空，无法训练", file=sys.stderr)
        return 1
    if len(modes) > 1:
        print(f"警告：dev 划分混有多种数据来源 {modes}", file=sys.stderr)
    dataset_mode = modes.pop() if modes else "unknown"
    recognizer = DtwCommandRecognizer().train(dev, dataset_mode=dataset_mode)
    recognizer.save(args.output)
    elapsed = time.time() - started
    print(
        f"训练完成: {len(recognizer.templates)} 类模板 "
        f"({sum(len(v) for v in dev.values())} 条 dev 样本, dataset_mode={dataset_mode}, {elapsed:.1f}s)"
    )
    if dataset_mode == "synthetic":
        print("⚠️ 当前模板来自 --synthetic 管线自检数据，禁止用于真实语音识别。")
    print(f"模板: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
