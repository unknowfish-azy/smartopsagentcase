# Windows Scripts

用于 SmartOpsAgent Windows 本地开发环境。

## 新手推荐路径

**第一次接触项目？请直接用 [`../handoff-kit/`](../handoff-kit/) 下的四个一键脚本**，它们会自动处理环境检查、依赖安装、`.env` 密钥生成、数据库创建等所有繁琐步骤。

本目录的脚本面向**已装好环境、需要更细粒度控制**的开发者。如果你不确定该用哪个，先看下表：

| 场景 | 脚本 | 说明 |
|---|---|---|
| 日常启停全栈 | `start-platform.ps1` | 推荐，支持 `-Status` / `-Stop` / `-Restart` |
| 一键启动（打开新窗口） | `start-dev.ps1` / `start-dev.bat` | 各服务独立 cmd 窗口，便于看实时日志 |
| 顺序等待就绪启动 | `start-all.ps1` | 每个服务等 HTTP 就绪后才起下一个 |
| 只起管理员前端 | `start-admin-frontend.ps1` | 单独起 5174 管理端 |
| 启动本地 Ollama | `start-mini.ps1` | 本地推理运行时 |
| 检查环境 | `check-env.ps1` | Java/Maven/Node/Python/Git/Docker |
| 查看运行状态 | `status-local.ps1` | 端口、进程内存、Docker、磁盘 |
| 检查配置完整性 | `check-config.ps1` | .env 必需项是否齐全 |
| 重启知识服务 | `restart-knowledge.ps1` | 带热重载 `-Reload` |
| 重启后端 | `restart-local-backend.ps1` | 安全模式，需 bootstrap.env |
| 停止所有服务 | `stop-all-local.ps1` | 按进程路径精确回收，不误杀 |

> ⚠️ **不要混用**：`start-platform.ps1`、`start-all.ps1`、`start-dev.ps1` 都是全栈启动脚本，选一个用即可，同时跑会争抢端口。

## start-platform.ps1（推荐：一键启停全栈）

管理本机八个服务（MySQL / Redis / Ollama / 后端 / knowledge / ai-service / 用户前端 / 管理前端），外加 E2E 用的 mock SSH。已在跑且健康检查通过的服务会被跳过，不会重复拉起。

```powershell
.\start-platform.ps1              # 启动全部（含 mock SSH）
.\start-platform.ps1 -SkipMockSsh # 演示模式：不起 mock SSH
.\start-platform.ps1 -Status      # 只读看状态（UP / WARN / DOWN）
.\start-platform.ps1 -Stop        # 停止全部（MySQL 为系统服务，不停）
.\start-platform.ps1 -Restart     # 先停再起
.\start-platform.ps1 -KeepAlive   # 起完不退出，前台保活（CI / 受管会话里用）
.\start-platform.ps1 -Dev         # 后端走 mvn spring-boot:run（改代码即时生效，多 ~400MB）
```

后端默认**单 JVM 跑 jar**：脚本比对 `backend/target/*.jar` 与 `backend/src` 最新修改时间，
源码有更新会自动 `mvn -DskipTests package` 后重启，不会跑到旧代码。需要 Maven 热重启行为时用 `-Dev`。

内存口径（2026-11-07 实测，提交内存）：九服务合计约 2.3GB；其中 knowledge 因收敛 torch 线程
（`OMP_NUM_THREADS=1`）从 2.6GB 降到 1.1GB，是最大的一笔。详见
`docs/一键启动脚本与冷启动验收-20261107.md` 第 9 节。

特性：

- 统一从根 `.env` 注入环境变量（JDK 17、DB 口令、run token secret、LLM 配置），Windows 大小写不敏感导致的重复键会自动去重；
- 启动前清理 `*_proxy` 并固定 `NO_PROXY=127.0.0.1,localhost`，避免系统代理劫持本机健康检查；
- 每个服务带健康门禁（HTTP 内容匹配，而不只是端口通），未就绪会打印日志尾部；
- 进程号写入 `.runtime\pids\<svc>.pid`，日志写入 `.runtime\logs\<svc>-<时间戳>.log`；
- 结束时若有关键服务未就绪，以退出码 1 失败，不会假成功。

双击入口：`scripts\windows\start-platform.cmd`（桌面版 `SmartOpsAgent-启动全部后台功能.cmd` 转发到同一脚本）。

### 桌面入口（SmartOpsAgent-启动/关闭全部后台功能.ps1）

桌面那两个脚本是**带体检的转发壳**，自身不含启停逻辑，只做四件事：

1. 定位仓库：`SMARTOPS_ROOT` → `D:\SmartOpsAgent` → 脚本所在目录及上级 → 各盘符根目录下的 `SmartOpsAgent`；都找不到则退出码 2 并给出 `setx` 指引（仓库搬家不用改脚本，设一次环境变量即可）。
2. 参数转发：桌面入口接受与 `start-platform.ps1` 相同的开关，另有 `-Open`（启动成功后打开 5173）与 `-Force`（停止后对残留端口补刀）。
3. 失败留窗口：打印退出码、日志目录、最近三个日志文件名，交互式运行时停住等回车，不会一闪而过。
4. 停止后逐端口核对八个服务，残留的报出 PID 与进程名；MySQL 只标注「仍在运行，未停止」。

`.cmd` 与 `.ps1` 必须同目录（`.cmd` 只负责拉起 `.ps1`，并透传参数与退出码）。CI 里可设 `SMARTOPS_NO_PAUSE=1` 关闭暂停。

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
