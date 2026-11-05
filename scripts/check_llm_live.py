#!/usr/bin/env python3
"""Run five real Ollama questions and report latency/provider state."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-service"))

from app.core.config import settings  # noqa: E402
from app.services.llm import LLMService  # noqa: E402


PROMPTS = [
    "用一句话说明 SmartOpsAgent 的用途。",
    "列出排查服务端口故障的第一步。",
    "解释什么是健康检查。",
    "给出一个安全的日志排查建议。",
    "用一句话总结本次连通性检查。",
]


async def _ollama_ready(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/tags")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


async def run_live_check() -> int:
    base_url = os.getenv("LLM_BASE_URL", settings.llm_base_url)
    if settings.llm_provider.lower() != "ollama":
        print(
            f"FAIL: LLM_PROVIDER={settings.llm_provider!r}; mock is not accepted as a live answer.",
            file=sys.stderr,
        )
        return 2
    if not await _ollama_ready(base_url):
        print(
            f"FAIL: Ollama is not started or /api/tags is unavailable at {base_url}.",
            file=sys.stderr,
        )
        return 2

    service = LLMService()
    total_start = time.perf_counter()
    for index, prompt in enumerate(PROMPTS, 1):
        first_token = None
        chunks: list[str] = []
        started = time.perf_counter()
        async for chunk in service.generate_stream(prompt):
            if first_token is None:
                first_token = time.perf_counter() - started
            chunks.append(chunk)
        elapsed = time.perf_counter() - started
        answer = "".join(chunks)
        print(
            f"{index}/5 effective_provider={service.effective_provider} "
            f"degraded={service.degraded} first_token_latency_ms="
            f"{(first_token * 1000 if first_token is not None else -1):.1f} "
            f"total_ms={elapsed * 1000:.1f} answer_chars={len(answer)}"
        )
        if service.degraded or service.effective_provider != "ollama" or not answer.strip():
            print("FAIL: response degraded to mock or was empty.", file=sys.stderr)
            return 1

    print(f"total_elapsed_ms={(time.perf_counter() - total_start) * 1000:.1f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    return asyncio.run(run_live_check())


if __name__ == "__main__":
    raise SystemExit(main())
