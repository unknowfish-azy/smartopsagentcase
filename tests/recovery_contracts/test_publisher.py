"""N06：契约上报客户端的字段映射、鉴权头与失败透传。

只验证"上报了什么、失败是否被吞掉"，不重复验证 Backend 语义：
平台侧准入/不变式由后端测试负责（``RecoveryContractServiceTest``）。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest

from agent.recovery_contracts import (
    IDEMPOTENCY_PREFIX,
    INTERNAL_TOKEN_HEADER,
    Claim,
    PublisherConfigError,
    RecoveryContract,
    RecoveryPublisher,
    RecoveryPublisherError,
    verify,
)
from agent.recovery_contracts.receipts import InvalidationEvent

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASE = "http://127.0.0.1:8080"
TOKEN = "test-internal-token"


def _case(name: str = "positive") -> dict:
    return json.loads((FIXTURES / f"vp01-{name}.json").read_text(encoding="utf-8"))


def _objects(name: str = "positive"):
    case = _case(name)
    return (
        case,
        RecoveryContract.from_dict(case["input"]["contract"]),
        Claim.from_dict(case["input"]["claim"]),
    )


def _receipt(name: str = "positive", *, receipt_id: str = "rcpt-publisher"):
    case, contract, claim = _objects(name)
    return (
        case,
        verify(
            contract,
            claim,
            case["input"]["observations"],
            case["decision_time"],
            run_id=case["run_id"],
            verification_round=case["verification_round"],
            authorized_scopes=[contract.scope],
            receipt_id=receipt_id,
        ),
    )


class _FakeResponse:
    def __init__(self, payload: dict | bytes, status: int = 200) -> None:
        self.status = status
        self._body = (
            payload if isinstance(payload, bytes)
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def _install(monkeypatch, response) -> list:
    calls: list = []

    def fake_urlopen(request, timeout=None):
        calls.append((request, timeout))
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    return calls


def _publisher() -> RecoveryPublisher:
    return RecoveryPublisher(BASE, TOKEN)


def _body(request) -> dict:
    return json.loads(request.data.decode("utf-8"))


def _http_error(status: int, payload: dict) -> urllib_error.HTTPError:
    return urllib_error.HTTPError(
        BASE,
        status,
        "rejected",
        {},
        io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# 配置缺失：不得降级为"跳过上报"
# ---------------------------------------------------------------------------

def test_missing_backend_url_is_config_error(monkeypatch):
    monkeypatch.delenv("SMARTOPS_BACKEND_URL", raising=False)
    monkeypatch.setenv("SMARTOPS_INTERNAL_TOKEN", TOKEN)
    with pytest.raises(PublisherConfigError) as error:
        RecoveryPublisher()
    assert "SMARTOPS_BACKEND_URL" in str(error.value)


def test_missing_internal_token_is_config_error(monkeypatch):
    monkeypatch.setenv("SMARTOPS_BACKEND_URL", BASE)
    monkeypatch.delenv("SMARTOPS_INTERNAL_TOKEN", raising=False)
    with pytest.raises(PublisherConfigError) as error:
        RecoveryPublisher()
    assert "SMARTOPS_INTERNAL_TOKEN" in str(error.value)


def test_blank_values_are_treated_as_missing(monkeypatch):
    monkeypatch.setenv("SMARTOPS_BACKEND_URL", "  ")
    monkeypatch.setenv("SMARTOPS_INTERNAL_TOKEN", "  ")
    with pytest.raises(PublisherConfigError):
        RecoveryPublisher()


def test_env_is_read_when_arguments_are_omitted(monkeypatch):
    monkeypatch.setenv("SMARTOPS_BACKEND_URL", BASE + "/")
    monkeypatch.setenv("SMARTOPS_INTERNAL_TOKEN", TOKEN)
    publisher = RecoveryPublisher()
    assert publisher.backend_url == BASE


# ---------------------------------------------------------------------------
# 契约登记
# ---------------------------------------------------------------------------

def test_create_contract_maps_fields_and_headers(monkeypatch):
    _, contract, claim = _objects()
    calls = _install(
        monkeypatch,
        _FakeResponse({"code": 200, "message": "success",
                       "data": {"id": 11, "contractId": contract.id,
                                "digest": contract.digest, "idempotentReplay": False}}),
    )

    result = _publisher().create_contract(contract, claim, owner_user_id=7, run_id=42)

    assert result["id"] == 11
    assert result["idempotentReplay"] is False
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == BASE + "/api/internal/recovery/contracts"
    assert request.method == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header(INTERNAL_TOKEN_HEADER.capitalize()) == TOKEN
    assert timeout == 10.0

    body = _body(request)
    assert body["ownerUserId"] == 7
    assert body["runId"] == 42
    assert body["idempotencyKey"] == IDEMPOTENCY_PREFIX + contract.digest
    assert body["contract"]["digest"] == contract.digest
    assert body["contract"]["target"]["target_id"] == contract.target.target_id
    assert body["claim"]["id"] == claim.id
    assert body["claim"]["contract_digest"] == contract.digest


def test_create_contract_accepts_raw_mappings_and_custom_key(monkeypatch):
    case, contract, _ = _objects()
    calls = _install(
        monkeypatch,
        _FakeResponse({"code": 200, "data": {"id": 3, "contractId": contract.id,
                                             "digest": contract.digest,
                                             "idempotentReplay": True}}),
    )
    result = _publisher().create_contract(
        case["input"]["contract"],
        case["input"]["claim"],
        owner_user_id=7,
        run_id=42,
        idempotency_key="batch-20261106-001",
        valid_from="2026-11-06T01:00:00Z",
    )
    assert result["idempotentReplay"] is True
    body = _body(calls[0][0])
    assert body["idempotencyKey"] == "batch-20261106-001"
    assert body["validFrom"] == "2026-11-06T01:00:00Z"


def test_create_contract_requires_digest_for_idempotency_key(monkeypatch):
    _install(monkeypatch, _FakeResponse({"code": 200, "data": {}}))
    _, contract, claim = _objects()
    raw = contract.to_dict()
    raw.pop("digest")
    with pytest.raises(RecoveryPublisherError) as error:
        _publisher().create_contract(raw, claim, owner_user_id=7, run_id=42)
    assert "digest" in str(error.value)


# ---------------------------------------------------------------------------
# 幂等与失败透传
# ---------------------------------------------------------------------------

def test_idempotent_replay_returns_original_record(monkeypatch):
    _, contract, claim = _objects()
    _install(
        monkeypatch,
        _FakeResponse({"code": 200, "message": "success",
                       "data": {"id": 11, "contractId": contract.id,
                                "digest": contract.digest, "idempotentReplay": True}}),
    )
    result = _publisher().create_contract(contract, claim, owner_user_id=7, run_id=42)
    assert result == {"id": 11, "contractId": contract.id,
                      "digest": contract.digest, "idempotentReplay": True}


@pytest.mark.parametrize(
    ("status", "code", "message"),
    [
        (409, 409, "幂等键已用于另一份契约（digest 不同）"),
        (400, 400, "run_id 指向的运行记录不存在: 42"),
    ],
)
def test_http_error_surfaces_backend_code_and_message(monkeypatch, status, code, message):
    _, contract, claim = _objects()
    _install(
        monkeypatch,
        _http_error(status, {"code": code, "message": message, "data": None}),
    )
    with pytest.raises(RecoveryPublisherError) as error:
        _publisher().create_contract(contract, claim, owner_user_id=7, run_id=42)
    assert error.value.status == status
    assert error.value.code == code
    assert message in str(error.value)


def test_success_envelope_with_error_code_is_rejected(monkeypatch):
    _install(
        monkeypatch,
        _FakeResponse({"code": 500, "message": "服务器内部错误", "data": None}),
    )
    _, contract, claim = _objects()
    with pytest.raises(RecoveryPublisherError) as error:
        _publisher().create_contract(contract, claim, owner_user_id=7, run_id=42)
    assert error.value.code == 500
    assert "服务器内部错误" in str(error.value)


def test_non_json_response_is_rejected(monkeypatch):
    _install(monkeypatch, _FakeResponse(b"<html>502 Bad Gateway</html>", status=200))
    _, contract, claim = _objects()
    with pytest.raises(RecoveryPublisherError) as error:
        _publisher().create_contract(contract, claim, owner_user_id=7, run_id=42)
    assert "非 JSON" in str(error.value)


def test_network_failure_is_rejected(monkeypatch):
    _install(monkeypatch, urllib_error.URLError("connection refused"))
    _, contract, claim = _objects()
    with pytest.raises(RecoveryPublisherError) as error:
        _publisher().create_contract(contract, claim, owner_user_id=7, run_id=42)
    assert error.value.status is None
    assert "无法连接" in str(error.value)


def test_internal_token_never_appears_in_error(monkeypatch):
    _install(monkeypatch, _http_error(403, {"code": 403, "message": "内部 Token 不匹配"}))
    _, contract, claim = _objects()
    with pytest.raises(RecoveryPublisherError) as error:
        _publisher().create_contract(contract, claim, owner_user_id=7, run_id=42)
    assert TOKEN not in str(error.value)


# ---------------------------------------------------------------------------
# 观测
# ---------------------------------------------------------------------------

def test_append_observations_maps_frozen_observation(monkeypatch):
    case, _, _ = _objects()
    observations = case["input"]["observations"][:2]
    calls = _install(
        monkeypatch,
        _FakeResponse({"code": 200, "data": {"contractRecordId": 11, "accepted": 2}}),
    )
    result = _publisher().append_observations(11, observations)

    assert result == {"contractRecordId": 11, "accepted": 2}
    request, _ = calls[0]
    assert request.full_url == BASE + "/api/internal/recovery/contracts/11/observations"
    body = _body(request)
    assert [item["id"] for item in body["observations"]] == [
        item["id"] for item in observations
    ]
    first = body["observations"][0]
    assert first["probe_id"] == observations[0]["probe_id"]
    assert first["source_group"] == observations[0]["source_group"]
    assert first["artifact_digest"] == observations[0]["artifact_digest"]


def test_append_observations_rejects_empty_batch(monkeypatch):
    calls = _install(monkeypatch, _FakeResponse({"code": 200, "data": {}}))
    with pytest.raises(RecoveryPublisherError):
        _publisher().append_observations(11, [])
    assert calls == []


# ---------------------------------------------------------------------------
# 回执
# ---------------------------------------------------------------------------

def test_append_receipt_keeps_verified_times_and_results(monkeypatch):
    _, receipt = _receipt()
    calls = _install(
        monkeypatch,
        _FakeResponse({"code": 200, "data": {"contractRecordId": 11,
                                             "receiptId": receipt.id}}),
    )
    result = _publisher().append_receipt(
        11,
        receipt,
        probe_decision={"stop_reason": "STOP_NO_NEW_INFORMATION", "calls_used": 6},
        invalidation_events=[
            InvalidationEvent(
                event_id="evt-1",
                receipt_id=receipt.id,
                kind="REVISION_CHANGED",
                reason="r17",
                created_at=receipt.issued_at,
            )
        ],
    )

    assert result == {"contractRecordId": 11, "receiptId": receipt.id}
    request, _ = calls[0]
    assert request.full_url == BASE + "/api/internal/recovery/contracts/11/receipts"
    body = _body(request)
    assert body["receipt"]["verdict"] == "VERIFIED"
    assert body["receipt"]["receipt_state"] == "ACTIVE"
    assert body["receipt"]["issued_at"] == receipt.to_dict()["issued_at"]
    assert body["receipt"]["valid_until"] == receipt.to_dict()["valid_until"]
    assert body["receipt"]["evidence_snapshot_digest"] == receipt.evidence_snapshot_digest
    assert body["obligation_results"] == receipt.to_dict()["obligation_results"]
    assert body["probe_decision"]["stop_reason"] == "STOP_NO_NEW_INFORMATION"
    assert body["invalidation_events"][0]["kind"] == "REVISION_CHANGED"


def test_append_receipt_does_not_sign_non_verified(monkeypatch):
    _, receipt = _receipt("negative-passed-but-business-false")
    calls = _install(monkeypatch, _FakeResponse({"code": 200, "data": {"receiptId": receipt.id}}))
    _publisher().append_receipt(11, receipt)

    body = _body(calls[0][0])
    assert body["receipt"]["verdict"] == "CONTRADICTED"
    assert body["receipt"]["receipt_state"] == "NOT_ISSUED"
    assert body["receipt"]["issued_at"] is None
    assert body["receipt"]["valid_until"] is None


# ---------------------------------------------------------------------------
# 回放包
# ---------------------------------------------------------------------------

def test_append_replay_bundle_passes_frozen_json(monkeypatch):
    bundle = {
        "schema_version": "recovery-replay/v1",
        "bundle_id": "bundle-positive-r17",
        "digest": "sha256:" + "a" * 64,
        "parent_bundle_id": None,
        "mutation_diff": None,
        "is_historical_fact": True,
    }
    calls = _install(
        monkeypatch,
        _FakeResponse({"code": 200, "data": {"contractRecordId": 11,
                                             "bundleId": bundle["bundle_id"]}}),
    )
    result = _publisher().append_replay_bundle(
        11, bundle, replay_result={"replay_state": "COMPLETE"}
    )

    assert result == {"contractRecordId": 11, "bundleId": bundle["bundle_id"]}
    body = _body(calls[0][0])
    assert body["bundle"] == bundle
    assert body["replay_result"] == {"replay_state": "COMPLETE"}


def test_append_replay_bundle_rejects_rebuilt_object(monkeypatch):
    calls = _install(monkeypatch, _FakeResponse({"code": 200, "data": {}}))
    with pytest.raises(RecoveryPublisherError) as error:
        _publisher().append_replay_bundle(11, object())
    assert "冻结原始 JSON" in str(error.value)
    assert calls == []
