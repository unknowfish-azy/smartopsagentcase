from pydantic import BaseModel


class HealthResponse(BaseModel):

    status: str

    service: str

    version: str

    # KV-CACHE 心跳状态快照（仅 ollama provider 时非 None，
    # 内容见 services/ollama_heartbeat.py 的 OllamaHeartbeat.status）
    heartbeat: dict | None = None