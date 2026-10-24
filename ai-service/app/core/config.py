import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    request_timeout: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()