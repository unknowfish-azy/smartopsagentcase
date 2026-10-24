from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ApprovalRequest:
    request_id: str
    operation: str
    reason: str
    user_id: str | None
    created_at: datetime


@dataclass
class ApprovalResult:
    request_id: str
    approved: bool
    reviewer: str | None
    reviewed_at: datetime


class ApprovalManager:

    def create_request(
        self,
        request_id: str,
        operation: str,
        reason: str,
        user_id: str | None,
    ) -> ApprovalRequest:

        return ApprovalRequest(
            request_id=request_id,
            operation=operation,
            reason=reason,
            user_id=user_id,
            created_at=datetime.now(
                timezone.utc
            ),
        )

    def approve(
        self,
        request_id: str,
        reviewer: str,
    ) -> ApprovalResult:

        return ApprovalResult(
            request_id=request_id,
            approved=True,
            reviewer=reviewer,
            reviewed_at=datetime.now(
                timezone.utc
            ),
        )

    def reject(
        self,
        request_id: str,
        reviewer: str,
    ) -> ApprovalResult:

        return ApprovalResult(
            request_id=request_id,
            approved=False,
            reviewer=reviewer,
            reviewed_at=datetime.now(
                timezone.utc
            ),
        )