# ============================================================
# 历史路径（PERF-08 修正）
# ============================================================
# 该文件原先 `COPY app.jar` 并 `java -jar`，与实际的 Python FastAPI 服务不符。
# 规范镜像定义在 ai-service/Dockerfile（构建上下文为 ai-service/）；
# 这里保留一份可用配方，构建上下文为仓库根目录：
#
#   docker build -f infrastructure/microservices/ai-service/Dockerfile -t smartops-ai-service .
# ============================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY ai-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai-service/app ./app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
