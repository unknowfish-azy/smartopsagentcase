"""主→备模型降级链（P0 执行闭环加固）。

LLM 服务本身不稳定（超时/限流/5xx/宕机）时，按顺序切换备用模型，
全部失败才抛出 `AllModelsFailedError`。响应 metadata 记录
`fallback_used` 与降级链路，便于可观测与成本归因。
"""

from __future__ import annotations

import logging
from typing import Any

from agent.sdk.model import ModelProvider, ModelResponse

logger = logging.getLogger(__name__)


class AllModelsFailedError(RuntimeError):
    """降级链上所有模型都失败。"""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("所有模型均不可用: " + " | ".join(errors))


class FallbackModelProvider(ModelProvider):
    """包装一组有序 Provider：主模型失败自动切备用模型。"""

    def __init__(
        self,
        providers: list[ModelProvider],
        name: str = "fallback-chain",
    ) -> None:
        if not providers:
            raise ValueError("降级链至少需要一个模型 Provider")
        self._providers = providers
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def chain(self) -> list[str]:
        return [provider.name for provider in self._providers]

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        errors: list[str] = []

        for index, provider in enumerate(self._providers):
            try:
                response = await provider.generate(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - 降级链必须吞掉任何上游异常继续切换
                errors.append(f"{provider.name}: {type(exc).__name__}: {exc}")
                logger.warning(
                    "model.fallback model=%s index=%s/%s error=%s",
                    provider.name, index + 1, len(self._providers), exc,
                )
                continue

            # 记录降级信息：primary 失败后由第 index 个模型接管的完整链路
            if index > 0:
                response.metadata["fallback_used"] = True
                response.metadata["fallback_chain"] = self.chain
            else:
                response.metadata.setdefault("fallback_used", False)
            return response

        raise AllModelsFailedError(errors)


__all__ = [
    "AllModelsFailedError",
    "FallbackModelProvider",
]
