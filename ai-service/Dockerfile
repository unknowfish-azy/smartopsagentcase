# ============================================================
# SmartOpsAgent AI Service 镜像（PERF-08）
# ============================================================
# 修正：此前该路径下的 Dockerfile 复制并运行 app.jar（Java 产物），
# 与实际 Python FastAPI 服务不符 —— 按它构建出来的镜像无法提供 AI 服务。
#
# 构建（上下文必须是仓库根目录：服务运行期依赖根目录的 agent/ 包）：
#   docker build -f ai-service/Dockerfile -t smartops-ai-service .
# ============================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY ai-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai-service/app ./app
# app/services/chat.py 运行期 `from agent...` 导入根目录的 agent 包
COPY agent ./agent

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
