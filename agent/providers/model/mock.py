from agent.sdk.model import (
    ModelProvider,
    ModelResponse,
)


class MockModelProvider(ModelProvider):

    def __init__(
        self,
        model_name: str = "mock-model",
    ) -> None:
        self.model_name = model_name

    @property
    def name(self) -> str:
        return self.model_name

    async def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> ModelResponse:

        return ModelResponse(
            content=(
                "[MOCK MODEL]\n"
                "已收到请求，但当前使用Mock模型。"
            ),
            model=self.model_name,
            provider="mock",
            metadata={
                "prompt_length": len(prompt)
            },
        )