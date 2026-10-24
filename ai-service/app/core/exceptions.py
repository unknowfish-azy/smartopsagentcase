class AIServiceException(Exception):
    """AI Service 基础异常。"""

    def __init__(
        self,
        message: str,
        code: str = "AI_SERVICE_ERROR",
    ):
        super().__init__(message)

        self.message = message

        self.code = code


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