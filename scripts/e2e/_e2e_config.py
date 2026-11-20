# -*- coding: utf-8 -*-
"""E2E 夹具凭据集中加载器。

所有 E2E 脚本共享的账号/口令/数据库连接统一在此读取，避免把凭据硬编码进
被 git 追踪的脚本。取值优先级：

  1. 进程环境变量
  2. ``scripts/e2e/.env.e2e``（已被 .gitignore 的 ``.env.*`` 规则排除）

关键凭据缺失时 fail-closed 抛错，避免误用空口令连库或登录夹具失败。
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent / ".env.e2e"


def _load_env_file() -> None:
    if not _ENV_FILE.exists():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"缺少 E2E 凭据 {name}；请在 scripts/e2e/.env.e2e 中配置"
            f"（参考 .env.e2e.example）或导出到环境变量后再运行。"
        )
    return value


_load_env_file()

# ── MySQL ────────────────────────────────────────────────────────────────
MYSQL_HOST = os.environ.get("E2E_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("E2E_MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("E2E_MYSQL_USER", "root")
MYSQL_PASSWORD = _required("E2E_MYSQL_PASSWORD")
MYSQL_DATABASE = os.environ.get("E2E_MYSQL_DATABASE", "smartops")
MYSQL = dict(
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE,
    charset="utf8mb4",
    autocommit=True,
)

# ── mock SSH（SEC-04/05 审批链路）─────────────────────────────────────────
SSH_HOST = os.environ.get("E2E_SSH_HOST", "127.0.0.1")
SSH_PORT = int(os.environ.get("E2E_SSH_PORT", "2222"))
SSH_USER = _required("E2E_SSH_USER")
SSH_PASSWORD = _required("E2E_SSH_PASSWORD")

# ── 夹具账号口令（seed_sec_fixtures.py 写入，各套件共享，必须一致）─────────
ADMIN_PASSWORD = _required("E2E_ADMIN_PASSWORD")
OPERATOR_PASSWORD = _required("E2E_OPERATOR_PASSWORD")
SEC14_PASSWORD = _required("E2E_SEC14_PASSWORD")
