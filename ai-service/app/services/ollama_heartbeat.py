"""Ollama KV-CACHE 心跳保活服务。

=================================================================
原理（用户方案 #1 的工程化落地）：
=================================================================
Ollama(llama.cpp) 只保留「最近一次评估」的 prompt 的 KV 缓存。空闲期间
若达到某个内部阈值（实测 ~60-120 秒无新评估），KV 会被驱逐——下次业务
请求即使前缀完全一致也得重新预填充（TTFT 从 ~20ms 回升到数百 ms）。

解法：空闲期每 INTERVAL 秒发一个**与业务前缀逐字节一致**的超短请求
（2 token prompt + 同款 system），刷新 KV 驱逐计时窗口。
关键：心跳必须用与业务**相同的 system + 相同的固定头部**——
这样即使它刷新了缓存槽，业务请求仍能命中其前缀。

成本极低：2 token 预填充 + 1 token 生成，单次 ~50ms。

=================================================================
使用条件：
=================================================================
- LLM_PROVIDER=ollama 时才启用；mock / openai-compatible 自动跳过
- heartbeat_prompt 必须用与业务 prompt **前缀逐字节一致**的固定文本
  （心跳不改业务 prompt，而是让心跳 prompt 匹配业务前缀）

=================================================================
生命周期：
=================================================================
由 main.py 的 lifespan 启动/关闭，与 AI Service 同生共死。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from ..core.config import settings
from ..core.http_pool import http_pool

# 关键：心跳必须用与业务**完全相同的 system prompt**，Ollama 才会复用
# system 部分的 KV 缓存。这里从 chat 模块直接引用——单向依赖，无循环。
# 如果 chat.SYSTEM_PROMPT 改了，心跳自动同步，不会出现 prefix 对不上的情况。
from .chat import SYSTEM_PROMPT as _BUSINESS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class OllamaHeartbeat:
    """Ollama KV 缓存心跳保活后台任务。

    单例——由 lifespan 持有，全局只有一个实例。
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._running = False

        # 统计字段（供健康检查 / metrics 读取）
        self.total_beats = 0
        self.last_beat_ms: Optional[int] = None
        self.last_success: Optional[bool] = None
        self.last_error: Optional[str] = None
        self.consecutive_failures = 0

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """在 lifespan 的 startup 阶段调用。非 ollama provider 时静默跳过。"""

        if not self._should_enable():
            logger.info(
                "OllamaHeartbeat: 跳过（provider=%s, heartbeat_enabled=%s）",
                settings.llm_provider,
                settings.ollama_heartbeat_enabled,
            )
            return

        if self._running:
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="ollama-heartbeat")
        self._running = True
        logger.info(
            "OllamaHeartbeat: 启动（model=%s, interval=%ss, keep_alive=%ss）",
            settings.llm_model,
            settings.ollama_heartbeat_interval_sec,
            settings.llm_keep_alive_sec,
        )

    async def stop(self) -> None:
        """在 lifespan 的 shutdown 阶段调用。"""
        if not self._running:
            return

        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._running = False
        logger.info("OllamaHeartbeat: 停止（总心跳 %d 次）", self.total_beats)

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _should_enable(self) -> bool:
        """是否应该启动心跳——两个条件同时满足。"""
        return (
            settings.llm_provider.lower() == "ollama"
            and settings.ollama_heartbeat_enabled
        )

    async def _loop(self) -> None:
        """心跳主循环：每 interval 秒发一次超短请求。"""

        interval = settings.ollama_heartbeat_interval_sec

        # 启动后先立即发一次——预热 KV，避免首个业务请求冷启动
        await self._beat()

        while not self._stop_event.is_set():
            try:
                # asyncio.wait_for 支持被 stop_event 提前唤醒
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(interval),
                )
                # stop_event 被 set → 退出循环
                break
            except asyncio.TimeoutError:
                # 正常超时 → 发心跳
                pass

            await self._beat()

    async def _beat(self) -> None:
        """发一次心跳请求。失败不抛异常——心跳不能影响主业务。"""

        self.total_beats += 1
        started = time.perf_counter()

        try:
            payload = {
                "model": settings.llm_model,
                # 关键 1：相同 system prompt → Ollama 复用 system 部分的 KV
                "system": _BUSINESS_SYSTEM_PROMPT,
                # 关键 2：心跳 prompt 必须与业务 prompt 前缀逐字节一致。
                # config.ollama_heartbeat_prompt 默认值已对齐 chat._build_prompt
                # 的固定头部（到「知识库证据：」为止），尾部只加极短的 "ping"。
                "prompt": settings.ollama_heartbeat_prompt,
                "stream": False,
                "keep_alive": f"{max(0, settings.llm_keep_alive_sec)}s",
            }
            # 心跳不需要输出 token，用 num_predict=1 强制 Ollama 只生成
            # 1 个 token 就停止——进一步压缩成本。
            payload["options"] = {"num_predict": 1}
            if settings.llm_num_ctx > 0:
                payload["options"]["num_ctx"] = settings.llm_num_ctx

            async with http_pool.acquire() as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/api/generate",
                    json=payload,
                    timeout=float(settings.ollama_heartbeat_timeout_sec),
                )

            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", "replace")[:300]
                raise RuntimeError(f"HTTP {response.status_code}: {body}")

            data = response.json()
            if data.get("error"):
                raise RuntimeError(f"Ollama error: {data['error']}")

            elapsed_ms = round((time.perf_counter() - started) * 1000)
            self.last_beat_ms = elapsed_ms
            self.last_success = True
            self.consecutive_failures = 0
            self.last_error = None

            # 日志：只在首次、或连续失败后恢复、或每 N 次打印一次
            if self.total_beats <= 3 or self.consecutive_failures == 0:
                logger.debug(
                    "OllamaHeartbeat: beat #%d OK (%dms, prompt_eval=%s, eval=%s)",
                    self.total_beats,
                    elapsed_ms,
                    data.get("prompt_eval_count"),
                    data.get("eval_count"),
                )

        except asyncio.CancelledError:
            raise  # 取消不吞，让外层 loop 正常退出
        except Exception as exc:
            self.last_success = False
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.consecutive_failures += 1
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            self.last_beat_ms = elapsed_ms

            # 连续失败时逐级加日志，但不 spam：1→warning, 5→error, 10→error
            if self.consecutive_failures in (1, 5, 10) or self.consecutive_failures % 20 == 0:
                log_fn = logger.error if self.consecutive_failures >= 5 else logger.warning
                log_fn(
                    "OllamaHeartbeat: beat #%d FAILED (%dms, consecutive=%d) — %s",
                    self.total_beats,
                    elapsed_ms,
                    self.consecutive_failures,
                    self.last_error,
                )

    # ------------------------------------------------------------------ #
    # 对外状态查询（供 /health、metrics 等）
    # ------------------------------------------------------------------ #

    @property
    def status(self) -> dict:
        """心跳状态快照——可被健康检查接口直接返回。"""
        return {
            "enabled": self._should_enable(),
            "running": self._running,
            "total_beats": self.total_beats,
            "last_beat_ms": self.last_beat_ms,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "interval_sec": settings.ollama_heartbeat_interval_sec,
            "model": settings.llm_model,
        }


# 全局单例——由 lifespan 负责 start/stop
heartbeat = OllamaHeartbeat()
