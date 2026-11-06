class AIServiceException(Exception):
    """AI Service 基础异常。"""

    def __init__(
        self,
        message: str,
        code: str = "AI_SERVICE_ERROR",
        *,
        http_status: int = 500,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)

        self.message = message

        self.code = code

        self.http_status = http_status

        self.headers = headers or {}


class LLMException(AIServiceException):
    """LLM 调用异常。"""

    def __init__(
        self,
        message: str,
    ):
        super().__init__(
            message=message,
            code="LLM_ERROR",
        )


class RAGException(AIServiceException):
    """RAG 检索异常。"""

    def __init__(
        self,
        message: str,
    ):
        super().__init__(
            message=message,
            code="RAG_ERROR",
        )


class UpstreamSaturated(AIServiceException):
    """上游并发闸门排队超时：明确过载，而不是静默降级或伪造成功。"""

    def __init__(
        self,
        message: str,
        *,
        retry_after: int = 2,
    ):
        super().__init__(
            message=message,
            code="UPSTREAM_SATURATED",
            http_status=503,
            headers={"Retry-After": str(max(1, retry_after))},
        )
