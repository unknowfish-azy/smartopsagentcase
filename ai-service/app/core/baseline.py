"""安全基线工厂（ai-service 侧组合根适配器）。

职责：把 agent.security_baseline.build_security_baseline 封装成模块级
单例，由 main.lifespan 在 startup 时装配、shutdown 时释放；业务链路
（ChatService 输入/输出护栏）通过 get_bundle() 惰性获取—— bundle 为
None 时表示基线关闭或装配失败，所有安全基线检查静默跳过，
guard_enabled 开关仍保持独立、不受基线影响。

配置读取：ai-service Settings 新增三项（见 core/config.py）：
* security_baseline_enabled = True      总开关（默认开）
* security_audit_dir = "data/security_audit"   审计落盘相对路径（仓库根）
* security_baseline_config_path = ""    外部 YAML（空=包内默认）

fail-closed：bootstrap 期间如果哈希链/清单校验失败，直接抛 ValueError
中断 lifespan——服务不得在无锚点审计下"裸奔"启动；skip=False 时静默跳过
并返回 None 让业务降级，但日志必须留痕。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

# 生产部署和 pytest 都必须能 import agent —— 仓库根在 ai-service/ 之上 3 层。
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
if TYPE_CHECKING:
    from agent.security_baseline import SecurityBaselineBundle

logger = logging.getLogger(__name__)

# 进程级单例缓存：lifespan startup 装一次；ChatService 多次请求通过 getter 取同一份。
_bundle: "SecurityBaselineBundle | None" = None
_lock = Lock()


def bootstrap(*, skip: bool = False) -> "SecurityBaselineBundle | None":
    """装配或重装配安全基线 bundle。

    参数 skip=True 时不做任何装配、直接返回 None——测试里用于模拟
    基线未启用的降级路径，绝不静默吞掉异常（与 build_security_baseline
    的 fail-closed 保持一致）。
    """
    global _bundle
    with _lock:
        if skip:
            logger.info("security_baseline.bootstrap skip=True → bundle=None")
            _bundle = None
            return None

        from ..core.config import settings
        from agent.security_baseline import build_security_baseline

        if not settings.security_baseline_enabled:
            logger.info("security_baseline.bootstrap disabled via Settings → bundle=None")
            _bundle = None
            return None

        repo_root = Path(__file__).resolve().parents[3]
        audit_dir = Path(settings.security_audit_dir)
        if not audit_dir.is_absolute():
            audit_dir = repo_root / audit_dir

        config_path = settings.security_baseline_config_path or None
        if config_path and not Path(config_path).is_absolute():
            config_path = str(repo_root / config_path)

        bundle = build_security_baseline(
            audit_dir=audit_dir,
            config_path=config_path,
        )
        _bundle = bundle
        report = bundle.verify_audit_chain()
        logger.info(
            "security_baseline.bootstrap ok audit_dir=%s events=%s segments=%s chain_ok=%s",
            audit_dir, report.get("total_events", 0),
            report.get("segments", 0), report.get("ok"),
        )
        return bundle


def get_bundle() -> "SecurityBaselineBundle | None":
    """业务链路惰性获取 bundle；未 bootstrap 或已关闭时返回 None。"""
    return _bundle


def teardown() -> None:
    """shutdown 时释放引用，供后续重启重新 bootstrap（进程内无后台线程需停）。"""
    global _bundle
    with _lock:
        if _bundle is not None:
            report = _bundle.verify_audit_chain()
            logger.info(
                "security_baseline.teardown final events=%s segments=%s chain_ok=%s",
                report.get("total_events", 0), report.get("segments", 0), report.get("ok"),
            )
            _bundle = None


__all__ = ["bootstrap", "get_bundle", "teardown"]
