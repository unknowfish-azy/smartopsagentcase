@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

REM ============================================================
REM  SmartOpsAgent Windows 一键启动脚本
REM  位置：scripts\windows\start-dev.bat
REM  功能：依次启动 Docker、Backend、AI Service、Frontend
REM ============================================================

REM 脚本所在目录为 scripts\windows，向上两级即项目根目录
set "PROJECT_ROOT=%~dp0..\.."
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fI"

echo.
echo ============================================
echo  SmartOpsAgent 一键启动
echo  项目根目录：%PROJECT_ROOT%
echo ============================================
echo.

REM ---------- 0. 首次运行自动生成 .env ----------
if not exist "%PROJECT_ROOT%\.env" (
    if exist "%PROJECT_ROOT%\.env.example" (
        copy "%PROJECT_ROOT%\.env.example" "%PROJECT_ROOT%\.env" >nul
        echo [提示] 已根据 .env.example 生成 .env，请按需填入密钥
    )
)

REM ---------- 1. 环境检查 ----------
where java   >nul 2>nul || (echo [错误] 未找到 java，请先安装 JDK 17 后重试 & goto :end)
where node   >nul 2>nul || (echo [错误] 未找到 node，请先安装 Node.js 后重试 & goto :end)
where python >nul 2>nul || (echo [错误] 未找到 python，请先安装 Python 3.10+ 后重试 & goto :end)
where mvn    >nul 2>nul || (echo [警告] 未找到 mvn，Backend 将无法启动)
where docker >nul 2>nul || (echo [警告] 未找到 docker，将跳过 MySQL / Redis 容器)

echo [OK] 基础环境检查完成。
echo.

REM ---------- 2. Docker（MySQL / Redis） ----------
where docker >nul 2>nul && (
    echo [启动] Docker Compose（MySQL / Redis）...
    start "SmartOps-Docker" /D "%PROJECT_ROOT%\deploy\docker" cmd /k "docker compose up -d"
) || (
    echo [跳过] 未安装 docker，跳过 MySQL / Redis 容器
)

REM ---------- 3. Backend ----------
REM 不用 mvn spring-boot:run：它会让 Maven 启动器 JVM（实测 343MB）与
REM 应用 JVM 同时常驻。改为先打包，再用封顶参数直接跑 jar。
echo [启动] Backend（Spring Boot，端口 8080）...
start "SmartOps-Backend" /D "%PROJECT_ROOT%\backend" cmd /k "mvn -q -DskipTests package && java -Xms64m -Xmx512m -XX:MaxMetaspaceSize=192m -XX:ReservedCodeCacheSize=96m -XX:MaxDirectMemorySize=128m -XX:+UseSerialGC -XX:+ExitOnOutOfMemoryError -Dfile.encoding=UTF-8 -jar target\smartops-backend-0.0.1-SNAPSHOT.jar"

REM ---------- 4. AI Service ----------
REM 不加 --reload：它会常驻 reloader 父进程 + worker，演示期不需要热重载。
echo [启动] AI Service（端口 8001）...
start "SmartOps-AI" /D "%PROJECT_ROOT%\ai-service" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"

REM ---------- 5. Frontend ----------
echo [启动] Frontend（Vite，端口 5173）...
start "SmartOps-Frontend" /D "%PROJECT_ROOT%\frontend" cmd /k "set NODE_OPTIONS=--max-old-space-size=512&&npm run dev"

echo.
echo ============================================
echo  各服务启动窗口已打开，访问地址：
echo    Backend    : http://localhost:8080
echo    AI Service : http://localhost:8001
echo    Frontend   : http://localhost:5173
echo    MySQL      : localhost:3306
echo    Redis      : localhost:6379
echo ============================================
echo.

:end
endlocal
