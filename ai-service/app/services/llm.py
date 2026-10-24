from typing import Any

from ..core.config import settings
from ..core.exceptions import LLMException


class LLMService:
    """
    LLM 统一服务接口。

    当前默认使用 mock。
    后续可接 Ollama、Qwen、OpenAI-compatible API 等。
    """

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:

        provider = settings.llm_provider.lower()

        if provider == "mock":
            return self._mock_generate(
                prompt
            )

        if provider == "ollama":
            return await self._ollama_generate(
                prompt=prompt,
                system_prompt=system_prompt,
                **kwargs,
            )

        raise LLMException(
            f"暂不支持的 LLM Provider: {provider}"
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
        **kwargs: Any,
    ) -> str:

        # 保留请求参数构造骨架，后续恢复密钥/服务地址即可直接使用。
        payload = {
            "model": settings.llm_model,
            "prompt": prompt,
            "stream": False,
        }

        if system_prompt:
            payload["system"] = system_prompt

        # 【此处为外部 API/卡密调用，已临时注释，后续填入密钥即可恢复】
        # try:
        #     import httpx
        # except ImportError as exc:
        #     raise LLMException("未安装 httpx") from exc
        #
        # async with httpx.AsyncClient(
        #     timeout=settings.request_timeout
        # ) as client:
        #     response = await client.post(
        #         f"{settings.llm_base_url}/api/generate",
        #         json=payload,
        #     )
        #
        # if response.status_code != 200:
        #     raise LLMException(
        #         "Ollama 调用失败："
        #         f"{response.status_code}"
        #     )
        #
        # data = response.json()
        # return data.get("response", "")

        # 模拟占位返回：避免缺少 Ollama 服务时程序崩溃。
        return (
            "（Ollama 模拟回答）\n\n"
            "当前 LLM Provider 为 ollama，外部模型服务调用已临时注释。\n"
            f"用户问题：{prompt}"
        )