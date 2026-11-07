# Windows Scripts

用于 SmartOpsAgent Windows 本地开发环境。

## start-platform.ps1（推荐：一键启停全栈）

管理本机八个服务（MySQL / Redis / Ollama / 后端 / knowledge / ai-service / 用户前端 / 管理前端），外加 E2E 用的 mock SSH。已在跑且健康检查通过的服务会被跳过，不会重复拉起。

```powershell
.\start-platform.ps1              # 启动全部（含 mock SSH）
.\start-platform.ps1 -SkipMockSsh # 演示模式：不起 mock SSH
.\start-platform.ps1 -Status      # 只读看状态（UP / WARN / DOWN）
.\start-platform.ps1 -Stop        # 停止全部（MySQL 为系统服务，不停）
.\start-platform.ps1 -Restart     # 先停再起
.\start-platform.ps1 -KeepAlive   # 起完不退出，前台保活（CI / 受管会话里用）
```

特性：

- 统一从根 `.env` 注入环境变量（JDK 17、DB 口令、run token secret、LLM 配置），Windows 大小写不敏感导致的重复键会自动去重；
- 启动前清理 `*_proxy` 并固定 `NO_PROXY=127.0.0.1,localhost`，避免系统代理劫持本机健康检查；
- 每个服务带健康门禁（HTTP 内容匹配，而不只是端口通），未就绪会打印日志尾部；
- 进程号写入 `.runtime\pids\<svc>.pid`，日志写入 `.runtime\logs\<svc>-<时间戳>.log`；
- 结束时若有关键服务未就绪，以退出码 1 失败，不会假成功。

双击入口：`scripts\windows\start-platform.cmd`（桌面版 `SmartOpsAgent-启动全部后台功能.cmd` 转发到同一脚本）。

## check-env.ps1

检查：

```text
Java
Maven
Node.js
npm
Python
Docker
Git
```

## status-local.ps1

本地运行环境体检：端口占用、进程内存、Docker 容器、可用内存与磁盘。

```powershell
.\status-local.ps1
.\status-local.ps1 -Clean   # 顺带清理 .runtime 旧构建快照与已退出容器
```

## start-all.ps1

按顺序启动本地开发服务，并在每一步等待 HTTP 就绪后再启动下一项。已有监听会复用，不重复拉起同一端口的服务；日志写入 `.runtime/launcher-logs/`，服务窗口在后台运行。

```powershell
.\start-all.ps1
.\start-all.ps1 -ProjectRoot 'D:\SmartOpsAgent'
.\start-all.ps1 -SkipDependencies       # 跳过 Docker Compose（MySQL / Redis）
```

脚本通过隐藏的 `cmd.exe /c` 和 `Start-Process` 启动服务，输出落入 `.runtime/launcher-logs/`。前端等待 TCP 监听；Backend、AI 和 Knowledge 还需通过各自 HTTP 就绪条件。任一步未在默认 120 秒内就绪时以非零状态退出。可用 `-StartupTimeoutSeconds` 调整等待时间；不会自动终止已有服务。

| 服务 | 端口 | 启动命令/就绪条件 |
| --- | ---: | --- |
| Frontend 用户层 | 5173 | `npm run dev` |
| Frontend 管理层 | 5174 | `npm run dev:admin` |
| Backend | 8080 | Maven 打包后运行 Spring Boot JAR；`/actuator/health` |
| AI Service | 8001 | `python -m uvicorn app.main:app`；`/api/health` 且服务名匹配 |
| Knowledge | 8002 | `python -m uvicorn knowledge.server:app`（`start-all.ps1` 额外加 `--reload --reload-dir knowledge`）；`/api/ready`、`READY`、`ready=true` 且 `chunks>0` |

`/api/health` 仅表示 Knowledge 进程存活；`/api/ready` 才表示当前实例已加载可检索索引。端口被旧实例占用且未就绪时，脚本会保留旧进程并报告失败，不会强制结束未知 PID。

Knowledge 服务单独重启（不会误杀占用 8002 的其它程序，失败会清理残留进程并输出日志尾部）：

```powershell
.\restart-knowledge.ps1              # 稳定启动，换代码/换配置后用
.\restart-knowledge.ps1 -Reload      # 带 --reload，开发态改 knowledge/ 下 .py 自动生效
```

`start-all.ps1` 已默认带 `--reload`，日常改代码不需要重启；只有改环境变量或依赖时才需要执行上面的重启脚本。
