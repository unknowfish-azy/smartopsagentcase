"""N06 平台接入：把 recovery-contract 对象上报到 Backend 内部写接口。

冻结规则来源：``docs/design/recovery-contract-v1/platform-integration.md``。

边界（有意如此）：
- 本模块只做 HTTP 传输与字段映射；不计算 verdict、不补签回执、不改写任何冻结字段。
- 配置缺失、网络失败、非 2xx、``ApiResponse.code != 200`` 一律抛异常。
  "接口返回 200" 只代表平台已受理该次写入，不代表恢复已成功。
- ``append_replay_bundle`` 只接受冻结原始 JSON（``Mapping``），不接受从
  ``ReplayBundle`` 重建，避免重建后的 canonical 摘要与正文不符。
- 幂等键由调用方给出，否则按 contract ``digest`` 派生：同契约重放返回原记录，
  不同 digest 复用同键由服务端返回 409，本模块不吞掉该冲突。
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Mapping

from urllib import error as urllib_error
from urllib import request as urllib_request

from .models import (
    Claim,
    EvidenceObservation,
    RecoveryContract,
    VerificationReceipt,
    format_time,
)

ENV_BACKEND_URL = "SMARTOPS_BACKEND_URL"
ENV_INTERNAL_TOKEN = "SMARTOPS_INTERNAL_TOKEN"
INTERNAL_TOKEN_HEADER = "X-SmartOps-Internal-Token"
IDEMPOTENCY_PREFIX = "recovery-contract:"

CONTRACTS_PATH = "/api/internal/recovery/contracts"


class RecoveryPublisherError(RuntimeError):
    """上报失败；调用方不得据此声称恢复已完成。"""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: int | None = None,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.data = data


class PublisherConfigError(RecoveryPublisherError):
    """``SMARTOPS_BACKEND_URL`` 或 ``SMARTOPS_INTERNAL_TOKEN`` 缺失。

    缺少配置时直接失败，不降级为"跳过上报"，也不把未写入写成已写入。
    """


class RecoveryPublisher:
    """Backend 内部写接口的薄客户端（标准库 urllib，不引入新依赖）。"""

    def __init__(
        self,
        backend_url: str | None = None,
        internal_token: str | None = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        url = (
            backend_url if backend_url is not None else os.getenv(ENV_BACKEND_URL, "")
        ).strip()
        token = (
            internal_token
            if internal_token is not None
            else os.getenv(ENV_INTERNAL_TOKEN, "")
        ).strip()
        if not url:
            raise PublisherConfigError(
                f"缺少 {ENV_BACKEND_URL}：未配置 Backend 地址，不发起上报"
            )
        if not token:
            raise PublisherConfigError(
                f"缺少 {ENV_INTERNAL_TOKEN}：未配置内部 Token，不发起上报"
            )
        self.backend_url = url.rstrip("/")
        self.timeout = timeout
        self._internal_token = token

    # ---------------------------------------------------------------- 写入

    def create_contract(
        self,
        contract: RecoveryContract | Mapping[str, Any],
        claim: Claim | Mapping[str, Any],
        *,
        owner_user_id: int,
        run_id: int,
        idempotency_key: str | None = None,
        valid_from: Any = None,
    ) -> dict[str, Any]:
        """登记契约；``data`` 含 ``id`` / ``contractId`` / ``digest`` / ``idempotentReplay``。"""
        contract_body = _object_body(contract, RecoveryContract, "contract")
        claim_body = _object_body(claim, Claim, "claim")
        digest = contract_body.get("digest")
        if not isinstance(digest, str) or not digest:
            raise RecoveryPublisherError("contract 缺少 digest，无法生成幂等键")
        payload: dict[str, Any] = {
            "ownerUserId": owner_user_id,
            "runId": run_id,
            "idempotencyKey": idempotency_key or IDEMPOTENCY_PREFIX + digest,
            "contract": contract_body,
            "claim": claim_body,
        }
        if valid_from is not None:
            payload["validFrom"] = format_time(valid_from)
        return self._post(CONTRACTS_PATH, payload)

    def append_observations(
        self,
        contract_record_id: int,
        observations: Iterable[EvidenceObservation | Mapping[str, Any]],
    ) -> dict[str, Any]:
        """追加观测；空批次直接失败，不用空数组冒充"已采样"。"""
        items = [_object_body(item, EvidenceObservation, "observation") for item in observations]
        if not items:
            raise RecoveryPublisherError("observations 不能为空：空批次不代表已采样")
        return self._post(
            f"{CONTRACTS_PATH}/{contract_record_id}/observations",
            {"observations": items},
        )

    def append_receipt(
        self,
        contract_record_id: int,
        receipt: VerificationReceipt | Mapping[str, Any],
        *,
        obligation_results: Iterable[Any] | None = None,
        probe_decision: Any = None,
        invalidation_events: Iterable[Any] = (),
    ) -> dict[str, Any]:
        """追加回执；原样上报 ``receipt``，不修正 verdict 或签发时间。"""
        receipt_body = _object_body(receipt, VerificationReceipt, "receipt")
        payload: dict[str, Any] = {
            "receipt": receipt_body,
            "obligation_results": (
                [_plain(item) for item in receipt_body.get("obligation_results") or []]
                if obligation_results is None
                else [_plain(item) for item in obligation_results]
            ),
        }
        if probe_decision is not None:
            payload["probe_decision"] = _plain(probe_decision)
        events = [_plain(item) for item in invalidation_events]
        if events:
            payload["invalidation_events"] = events
        return self._post(
            f"{CONTRACTS_PATH}/{contract_record_id}/receipts", payload
        )

    def append_replay_bundle(
        self,
        contract_record_id: int,
        bundle: Mapping[str, Any],
        *,
        replay_result: Any = None,
    ) -> dict[str, Any]:
        """登记回放包；``bundle`` 必须是冻结原始 JSON。"""
        if not isinstance(bundle, Mapping):
            raise RecoveryPublisherError(
                "bundle 必须是冻结原始 JSON 对象：不从 ReplayBundle 重建，避免摘要与正文不符"
            )
        payload: dict[str, Any] = {"bundle": dict(bundle)}
        if replay_result is not None:
            payload["replay_result"] = _plain(replay_result)
        return self._post(
            f"{CONTRACTS_PATH}/{contract_record_id}/replay-bundles", payload
        )

    # ---------------------------------------------------------------- HTTP

    def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib_request.Request(
            self.backend_url + path,
            data=body,
            headers={
                "Content-Type": "application/json",
                INTERNAL_TOKEN_HEADER: self._internal_token,
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                raw = response.read()
        except urllib_error.HTTPError as exc:
            code, message, data = _parse_error(exc, exc.read())
            raise RecoveryPublisherError(
                f"Backend 拒绝 {path}：HTTP {exc.code} code={code} {message}",
                status=exc.code,
                code=code,
                data=data,
            ) from exc
        except (urllib_error.URLError, OSError, TimeoutError) as exc:
            # 网络层失败：没有拿到任何受理结果，不得重试成"成功"。
            raise RecoveryPublisherError(f"无法连接 Backend {path}：{exc}") from exc

        envelope = _parse_envelope(raw, status, path)
        code = envelope.get("code")
        if code != 200:
            raise RecoveryPublisherError(
                f"Backend 返回 code={code}：{envelope.get('message')}",
                status=status,
                code=code if isinstance(code, int) else None,
                data=envelope.get("data"),
            )
        data = envelope.get("data")
        if not isinstance(data, Mapping):
            raise RecoveryPublisherError(
                f"Backend 响应缺少 data 对象：{path}", status=status, code=code
            )
        return dict(data)


def _object_body(value: Any, expected: type, where: str) -> dict[str, Any]:
    """冻结对象按 ``to_dict()`` 序列化；原始 Mapping 原样透传。"""
    if isinstance(value, expected):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    raise RecoveryPublisherError(f"{where} 必须是 {expected.__name__} 或 JSON 对象")


def _plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _parse_envelope(raw: bytes, status: int | None, path: str) -> Mapping[str, Any]:
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RecoveryPublisherError(
            f"Backend 返回非 JSON 响应（HTTP {status}）：{path}", status=status
        ) from exc
    if not isinstance(envelope, Mapping):
        raise RecoveryPublisherError(
            f"Backend 响应不是 ApiResponse 对象（HTTP {status}）：{path}", status=status
        )
    return envelope


def _parse_error(
    exc: urllib_error.HTTPError, raw: bytes
) -> tuple[int | None, str, Any]:
    """从 ``ApiResponse`` 错误体提取 code/message；无结构体时退回 HTTP 原因短语。"""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        payload = None
    if isinstance(payload, Mapping):
        code = payload.get("code")
        message = payload.get("message")
        return (
            code if isinstance(code, int) else None,
            str(message) if message else str(exc.reason),
            payload.get("data"),
        )
    return None, str(exc.reason), None


__all__ = [
    "ENV_BACKEND_URL",
    "ENV_INTERNAL_TOKEN",
    "IDEMPOTENCY_PREFIX",
    "INTERNAL_TOKEN_HEADER",
    "PublisherConfigError",
    "RecoveryPublisher",
    "RecoveryPublisherError",
]
