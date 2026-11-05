# ============================================================
# SmartOpsAgent Backend 镜像（PERF-08）
# ============================================================
# 目的：让"可运行发布"有一条真实入口，而不是只存在于文档里。
# 构建：
#   docker build -f backend/Dockerfile -t smartops-backend .
# ============================================================

FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
# 先只复制 pom，利用层缓存避免每次改代码都重新下载依赖
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
# 非 root 运行，降低容器逃逸风险
RUN useradd --system --uid 10001 smartops \
    && apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/target/*.jar /app/app.jar
USER smartops
EXPOSE 8080
# 优雅停机由 server.shutdown=graceful 生效，编排侧需给出足够的终止宽限期
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/app.jar"]
