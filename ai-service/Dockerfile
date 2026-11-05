# ============================================================
# SmartOpsAgent AI Service 镜像（PERF-08）
# ============================================================
# 修正：此前该路径下的 Dockerfile 复制并运行 app.jar（Java 产物），
# 与实际 Python FastAPI 服务不符 —— 按它构建出来的镜像无法提供 AI 服务。
#
# 构建：
#   docker build -f ai-service/Dockerfile -t smartops-ai-service .
# ============================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
