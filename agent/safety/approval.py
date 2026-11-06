from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
import warnings
from uuid import uuid4


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    operation: str
    reason: str
    user_id: str | None
    created_at: datetime
    approval_id: str = ""
    expires_at: datetime | None = None
    execution_fingerprint: str | None = None


@dataclass(frozen=True)
class ApprovalResult:
    request_id: str
    approved: bool
    reviewer: str | None
    reviewed_at: datetime


class ApprovalManager:

    """Trusted-host, process-local approvals; never deserialize client grants.

    Host code authenticates reviewers before approve/reject. No public API is
    provided here. Restarting the process invalidates every pending grant.
    """

    def __init__(self, *, clock=None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._records = {}

    @staticmethod
    def _fingerprint(context, step):
        def require_json(value, ancestors=frozenset()):
            if value is None or type(value) in (str, bool, int, float):
                return
            if id(value) in ancestors or len(ancestors) > 64:
                raise ValueError("Approval arguments contain a cycle or exceed nesting limit")
            path = ancestors | {id(value)}
            if type(value) is list:
                for item in value:
                    require_json(item, path)
                return
            if type(value) is dict and all(type(key) is str for key in value):
                for item in value.values():
                    require_json(item, path)
                return
            raise ValueError("Approval arguments must use JSON types with string keys")

        payload = {
            "request_id": context.request_id,
            "user_id": context.user_id,
            "environment": context.environment,
            # SEC-04：同一请求跨 run 复用审批必须失效。run_id 是执行身份的一部分，
            # 只绑定 request/step/参数会让"旧 run 的批准"在新 run 里继续生效。
            "run_id": getattr(context, "run_id", None),
            "step_id": step.step_id,
            "tool_name": step.tool_name,
            "action": step.action,
            "arguments": step.arguments,
        }
        require_json(payload)
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def create_for_step(self, context, step, *, ttl_seconds=300):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise ValueError("Approval TTL must be between 1 and 3600 seconds")
        if not context.request_id or not context.user_id:
            raise ValueError("Approval requires request and user identity")
        # SEC-04：没有 run 身份的审批无法与新 run 区分，直接拒绝创建（fail-closed）。
        run_id = getattr(context, "run_id", None)
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("Approval requires run identity")
        created = self._clock()
        request = ApprovalRequest(
            request_id=context.request_id,
            operation=step.tool_name,
            reason=step.action,
            user_id=context.user_id,
            created_at=created,
            approval_id=uuid4().hex,
            expires_at=created + timedelta(seconds=ttl_seconds),
            execution_fingerprint=self._fingerprint(context, step),
        )
        with self._lock:
            self._records[request.approval_id] = {"request": request, "state": "pending"}
        return request

    def validate(self, approval_id, context, step, *, consume=False):
        if not isinstance(approval_id, str):
            return False
        with self._lock:
            record = self._records.get(approval_id)
            if record is None or record["state"] != "approved":
                return False
            request = record["request"]
            if request.execution_fingerprint is None or request.expires_at is None:
                return False
            if self._clock() >= request.expires_at:
                record["state"] = "expired"
                return False
            try:
                if request.execution_fingerprint != self._fingerprint(context, step):
                    return False
            except (TypeError, ValueError):
                return False
            if consume:
                record["state"] = "consumed"
            return True

    def create_request(
        self,
        request_id: str,
        operation: str,
        reason: str,
        user_id: str | None,
    ) -> ApprovalRequest:
        """已废弃（SEC-04）：仅作信息记录，不绑定执行指纹与 run，永远不能授权执行。

        新代码必须使用 :meth:`create_for_step`。
        """

        warnings.warn(
            "ApprovalManager.create_request is deprecated; use create_for_step",
            DeprecationWarning,
            stacklevel=2,
        )
        request = ApprovalRequest(
            request_id=request_id,
            operation=operation,
            reason=reason,
            user_id=user_id,
            created_at=datetime.now(
                timezone.utc
            ),
            approval_id=request_id,
        )
        with self._lock:
            if request_id in self._records:
                raise ValueError("Approval request already exists")
            self._records[request_id] = {"request": request, "state": "pending"}
        return request

    def approve(
        self,
        request_id: str,
        reviewer: str,
    ) -> ApprovalResult:

        return self._review(request_id, reviewer, approved=True)

    def reject(
        self,
        request_id: str,
        reviewer: str,
    ) -> ApprovalResult:

        return self._review(request_id, reviewer, approved=False)

    def _review(self, approval_id, reviewer, *, approved):
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("Reviewer identity required")
        with self._lock:
            record = self._records.get(approval_id)
            if record is None or record["state"] not in ({"pending"} if approved else {"pending", "approved"}):
                raise ValueError("Unknown or terminal approval request")
            request = record["request"]
            # SEC-04：审批人不得是申请人；宿主须先在可信边界完成 reviewer 身份认证。
            if approved and request.user_id is not None and reviewer.strip() == str(request.user_id):
                raise ValueError("Approval reviewer must differ from the requester")
            if request.expires_at and self._clock() >= request.expires_at:
                record["state"] = "expired"
                raise ValueError("Approval expired")
            record["state"] = "approved" if approved else "rejected"
            result = ApprovalResult(request.request_id, approved, reviewer, self._clock())
            record["result"] = result
            return result
