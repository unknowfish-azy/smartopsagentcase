"""GCN/GAT 推理状态回归测试。"""

import numpy as np
import pytest

from app.schemas.rootcause import AlertNode, RootCauseRequest, RootCauseResponse
from app.services import rootcause_detector


@pytest.mark.parametrize("kind", ["pyg_gat", "pytorch_gat", "pyg_gcn", "pytorch_gcn"])
def test_loaded_deep_models_report_ok(monkeypatch, kind):
    state = rootcause_detector._ModelState(kind=kind, model=object())
    monkeypatch.setattr(rootcause_detector, "_state", state)
    monkeypatch.setattr(rootcause_detector, "_TORCH_AVAILABLE", True)
    monkeypatch.setattr(
        rootcause_detector,
        "_score_deep",
        lambda _state, nodes, _edge_index, _edge_weight: np.linspace(0.1, 0.9, len(nodes)),
    )
    request = RootCauseRequest(nodes=[AlertNode(alert_id="a"), AlertNode(alert_id="b")])

    response = RootCauseResponse(**rootcause_detector.detect(request))

    assert response.mode == kind
    assert response.model_status == "ok"
    assert response.candidates[0].alert_id == "b"


def test_heuristic_reports_unavailable(monkeypatch):
    monkeypatch.setattr(
        rootcause_detector,
        "_state",
        rootcause_detector._ModelState(kind="heuristic", reason="无权重"),
    )
    request = RootCauseRequest(nodes=[AlertNode(alert_id="a")])
    result = rootcause_detector.detect(request)
    assert result["mode"] == "heuristic"
    assert result["model_status"] == "unavailable"
    assert result["extra"]["reason"] == "无权重"
