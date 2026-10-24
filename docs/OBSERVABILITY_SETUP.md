# Prometheus / Loki HTTP 查询接入

本轮实现固定后端数据源的真实 HTTP 只读查询。页面入口：云原生工程 → 指标实时查询 / 日志实时查询。

## 配置

在启动后端的进程环境中设置：

- `SMARTOPS_PROMETHEUS_URL`：Prometheus 服务基础地址，例如 `http://127.0.0.1:9090`。
- `SMARTOPS_PROMETHEUS_TOKEN`：可选 Bearer Token。
- `SMARTOPS_LOKI_URL`：Loki 服务基础地址，例如 `http://127.0.0.1:3100`。
- `SMARTOPS_LOKI_TOKEN`：可选 Bearer Token。

上述示例不表示服务已安装。重启后端后，页面点击「重新检查配置」，再点击「测试连接」。配置状态不等于连接成功。Loki 最小测试使用输入的 LogQL，Prometheus 使用 `vector(1)`。

## Windows 本机启动（无需 Docker）

本机开发方案使用 Prometheus 3.5.0、Loki 3.5.0、Promtail 3.5.0 和 windows_exporter 0.31.8 的官方 Windows amd64 发布包。将发布包放入 `data/local/observability/bin/`，目录应包含：

```text
data/local/observability/bin/prometheus-3.5.0.windows-amd64/prometheus.exe
data/local/observability/bin/loki-windows-amd64.exe
data/local/observability/bin/promtail-windows-amd64.exe
data/local/observability/bin/windows_exporter-0.31.8-amd64.exe
```

发布地址分别是 `https://github.com/prometheus/prometheus/releases/tag/v3.5.0`、`https://github.com/grafana/loki/releases/tag/v3.5.0` 和 `https://github.com/prometheus-community/windows_exporter/releases/tag/v0.31.8`。Prometheus Windows 压缩包的 SHA256 应为 `b3c2607d1e80a277735fd3cde86432eb1b6843897cb82fb04fbf4c7ffb1d1c36`；windows_exporter amd64 EXE 的 SHA256 应为 `03bb0fe80b8ad0b4e39606b96c4c5cc56b1f766760011ea2b00111157c6ef077`。安装前用官方发布元数据或 `sha256sums.txt` 核对，不运行未完整下载的文件。本机 Loki 直接下载地址曾超时，改用该 release 中的官方 GitHub asset API 下载成功。二进制和日志在已忽略的本地目录，不提交到 Git。

在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/observability/start-local.ps1
```

脚本启动仅监听本机的 windows_exporter `9182`、Prometheus `9090`、Loki `3100`、Promtail `9081`。Exporter 只启用 CPU、计算机系统、逻辑磁盘、网络、操作系统和系统采集器；Prometheus 抓取自身及本机 exporter 的真实指标。Promtail 只采集 `data/local/observability/logs/backend.log`，并过滤 Spring 启动时生成的安全密码行。原有容器版 `infrastructure/prometheus/prometheus.yml` 不用于本机脚本。检查：

```powershell
curl.exe http://127.0.0.1:9090/-/ready
curl.exe http://127.0.0.1:3100/ready
curl.exe http://127.0.0.1:9081/ready
curl.exe http://127.0.0.1:9182/metrics
curl.exe 'http://127.0.0.1:9090/api/v1/query?query=up'
```

确认 `up{job="windows"}` 为 `1` 后，再查询 `windows_cpu_time_total`、`windows_memory_available_bytes`、`windows_logical_disk_free_bytes`、`windows_net_bytes_received_total` 等实际主机指标。`up=1` 只证明抓取成功，不等于每个采集器都有有效数据。

后端查询会写入运行记录。如果现有 MySQL 尚无 `operation_run_record` 等三张表，先执行非破坏性建表脚本：

```powershell
mysql.exe -u root -p smartops -e "source D:/SmartOpsAgent/backend/src/main/resources/db/migration/V20260927__operation_run_tables.sql"
```

停止旧的 SmartOps 后端进程，再在启动后端的同一个 PowerShell 中设置地址。MySQL 密码从当前环境或交互输入取得，不写入脚本：

```powershell
$env:SMARTOPS_PROMETHEUS_URL = 'http://127.0.0.1:9090'
$env:SMARTOPS_LOKI_URL = 'http://127.0.0.1:3100'
cd D:\SmartOpsAgent\backend
mvn.cmd -s .mvn\smartops-settings.xml spring-boot:run 2>&1 | Tee-Object D:\SmartOpsAgent\data\local\observability\logs\backend.log
```

确认 `http://127.0.0.1:8080/actuator/health` 为 `UP`，且 `/api/observability/sources` 中两个 `configured` 均为 `true`。页面入口点击「重新检查配置」和「测试连接」；Loki 使用 `{job="smartops-backend"}` 查询。Loki 返回空列表仅说明接口可用，日志是否被采集还应检查 `9081/ready` 和实际日志流。

此本机方案覆盖 Prometheus 自身指标、Windows 本机主机指标和 SmartOps 后端日志。Docker 与 Kubernetes 尚无本机客户端或集群连接，不能显示真实容器或集群指标；接入对应数据源前应明确保持未配置状态。生产日志采集应迁移到 Grafana Alloy，并补齐身份认证、数据源授权与更完整的敏感字段过滤。

当前不支持 Basic Auth、Loki 租户请求头和页面写入凭据。保留原项目开发环境身份约定，生产部署前须完成真实用户鉴权、空间隔离和数据源访问授权。环境变量由管理员设置，不在前端、本仓库或查询审计中保存 Token。

## API

- `GET /api/observability/sources`：仅返回固定 ID、地址配置标记、Token 配置标记。
- `POST /api/observability/prometheus/query` 或 `/loki/query`。
- JSON：`{"query":"up","minutes":15,"limit":200}`；本机 Loki 示例 query 为 `{job="smartops-backend"}`。
- Prometheus 调用 `/api/v1/query_range`；Loki 调用 `/loki/api/v1/query_range`。
- 旧工具执行入口的 prometheus-query / loki-log-query 已改用同一适配器，不再执行占位 Shell。

## 限制与证据

查询表达式最多 2000 字符，最近 1–60 分钟，Loki limit 为 1–500。Prometheus 自动设置 step，结果上限 1 MiB；连接超时 3 秒、单次读取超时 5 秒。禁止跟随重定向；请求只会发往管理员配置地址。上游错误体不回显。

运行记录复用现有表；尚未初始化的本机数据库需先执行上述三表建表脚本。每次实际请求有 TraceId，保存成功/失败、时间范围和结果摘要；不持久化原始查询或原始日志。空结果是可展示的成功结果，不判定环境健康。认证失败、网络失败、响应超限均作为失败记录。

## 测试边界

自动化测试使用本地 HTTP 测试服务，覆盖编码、认证请求头、空结果、非成功状态、重定向拒绝、大小限制和审计。它不代表真实 Prometheus / Loki 已连接。未提供数据源时，页面必须显示未配置，禁止提交查询。
