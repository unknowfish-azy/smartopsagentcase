"""PatchTST 时序预测与显式降级测试。"""

from pathlib import Path

import numpy as np
import pytest

from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services import forecast_detector
from app.training.patchtst_model import normalize_series


def _request(**kwargs):
    values = np.linspace(20, 40, 80).tolist()
    return ForecastRequest(values=values, horizon=6, metric_name="cpu", **kwargs)


def test_normalize_series_round_trip():
    values = np.array([1.0, 2.0, 3.0, 4.0])
    normalized, center, scale = normalize_series(values)
    assert normalized.mean() == pytest.approx(0.0)
    assert np.allclose(normalized * scale + center, values)


def test_linear_fallback_forecast_shape_and_interval():
    forecast_detector.init_model(model_path=Path("not-exist-patchtst.pt"))
    response = ForecastResponse(**forecast_detector.forecast(_request()))
    assert response.mode == "linear"
    assert response.model_status == "fallback"
    assert len(response.points) == 6
    assert response.points[-1].value > response.points[0].value
    for point in response.points:
        assert point.lower <= point.value <= point.upper
    assert "不代表故障或恶化概率" in response.risk_basis[-1]


def test_seasonal_naive_fallback():
    forecast_detector.init_model(model_path=Path("not-exist-patchtst.pt"))
    values = [1.0, 2.0, 3.0, 2.0] * 8
    request = ForecastRequest(values=values, horizon=4, seasonal_period=4)
    result = forecast_detector.forecast(request)
    assert result["mode"] == "seasonal_naive"
    assert [p["value"] for p in result["points"]] == [1.0, 2.0, 3.0, 2.0]


def test_threshold_breach_enters_risk_basis():
    forecast_detector.init_model(model_path=Path("not-exist-patchtst.pt"))
    result = forecast_detector.forecast(_request(upper_threshold=41.0))
    assert result["risk_score"] > 0
    assert any("超过上限" in item for item in result["risk_basis"])


def test_patchtst_forward_and_predict_shape():
    torch = pytest.importorskip("torch")
    from app.training.patchtst_model import PatchTST

    model = PatchTST(context_length=32, horizon=4, patch_len=8, stride=4, d_model=16, nhead=4, num_layers=1)
    x = torch.randn(2, 32)
    assert model(x).shape == (2, 4)
    prediction = model.predict_normalized(x[0].numpy(), horizon=2)
    assert prediction.shape == (2,)


def test_checkpoint_round_trip_uses_patchtst(tmp_path):
    torch = pytest.importorskip("torch")
    from app.training.patchtst_model import NORMALIZATION, PatchTST

    model = PatchTST(context_length=32, horizon=6, patch_len=8, stride=4, d_model=16, nhead=4, num_layers=1)
    path = tmp_path / "patchtst.pt"
    torch.save({
        "config": model.config(),
        "model_state": model.state_dict(),
        "normalization": NORMALIZATION,
        "residual_std": [0.1] * 6,
    }, path)

    state = forecast_detector.init_model(model_path=path)
    assert state.kind == "patchtst"
    result = forecast_detector.forecast(ForecastRequest(values=np.linspace(1, 20, 40).tolist(), horizon=6))
    assert result["mode"] == "patchtst"
    assert result["model_status"] == "ok"
    assert len(result["points"]) == 6


def test_invalid_threshold_order_rejected():
    with pytest.raises(ValueError):
        _request(upper_threshold=10, lower_threshold=20)
