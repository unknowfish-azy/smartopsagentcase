"""P2-1 处置动作效果预测训练脚本。

任务：给定（故障 category, severity, 建议动作）→ 预测
  1. success_prob         — 动作解决问题的概率
  2. secondary_risk_prob  — 动作引发次生故障的概率

数据源：agent_decision_loop（真实 MySQL 表 + mock fallback）
评测指标：BCE loss + success_auc + risk_auc

用法：
    python scripts/train_p21_action_effect.py --mock
    python scripts/train_p21_action_effect.py --mock --epochs 80 --json ../data/lake/_eval/p21_action.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.action_model import (  # noqa: E402
    CATEGORIES, CATEGORY_TO_ID,
    ACTIONS, ACTION_TO_ID,
    encode_batch, encode_features,
    heuristic_predict,
    ActionEffectMLP, ActionEffectConfig,
    available, _TORCH_AVAILABLE,
)


# ---------------------------------------------------------------------------
# Mock 训练数据（模拟 agent_decision_loop 里的 action + outcome 记录）
# ---------------------------------------------------------------------------

# (category, action, outcome_success, outcome_secondary_risk, count)
# outcome_success  = 1 if resolved else 0
# outcome_secondary_risk = 1 if 执行这个动作后出现了额外告警
INTERACTION_TABLE: list[tuple[str, str, float, float, int]] = [
    # OOM — scale_out 最稳，restart 也稳，code_fix 根因但周期长
    ("oom", "scale_out", 0.85, 0.05, 20),
    ("oom", "restart", 0.75, 0.15, 25),
    ("oom", "manual_cleanup", 0.5, 0.05, 8),
    ("oom", "wait_and_observe", 0.1, 0.0, 10),
    # Timeout — rollback 最稳，scale_out 有效但要确认
    ("timeout", "rollback", 0.9, 0.05, 15),
    ("timeout", "scale_out", 0.65, 0.1, 18),
    ("timeout", "config_change", 0.55, 0.25, 10),
    ("timeout", "wait_and_observe", 0.2, 0.0, 12),
    # Disk Full — manual_cleanup 最直接
    ("disk_full", "manual_cleanup", 0.9, 0.05, 20),
    ("disk_full", "restart", 0.3, 0.1, 8),
    ("disk_full", "scale_out", 0.1, 0.0, 5),
    # Process Crash — restart 紧急，rollback 根治
    ("process_crash", "restart", 0.7, 0.2, 22),
    ("process_crash", "rollback", 0.85, 0.05, 15),
    ("process_crash", "code_fix", 0.95, 0.0, 10),
    # Connection Refused — restart 高频有效
    ("connection_refused", "restart", 0.8, 0.15, 25),
    ("connection_refused", "wait_and_observe", 0.3, 0.0, 10),
    # Auth Error — config_change / rollback
    ("auth_error", "config_change", 0.8, 0.05, 15),
    ("auth_error", "rollback", 0.9, 0.05, 12),
    # Network Error — restart + wait
    ("network_error", "restart", 0.6, 0.1, 15),
    ("network_error", "wait_and_observe", 0.5, 0.0, 10),
]

SEVERITY_POOL = ["P0", "P1", "P1", "P2", "P2", "P3"]


def generate_mock_data(seed: int = 17) -> dict[str, list[Any]]:
    """展开 INTERACTION_TABLE × severity pool → 训练样本字典。"""
    rng = np.random.default_rng(seed)
    cats, sevs, acts = [], [], []
    y_success, y_risk = [], []

    for cat, act, succ, risk, count in INTERACTION_TABLE:
        for _ in range(count):
            sev = rng.choice(SEVERITY_POOL)
            cats.append(cat)
            sevs.append(sev)
            acts.append(act)
            # severity P0/P1 成功概率稍微降（紧急场景更难处理）
            sev_penalty = 0.05 if sev in ("P0", "P1") else 0.0
            y_success.append(max(0.0, min(1.0, succ - sev_penalty + rng.normal(0, 0.1))))
            y_risk.append(max(0.0, min(1.0, risk + rng.normal(0, 0.08))))

    return {"category": cats, "severity": sevs, "action": acts,
            "success": y_success, "risk": y_risk}


# ---------------------------------------------------------------------------
# 训练
# ---------------------------------------------------------------------------

def train_mlp(data: dict[str, list], config: ActionEffectConfig) -> Any:
    """双任务 MLP 训练。"""
    import torch
    from app.training.action_model import ActionEffectMLP, encode_batch

    X = encode_batch(data["category"], data["severity"], data["action"])
    y_succ = np.array(data["success"], dtype=np.float32)
    y_risk = np.array(data["risk"], dtype=np.float32)

    torch.manual_seed(config.seed)
    model = ActionEffectMLP(
        num_categories=len(CATEGORIES), num_actions=len(ACTIONS),
        hidden1=config.hidden1, hidden2=config.hidden2, dropout=config.dropout,
    )

    X_t = torch.tensor(X)
    y_s_t = torch.tensor(y_succ)
    y_r_t = torch.tensor(y_risk)

    dataset = torch.utils.data.TensorDataset(X_t, y_s_t, y_r_t)
    loader = torch.utils.data.DataLoader(dataset, batch_size=config.batch_size, shuffle=True)

    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    loss_fn = torch.nn.BCELoss()

    model.train()
    for _ in range(config.epochs):
        for xb, ys, yr in loader:
            optimizer.zero_grad()
            pred_s, pred_r = model(xb)
            loss = loss_fn(pred_s, ys) + loss_fn(pred_r, yr)  # 双任务加和
            loss.backward()
            optimizer.step()

    model.eval()
    return model


# ---------------------------------------------------------------------------
# 评测
# ---------------------------------------------------------------------------

def compute_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """最小可用 AUC（ROC 曲线下面积，简单但足够比较）。"""
    if len(y_true) < 2 or len(np.unique(y_true)) < 2:
        return 0.5
    pairs = 0
    wins = 0
    for i in range(len(y_true)):
        if y_true[i] == 1:
            for j in range(len(y_true)):
                if y_true[j] == 0:
                    pairs += 1
                    if y_prob[i] > y_prob[j]:
                        wins += 1
                    elif y_prob[i] == y_prob[j]:
                        wins += 0.5
    return wins / pairs if pairs > 0 else 0.5


def evaluate(data: dict[str, list], model=None) -> dict[str, Any]:
    """评测：success_auc + risk_auc + success_mae（heuristic baseline + MLP）。"""
    report: dict[str, Any] = {"mode": available(), "num_samples": len(data["category"])}

    # Heuristic baseline
    h_succ, h_risk = [], []
    for cat, sev, act in zip(data["category"], data["severity"], data["action"]):
        s, r, _ = heuristic_predict(cat, sev, act)
        h_succ.append(s)
        h_risk.append(r)
    y_succ_bin = (np.array(data["success"]) >= 0.5).astype(int)
    y_risk_bin = (np.array(data["risk"]) >= 0.5).astype(int)
    report["heuristic"] = {
        "success_auc": round(compute_auc(y_succ_bin, np.array(h_succ)), 4),
        "risk_auc": round(compute_auc(y_risk_bin, np.array(h_risk)), 4),
    }

    # MLP
    if model is not None and _TORCH_AVAILABLE:
        import torch
        from app.training.action_model import encode_batch
        X = encode_batch(data["category"], data["severity"], data["action"])
        with torch.no_grad():
            p_s, p_r = model(torch.tensor(X))
        p_s_np = p_s.numpy()
        p_r_np = p_r.numpy()
        report["mlp"] = {
            "success_auc": round(compute_auc(y_succ_bin, p_s_np), 4),
            "risk_auc": round(compute_auc(y_risk_bin, p_r_np), 4),
            "success_mae": round(float(np.mean(np.abs(p_s_np - np.array(data["success"])))), 4),
            "risk_mae": round(float(np.mean(np.abs(p_r_np - np.array(data["risk"])))), 4),
        }

    return report


def run_benchmark(config: ActionEffectConfig) -> dict[str, Any]:
    """80/20 split → 训练 → 评测。"""
    import torch
    data = generate_mock_data()
    n = len(data["category"])
    rng = np.random.default_rng(42)
    idx = rng.permutation(n)
    cut = int(n * 0.8)
    train_idx = idx[:cut]
    test_idx = idx[cut:]

    train_data = {k: [v[i] for i in train_idx] for k, v in data.items()}
    test_data = {k: [v[i] for i in test_idx] for k, v in data.items()}

    print(f"  train={len(train_data['category'])} test={len(test_data['category'])}")
    print("  training ActionEffectMLP...")
    model = train_mlp(train_data, config)
    return evaluate(test_data, model)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="用 mock agent_decision_loop 数据")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    print(f"mode={available()}")

    if args.mock:
        report = run_benchmark(ActionEffectConfig(epochs=args.epochs, lr=args.lr))
    else:
        print("⚠️  真实 DB 读取待实现，请用 --mock")
        return 1

    print(f"\n评测汇总（mode={report['mode']}, n={report['num_samples']}）")
    cols = ["heuristic"]
    if "mlp" in report:
        cols.append("mlp")
    header = f"{'metric':<16}" + "".join(f"{c:>12}" for c in cols)
    print(header)
    for metric in ("success_auc", "risk_auc"):
        row = f"{metric:<16}"
        for c in cols:
            row += f"{report[c][metric]:>12.3f}"
        if len(cols) > 1:
            row += f"  Δ={report.get('mlp', report['heuristic'])[metric] - report['heuristic'][metric]:+.3f}"
        print(row)
    if "mlp" in report:
        for metric in ("success_mae", "risk_mae"):
            print(f"{metric:<16}{report['mlp'][metric]:>12.3f}")

    # 保存
    if args.model_dir and _TORCH_AVAILABLE:
        import torch
        args.model_dir.mkdir(parents=True, exist_ok=True)
        from app.training.action_model import ActionEffectMLP
        model = ActionEffectMLP(num_categories=len(CATEGORIES), num_actions=len(ACTIONS))
        save_path = args.model_dir / "action_effect.pt"
        torch.save({
            "num_categories": len(CATEGORIES),
            "num_actions": len(ACTIONS),
            "hidden1": 32, "hidden2": 16, "dropout": 0.2,  # 与 ActionEffectMLP 默认参数对齐
            "model_state": model.state_dict(),
        }, save_path)
        print(f"\n模型 → {save_path}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
