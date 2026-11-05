import asyncio
import json
import re
from typing import Any

from ..core.config import settings
from ..core.exceptions import LLMException


class LLMService:
    """
    LLM 统一服务接口。

    Provider 统一接口：Ollama 可用时真实调用，连接失败时明确降级到 mock。
    """

    def __init__(self) -> None:
        self.degraded = False
        self.degradation_reason = ""
        self.effective_provider = settings.llm_provider.lower()

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:

        provider = self._reset_call_state()

        if provider == "mock":
            self.effective_provider = "mock"
            return self._mock_generate(
                prompt
            )

        if provider == "ollama":
            try:
                result = await self._ollama_generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    **kwargs,
                )
                self.effective_provider = "ollama"
                return result
            except Exception as exc:
                self._mark_degraded(exc)
                return self._mock_generate(prompt)

        raise LLMException(
            f"暂不支持的 LLM Provider: {provider}"
        )

    async def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """流式生成：mock 分块或读取 Ollama NDJSON 响应。"""

        provider = self._reset_call_state()

        if provider == "mock":
            self.effective_provider = "mock"
            async for chunk in self._mock_stream(prompt):
                yield chunk
            return

        if provider == "ollama":
            emitted = False
            try:
                async for chunk in self._ollama_stream(
                    prompt=prompt,
                    system_prompt=system_prompt,
                ):
                    self.effective_provider = "ollama"
                    emitted = True
                    yield chunk
                if not emitted:
                    raise LLMException("Ollama 返回为空")
            except Exception as exc:
                if emitted:
                    self._mark_degraded(exc, provider="ollama")
                    raise LLMException("真实模型输出中断，已保留部分回答，请重试") from exc
                self._mark_degraded(exc)
                async for chunk in self._mock_stream(prompt):
                    yield chunk
            return

        # 真实 Provider 接入时在此按 stream=True 解析 SSE/NDJSON
        raise LLMException(
            f"暂不支持的 LLM Provider: {provider}"
        )

    @staticmethod
    async def _mock_stream(prompt: str):

        text = (
            "这是 SmartOpsAgent AI Service "
            "的开发阶段模拟回答。\n\n"
            "当前系统已经完成请求接收、RAG 编排和 "
            "LLM 服务接口预留。\n\n"
            f"用户问题：{prompt}"
        )

        for piece in re.split(r"(\s+)", text):
            if not piece:
                continue
            await asyncio.sleep(0.015)
            yield piece

    async def _ollama_stream(
        self,
        prompt: str,
        system_prompt: str | None,
    ):

        payload = self._payload(prompt, system_prompt, stream=True)
        import httpx

        async with httpx.AsyncClient(
            timeout=settings.request_timeout,
            trust_env=False,
        ) as client:
            async with client.stream(
                "POST",
                f"{settings.llm_base_url.rstrip('/')}/api/generate",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    raise LLMException(
                        f"Ollama 调用失败：{response.status_code}"
                    )
                completed = False
                has_text = False
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if not isinstance(data, dict) or data.get("error"):
                        raise LLMException("Ollama 流返回错误")
                    if "done" in data and not isinstance(data["done"], bool):
                        raise LLMException("Ollama 流完成标志格式错误")
                    chunk = data.get("response", "")
                    if not isinstance(chunk, str):
                        raise LLMException("Ollama 流格式错误")
                    if chunk:
                        has_text = has_text or bool(chunk.strip())
                        yield chunk
                    if data.get("done"):
                        completed = True
                        break
                if not completed or not has_text:
                    raise LLMException("Ollama 流未完整结束或返回为空")

    @staticmethod
    def _mock_generate(
        prompt: str,
    ) -> str:

        return (
            "这是 SmartOpsAgent AI Service "
            "的开发阶段模拟回答。\n\n"
            "当前系统已经完成请求接收、RAG 编排和 "
            "LLM 服务接口预留。\n\n"
            f"用户问题：{prompt}"
        )

    async def _ollama_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:

        import httpx

        payload = self._payload(prompt, system_prompt, stream=False)
        async with httpx.AsyncClient(
            timeout=settings.request_timeout,
            trust_env=False,
        ) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/api/generate",
                json=payload,
            )
        if response.status_code != 200:
            raise LLMException(f"Ollama 调用失败：{response.status_code}")
        data = response.json()
        answer = data.get("response")
        if not isinstance(answer, str) or not answer.strip():
            raise LLMException("Ollama 返回为空")
        return answer

    @staticmethod
    def _payload(prompt: str, system_prompt: str | None, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": settings.llm_model,
            "prompt": prompt,
            "stream": stream,
        }
        if system_prompt:
            payload["system"] = system_prompt
        return payload

    def _reset_call_state(self) -> str:
        provider = settings.llm_provider.lower()
        self.degraded = False
        self.degradation_reason = ""
        self.effective_provider = provider
        return provider

    def _mark_degraded(self, exc: Exception, *, provider: str = "mock") -> None:
        self.degraded = True
        self.effective_provider = provider
        self.degradation_reason = f"{type(exc).__name__}: {exc}"
