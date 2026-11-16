import asyncio
import json
import re
import time
from typing import Any

from ..core.config import settings
from ..core.exceptions import LLMException, UpstreamSaturated
from ..core.http_pool import http_pool


class LLMService:
    """
    LLM 统一服务接口。

    Provider 统一接口：Ollama 可用时真实调用，连接失败时明确降级到 mock。
    """

    def __init__(self) -> None:
        self.degraded = False
        self.degradation_reason = ""
        self.effective_provider = settings.llm_provider.lower()
        # KV-CACHE：最近一次真实调用的推理指标（Ollama 返回的预填充/解码计数），
        # 由 chat 层并入响应 metadata.llm_perf，用于验证 prompt 前缀复用效果。
        self.last_llm_perf: dict[str, Any] = {"provider": settings.llm_provider.lower()}

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
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
                    model=model,
                    **kwargs,
                )
                self.effective_provider = "ollama"
                return result
            except UpstreamSaturated:
                # 容量不足不是模型故障：向上返回明确的过载响应，不降级为 mock。
                raise
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
        model: str | None = None,
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
                    model=model,
                ):
                    self.effective_provider = "ollama"
                    emitted = True
                    yield chunk
                if not emitted:
                    raise LLMException("Ollama 返回为空")
            except UpstreamSaturated:
                # 容量不足不是模型故障：保留已输出的部分，但以明确过载结束，不混入 mock。
                raise
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

    @staticmethod
    def _perf_from_ollama(data: dict[str, Any], ttft_ms: int | None, total_ms: int) -> dict[str, Any]:
        """从 Ollama 响应/完成帧提取推理指标（时长单位 ns → ms，如实缺省 None）。"""

        def _ms(key: str) -> int | None:
            value = data.get(key)
            return round(value / 1e6) if isinstance(value, (int, float)) else None

        return {
            "provider": "ollama",
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
            "prompt_eval_count": data.get("prompt_eval_count"),
            "prompt_eval_duration_ms": _ms("prompt_eval_duration"),
            "eval_count": data.get("eval_count"),
            "eval_duration_ms": _ms("eval_duration"),
        }

    async def _ollama_stream(
        self,
        prompt: str,
        system_prompt: str | None,
        model: str | None = None,
    ):

        payload = self._payload(prompt, system_prompt, stream=True, model=model)

        started = time.perf_counter()
        ttft_ms: int | None = None
        done_data: dict[str, Any] = {}
        async with http_pool.acquire() as client:
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
                        if ttft_ms is None:
                            ttft_ms = round((time.perf_counter() - started) * 1000)
                        has_text = has_text or bool(chunk.strip())
                        yield chunk
                    if data.get("done"):
                        completed = True
                        if isinstance(data, dict):
                            done_data = data
                        break
                if not completed or not has_text:
                    raise LLMException("Ollama 流未完整结束或返回为空")
        # KV-CACHE：完成帧带最终计数，如实记录本次预填充/解码指标。
        self.last_llm_perf = self._perf_from_ollama(
            done_data,
            ttft_ms=ttft_ms,
            total_ms=round((time.perf_counter() - started) * 1000),
        )

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
        model: str | None = None,
        **kwargs: Any,
    ) -> str:

        payload = self._payload(prompt, system_prompt, stream=False, model=model)
        started = time.perf_counter()
        async with http_pool.acquire() as client:
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
        # KV-CACHE：非流式响应体自带最终计数，如实记录本次预填充/解码指标。
        self.last_llm_perf = self._perf_from_ollama(
            data if isinstance(data, dict) else {},
            ttft_ms=None,
            total_ms=round((time.perf_counter() - started) * 1000),
        )
        return answer

    @staticmethod
    def _payload(prompt: str, system_prompt: str | None, *, stream: bool,
                 model: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            # PERF-07：调用方可按复杂度路由指定模型；未指定时沿用全局配置。
            "model": model or settings.llm_model,
            "prompt": prompt,
            "stream": stream,
        }
        if system_prompt:
            payload["system"] = system_prompt
        # KV-CACHE：保模型与 KV 缓存驻留，前缀复用生效的前提（时长串，Ollama 接受 Go duration）。
        payload["keep_alive"] = f"{max(0, settings.llm_keep_alive_sec)}s"
        return payload

    def _reset_call_state(self) -> str:
        provider = settings.llm_provider.lower()
        self.degraded = False
        self.degradation_reason = ""
        self.effective_provider = provider
        # KV-CACHE：每次调用先重置，chat 层读到的一定是本次请求的指标。
        self.last_llm_perf = {"provider": provider}
        return provider

    def _mark_degraded(self, exc: Exception, *, provider: str = "mock") -> None:
        self.degraded = True
        self.effective_provider = provider
        self.degradation_reason = f"{type(exc).__name__}: {exc}"
