"""P1-2 TinyBERT 日志分类前置过滤训练脚本。

目标：海量日志先过 TinyBERT 打标签 + 过滤 noise，相似告警合并；
     Agent 只处理聚合后的事件，防告警风暴。

mock 数据：8 类日志（oom/timeout/disk_full/connection_refused/process_crash/auth_error/network_error/noise），
noise 占 65%（模拟真实告警风暴里大多数是正常心跳/INFO 日志）。

评测指标：
  - macro-F1（类别不均衡下比 accuracy 有意义）
  - noise_precision（前置过滤场景最重要的指标——标记为 noise 的里有多少真 noise）
  - noise_recall（真 noise 里有多少被正确过滤掉）

用法：
    python scripts/train_p12_log_classifier.py --mock --variant tinybert --epochs 5 \
        --model-dir ../data/models/log_classifier --json ../data/lake/_eval/p12_log_eval.json
    python scripts/train_p12_log_classifier.py --mock --variant textcnn --epochs 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.log_model import (  # noqa: E402
    LABEL_SPACE,
    LABEL_TO_ID,
    NUM_LABELS,
    ID_TO_LABEL,
    available,
    heuristic_classify,
    keywords_to_ids,
)


MODE = available()


# ---------------------------------------------------------------------------
# Mock 日志生成器
# ---------------------------------------------------------------------------

TEMPLATE_BY_LABEL: dict[str, list[str]] = {
    "oom": [
        "java.lang.OutOfMemoryError: Java heap space in worker-{w}",
        "Process {p} killed, out of memory (RSS={m}MB)",
        "gc_pause_ms={t} heap_usage={h}% — possible OOM",
        "fatal: Cannot allocate memory for {p}",
    ],
    "timeout": [
        "request timeout after {t}ms from {c}",
        "context deadline exceeded calling {s}",
        "connect timeout {h}:{port} — dead peer",
        "rpc timeout in shard-{n}, queue backlog={q}",
    ],
    "disk_full": [
        "no space left on device /var/lib/docker on {h}",
        "disk usage {d}% on {h}, threshold 90%",
        "inode table full: {i} inodes used on {h}",
        "write failed: filesystem full at /data/db",
    ],
    "connection_refused": [
        "connect refused 10.0.{x}.{y}:{port}",
        "econnrefused while dialing {s}",
        "port {port} not listening on {h}, health check failed",
        "upstream {s} closed connection before response",
    ],
    "process_crash": [
        "segmentation fault (core dumped) by {p}",
        "python {p} exited with code -11",
        "killed {p}: segfault address 0x{x}",
        "panic: runtime error: nil pointer dereference",
    ],
    "auth_error": [
        "unauthorized 401 from {c} token expired",
        "403 forbidden accessing /api/admin by role viewer",
        "auth failed: invalid signature from {c}",
        "jwt verification failed: token expired at ts={t}",
    ],
    "network_error": [
        "dns lookup {h} failed: nxdomain",
        "connection reset by peer 10.0.{x}.{y}",
        "network unreachable to subnet 10.0.{x}.0/24",
        "packet loss {loss}% on interface eth0, latency {l}ms",
    ],
    "noise": [
        "heartbeat ok from pod-{w}",
        "health check passed: alive at ts={t}",
        "started worker-{w} successfully",
        "ready to accept connections on port {port}",
        "INFO: background job completed in {t}ms",
        "scheduled cleanup finished, freed {m}MB",
    ],
}

SERVERS = ["srv-api-01", "srv-api-02", "srv-cache-01", "srv-db-01", "srv-web-01"]
PROCESSES = ["java", "nginx", "redis-server", "python-worker", "postgres", "node", "kafka-broker"]


def generate_mock_logs(
    n_per_label: dict[str, int] | None = None,
    total: int = 1000,
    noise_ratio: float = 0.65,
    seed: int = 17,
) -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(seed)
    if n_per_label is None:
        n_noise = int(total * noise_ratio)
        n_other = (total - n_noise) // (NUM_LABELS - 1)
        n_per_label = {label: n_noise if label == "noise" else n_other for label in LABEL_SPACE}
        diff = total - sum(n_per_label.values())
        if diff != 0:
            first_label = next(l for l in LABEL_SPACE if l != "noise")
            n_per_label[first_label] += diff

    texts: list[str] = []
    labels: list[str] = []

    for label, n in n_per_label.items():
        templates = TEMPLATE_BY_LABEL[label]
        for _ in range(n):
            tmpl = templates[rng.integers(len(templates))]
            fmt = dict(
                w=rng.integers(1, 100),
                p=PROCESSES[rng.integers(len(PROCESSES))],
                m=rng.integers(500, 4000),
                h=SERVERS[rng.integers(len(SERVERS))],
                t=rng.integers(100, 60000),
                c=f"client-{rng.integers(1, 50)}",
                s=f"service-{rng.integers(1, 30)}",
                d=rng.integers(70, 100),
                i=rng.integers(90, 100),
                x=rng.integers(0, 255),
                y=rng.integers(0, 255),
                n=rng.integers(1, 10),
                q=rng.integers(1, 500),
                l=rng.integers(10, 500),
                port=rng.choice([80, 443, 8080, 5432, 6379, 3306]),
                loss=rng.integers(0, 30),
            )
            text = tmpl.format(**fmt)
            texts.append(text)
            labels.append(label)

    order = rng.permutation(len(texts))
    texts = [texts[i] for i in order]
    labels = [labels[i] for i in order]
    return texts, labels


# ---------------------------------------------------------------------------
# 训练
# ---------------------------------------------------------------------------

def train_tinybert(texts: list[str], labels: list[str], config) -> tuple[Any, Any]:
    """TinyBERT 训练：tokenize → forward → BCE/CELoss。返回 (model, tokenizer)。"""
    import torch
    from transformers import BertTokenizerFast
    from app.training.log_model import TinyBERTLogClassifier

    tokenizer = BertTokenizerFast.from_pretrained(config.model_name)
    model = TinyBERTLogClassifier(
        num_labels=NUM_LABELS,
        model_name=config.model_name,
        freeze_backbone=config.freeze_backbone,
        dropout=config.dropout,
    )

    # Tokenize
    enc = tokenizer(
        texts, padding=True, truncation=True,
        max_length=config.max_len, return_tensors="pt",
    )
    y = torch.tensor([LABEL_TO_ID[l] for l in labels], dtype=torch.long)

    dataset = torch.utils.data.TensorDataset(enc["input_ids"], enc["attention_mask"], y)
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=config.batch_size, shuffle=True,
    )

    torch.manual_seed(config.seed)
    optimizer = torch.optim.AdamW(model.classifier.parameters(), lr=config.lr)
    loss_fn = torch.nn.CrossEntropyLoss()

    model.train()
    for _ in range(config.epochs):
        for input_ids, attn_mask, target in loader:
            optimizer.zero_grad()
            logits = model(input_ids, attn_mask)
            loss = loss_fn(logits, target)
            loss.backward()
            optimizer.step()

    model.eval()
    return model, tokenizer


def train_textcnn(texts: list[str], labels: list[str], config) -> Any:
    """TextCNN 训练：关键词向量化 → Conv1d → 分类头。"""
    import torch
    from app.training.log_model import TextCNNLogClassifier, keywords_to_ids, KEYWORD_VOCAB

    model = TextCNNLogClassifier(
        num_labels=NUM_LABELS,
        vocab_size=len(KEYWORD_VOCAB) + 1,
        max_len=config.max_len,
    )

    ids = np.stack([keywords_to_ids(t, config.max_len) for t in texts])
    y = np.array([LABEL_TO_ID[l] for l in labels], dtype=np.int64)

    torch.manual_seed(config.seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    loss_fn = torch.nn.CrossEntropyLoss()

    dataset = torch.utils.data.TensorDataset(torch.tensor(ids), torch.tensor(y))
    loader = torch.utils.data.DataLoader(dataset, batch_size=config.batch_size, shuffle=True)

    model.train()
    for _ in range(config.epochs):
        for input_ids, target in loader:
            optimizer.zero_grad()
            logits = model(input_ids)
            loss = loss_fn(logits, target)
            loss.backward()
            optimizer.step()

    model.eval()
    return model


# ---------------------------------------------------------------------------
# 评测
# ---------------------------------------------------------------------------

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """macro-F1 + noise_precision/recall（前置过滤核心指标）。"""
    n_classes = NUM_LABELS
    tp = np.zeros(n_classes, dtype=float)
    fp = np.zeros(n_classes, dtype=float)
    fn = np.zeros(n_classes, dtype=float)
    for t, p in zip(y_true, y_pred):
        if t == p:
            tp[t] += 1
        else:
            fp[p] += 1
            fn[t] += 1

    precision = np.where(tp + fp > 0, tp / (tp + fp + 1e-9), 0)
    recall = np.where(tp + fn > 0, tp / (tp + fn + 1e-9), 0)
    f1 = 2 * precision * recall / (precision + recall + 1e-9)
    macro_f1 = float(f1.mean())

    # noise 专项
    noise_idx = LABEL_TO_ID["noise"]
    noise_precision = float(precision[noise_idx])
    noise_recall = float(recall[noise_idx])

    # accuracy（参考）
    accuracy = float((y_true == y_pred).mean())

    per_label = {}
    for i, label in enumerate(LABEL_SPACE):
        per_label[label] = {
            "precision": round(float(precision[i]), 4),
            "recall": round(float(recall[i]), 4),
            "f1": round(float(f1[i]), 4),
            "support": int(tp[i] + fn[i]),
        }

    return {
        "macro_f1": round(macro_f1, 4),
        "accuracy": round(accuracy, 4),
        "noise_precision": round(noise_precision, 4),
        "noise_recall": round(noise_recall, 4),
        "per_label": per_label,
    }


def run_benchmark(texts: list[str], labels: list[str], config) -> dict[str, Any]:
    """train/test split（80/20）→ 训练 → 评测 → 对比 heuristic。"""
    import torch

    n = len(texts)
    rng = np.random.default_rng(42)
    idx = rng.permutation(n)
    cut = int(n * 0.8)
    train_idx = idx[:cut]
    test_idx = idx[cut:]

    train_texts = [texts[i] for i in train_idx]
    train_labels = [labels[i] for i in train_idx]
    test_texts = [texts[i] for i in test_idx]
    test_labels = [labels[i] for i in test_idx]
    y_true = np.array([LABEL_TO_ID[l] for l in test_labels])

    # Heuristic baseline
    heur_pred = np.array([LABEL_TO_ID[heuristic_classify(t)[0]] for t in test_texts])
    heur_metrics = compute_metrics(y_true, heur_pred)

    report: dict[str, Any] = {
        "mode": MODE,
        "variant": config.variant,
        "num_train": len(train_texts),
        "num_test": len(test_texts),
        "heuristic": heur_metrics,
    }

    # TinyBERT
    if config.variant == "tinybert" and MODE != "heuristic":
        print("  training TinyBERT...")
        model, tokenizer = train_tinybert(train_texts, train_labels, config)
        enc = tokenizer(test_texts, padding=True, truncation=True, max_length=config.max_len, return_tensors="pt")
        with torch.no_grad():
            logits = model(enc["input_ids"], enc["attention_mask"])
        y_pred = logits.argmax(-1).numpy()
        report["tinybert"] = compute_metrics(y_true, y_pred)
    elif config.variant == "textcnn" and MODE != "heuristic":
        print("  training TextCNN...")
        model = train_textcnn(train_texts, train_labels, config)
        ids = np.stack([keywords_to_ids(t, config.max_len) for t in test_texts])
        with torch.no_grad():
            logits = model(torch.tensor(ids))
        y_pred = logits.argmax(-1).numpy()
        report["textcnn"] = compute_metrics(y_true, y_pred)
    else:
        print(f"  ⚠️  variant={config.variant} 不可用（mode={MODE}），只输出 heuristic")

    return report


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="生成 mock 日志训练评测")
    parser.add_argument("--total", type=int, default=1000, help="mock 日志总数")
    parser.add_argument("--noise-ratio", type=float, default=0.65)
    parser.add_argument("--variant", choices=["tinybert", "textcnn"], default="tinybert")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--max-len", type=int, default=64)
    parser.add_argument("--freeze-backbone", action="store_true", default=True)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    print(f"mode={MODE}  variant={args.variant}  total={args.total}  noise_ratio={args.noise_ratio}")

    if args.mock:
        texts, labels = generate_mock_logs(total=args.total, noise_ratio=args.noise_ratio)
        print(f"generated {len(texts)} mock logs, {sum(1 for l in labels if l == 'noise')} noise")
    else:
        print("⚠️  真实 inspector_event 导出待实现，请用 --mock")
        return 1

    from app.training.log_model import LogClassifierConfig
    config = LogClassifierConfig(
        variant=args.variant,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_len=args.max_len,
        freeze_backbone=args.freeze_backbone,
    )

    report = run_benchmark(texts, labels, config)

    # 打印
    print(f"\n评测汇总（mode={report['mode']}, variant={report['variant']}）")
    cols = ["heuristic"]
    if "tinybert" in report:
        cols.append("tinybert")
    if "textcnn" in report:
        cols.append("textcnn")
    header = f"{'metric':<18}" + "".join(f"{c:>12}" for c in cols) + f"{'Δ vs h':>10}"
    print(header)
    for metric in ("macro_f1", "accuracy", "noise_precision", "noise_recall"):
        base = report["heuristic"][metric]
        row = f"{metric:<18}"
        best_name = cols[-1] if len(cols) > 1 else "heuristic"
        best_val = report[best_name][metric]
        for c in cols:
            row += f"{report[c][metric]:>12.3f}"
        row += f"{best_val - base:>+10.3f}" if best_name != "heuristic" else f"{'—':>10}"
        print(row)

    # per-label 打印（仅 deep model）
    for name in cols[1:]:
        if name in report:
            print(f"\n{name} per-label F1:")
            for label in LABEL_SPACE:
                pl = report[name]["per_label"][label]
                support = pl["support"]
                print(f"  {label:<22} F1={pl['f1']:.3f} prec={pl['precision']:.3f} rec={pl['recall']:.3f} n={support}")

    # 保存模型
    if args.model_dir and MODE != "heuristic":
        import torch
        args.model_dir.mkdir(parents=True, exist_ok=True)
        save_path = args.model_dir / "log_classifier.pt"

        if args.variant == "tinybert":
            from transformers import BertTokenizerFast
            from app.training.log_model import TinyBERTLogClassifier

            tokenizer = BertTokenizerFast.from_pretrained(config.model_name)
            model = TinyBERTLogClassifier(
                num_labels=NUM_LABELS, model_name=config.model_name,
                freeze_backbone=config.freeze_backbone, dropout=config.dropout,
            )
            torch.save({
                "variant": "tinybert",
                "model_name": config.model_name,
                "max_len": config.max_len,
                "model_state": model.state_dict(),
            }, save_path)
            # tokenizer 也存一下
            tokenizer.save_pretrained(args.model_dir / "tokenizer")
        else:
            from app.training.log_model import TextCNNLogClassifier, KEYWORD_VOCAB

            model = TextCNNLogClassifier(vocab_size=len(KEYWORD_VOCAB) + 1, max_len=config.max_len)
            torch.save({
                "variant": "textcnn",
                "max_len": config.max_len,
                "vocab_size": len(KEYWORD_VOCAB) + 1,
                "model_state": model.state_dict(),
            }, save_path)

        print(f"\n模型 ({args.variant}) → {save_path}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
