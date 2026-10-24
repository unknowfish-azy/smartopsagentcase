FROM eclipse-temurin:17-jre
WORKDIR /app
# 构建产物由CI/CD复制到此处。
COPY app.jar /app/app.jar
EXPOSE 8003
ENTRYPOINT ["java", "-jar", "/app/app.jar"]