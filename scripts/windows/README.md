# Windows Scripts

用于 SmartOpsAgent Windows 本地开发环境。

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
