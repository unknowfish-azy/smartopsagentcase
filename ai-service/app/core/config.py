from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 定位为仓库根目录（ai-service/app/core/config.py → 上溯 3 级），
# 与进程启动时的工作目录无关：无论 uvicorn 从仓库根、ai-service/ 还是其他目录启动，
# 都能读到同一份配置，避免因 cwd 不同而静默退回 mock。
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):

    app_name: str = "SmartOpsAgent AI Service"

    app_version: str = "0.1.0"

    host: str = "0.0.0.0"

    port: int = 8001

    debug: bool = False

    llm_provider: str = Field(
        default="mock",
        description="mock / ollama / openai-compatible",
    )

    llm_model: str = "mock-model"

    llm_base_url: str = "http://localhost:11434"

    llm_api_key: str = ""

    knowledge_service_url: str = (
        "http://localhost:8002"
    )

    # Knowledge 服务开启鉴权时（KNOWLEDGE_API_KEY），调用侧需发送同名 X-API-Key。
    # 留空表示 Knowledge 未开启鉴权。
    knowledge_api_key: str = ""

    # SEC-01/SEC-02：Java 边缘签发的聊天 run 令牌校验密钥，必须与
    # SMARTOPS_CHAT_RUN_TOKEN_SECRET 一致。留空时不接受任何聊天请求（503），
    # 不会退回匿名可用的旧行为。
    chat_run_token_secret: str = ""

    # 仅本地/内网联调时显式打开；生产不得开启（等同放弃聊天鉴权）。
    chat_allow_anonymous: bool = False

    request_timeout: int = 30

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()