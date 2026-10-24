from agent.sdk.model import ModelProvider


class ModelRegistry:

    def __init__(self) -> None:
        self._models: dict[
            str,
            ModelProvider,
        ] = {}

    def register(
        self,
        model: ModelProvider,
    ) -> None:
        self._models[model.name] = model

    def get(
        self,
        name: str,
    ) -> ModelProvider | None:
        return self._models.get(name)

    def list(self) -> list[ModelProvider]:
        return list(self._models.values())