"""P2-1 处置动作效果预测推理服务。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

_TORCH_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None

from ..training.action_model import (  # noqa: E402
    CATEGORIES, NUM_CATEGORIES,
    ACTIONS, NUM_ACTIONS,
    encode_batch, encode_features,
    heuristic_predict,
)


@dataclass
class _State:
    mode: Literal["mlp", "heuristic"] = "heuristic"
    reason: str | None = None
    model: Any = None


_state: _State | None = None


def init_model(model_path: Path | None = None) -> _State:
    global _state
    state = _State()

    if not _TORCH_AVAILABLE:
        state.reason = "torch 未安装，降级为 heuristic 规则"
        _state = state
        return state

    # 默认路径（和训练脚本 --model-dir 对齐）
    if model_path is None:
        model_path = Path(__file__).resolve().parents[3] / "data" / "models" / "action_effect" / "action_effect.pt"

    if model_path and model_path.exists():
        try:
            from ..training.action_model import ActionEffectMLP
            ckpt = torch.load(model_path, map_location="cpu")
            model = ActionEffectMLP(
                num_categories=ckpt.get("num_categories", NUM_CATEGORIES),
                num_actions=ckpt.get("num_actions", NUM_ACTIONS),
            )
            model.load_state_dict(ckpt["model_state"])
            model.eval()
            state.model = model
            state.mode = "mlp"
            _state = state
            return state
        except Exception as exc:
            state.reason = f"权重加载失败({exc})，降级为 heuristic"

    state.reason = f"未找到 action_effect.pt at {model_path}，降级为 heuristic 规则"
    _state = state
    return state


def get_state() -> _State:
    global _state
    if _state is None:
        return init_model()
    return _state


def predict(request) -> dict:
    state = get_state()

    category = request.category
    severity = request.severity
    actions = request.actions

    if state.mode == "mlp" and state.model is not None and _TORCH_AVAILABLE:
        X = encode_batch(
            [category] * len(actions),
            [severity] * len(actions),
            list(actions),
        )
        with torch.no_grad():
            p_s, p_r = state.model(torch.tensor(X))
        success = p_s.numpy().tolist()
        risk = p_r.numpy().tolist()
    else:
        success, risk = [], []
        for act in actions:
            s, r, _ = heuristic_predict(category, severity, act)
            success.append(s)
            risk.append(r)

    results = []
    for i, act in enumerate(actions):
        s = float(success[i])
        r = float(risk[i])
        results.append({
            "action": act,
            "success_prob": round(s, 4),
            "secondary_risk": round(r, 4),
            "risk_score": round((1 - s) + r, 4),
        })

    # 按 risk_score 升序排（越小越安全）
    results.sort(key=lambda x: x["risk_score"])

    return {
        "ok": True,
        "mode": state.mode,
        "category": category,
        "severity": severity,
        "results": results,
    }


def get_model_info() -> dict:
    state = get_state()
    return {
        "available": state.mode != "unavailable",
        "kind": state.mode,
        "reason": state.reason,
    }
