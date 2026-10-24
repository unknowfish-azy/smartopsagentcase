# SmartOpsAgent 交接环境准备与启动指南

适用：Windows 本地源码交付，2026-10-17 配置核对。命令从项目根目录执行。本文不代表接收方机器已完成安装或验收。

## 1. 环境与服务

默认交付主链路是 Vue 双前端 → Java 后端 → MySQL；模型按 Mini/Ollama 或外部模型路径配置。Python 8001/8002 是可选独立服务，不是当前 /api/assistant 聊天入口的必需依赖。Redis 按启用功能和健康检查验收；当前会话注册表使用 Java 进程内存，不能据此宣称多实例会话共享已完成。详见 [架构调整决策](ARCHITECTURE-DIRECTION.md)。

|服务|环境|默认端口|用途|
|---|---|---|---|
|数据库|MySQL 8.x|3306|核心数据持久化|
|后端|JDK 17、Maven|8080|登录、业务 API|
|用户前端|Node 22.12+（建议 Node 22 LTS）、npm|5173|用户入口|
|管理前端|同上|5174|独立管理入口|
|Redis|Redis 7.x|6379|已配置的缓存/状态与健康检查依赖|
|AI 服务|Python 3.10–3.12 建议|8001|可选 Python AI 接口|
|知识服务|Python，同一虚拟环境可用|8002|可选独立 HTTP 知识检索|
|Mini|Ollama、qwen3:1.7b|11434|Java 后端内置模型路径|

Docker 是 MySQL/Redis 的一种部署方式，不是应用本身必需环境。现有 start-dev.ps1 和 check-env.ps1 强制检查 Docker，采用原生服务时按本指南分别启动。Git 用于源码管理；构建依赖需要网络或事先准备完整离线缓存。前端建议 npm ci 重建依赖，不依赖搬来的 node_modules。Python 虚拟环境也应在接收方重建。

LLM_PROVIDER=mock 只控制 Python AI 服务，不会把 Java Mini 自动变为 mock。是否需要 Python 服务、Mini 或外部模型应按交付功能逐项验收，不能把登录页可见当成全功能可用。

## 2. 准备本机配置

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

设置 MYSQL_URL、MYSQL_USERNAME、MYSQL_PASSWORD，首个管理员 SMARTOPS_BOOTSTRAP_USERNAME/PASSWORD，以及 SMARTOPS_API_KEY_ENCRYPTION_KEY、SMARTOPS_INTERNAL_TOKEN。AES 密钥须为 32 个随机字节的 Base64，内部 Token 应独立生成。不要使用示例默认密码作为交付密码。

迁移既有数据库时，同时移交其实际使用的加密密钥，否则已有模型凭据可能解密失败；通过单独的受控渠道传递，不写入源码包。不要无条件轮换数据库关联的加密密钥。

每个启动服务的新 PowerShell 窗口都先从项目根目录执行以下加载片段。它只将键值作为字符串处理，不执行 .env 内容：

```powershell
Get-Content -LiteralPath .env -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $name = $matches[1]
        $value = $matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}
```

根目录 .env 不会被 Vite 或 Spring 自动读取；当前 Python Settings 的 env_file=.env 也相对于工作目录。以上显式加载解决进程继承问题。当前 start-dev.ps1 未实现该加载、知识服务启动或数据库迁移，不将它作为完整的一键交付安装器。

## 3. 数据库和 Redis

原生方式：先启动接收方自行安装的 MySQL/Redis 服务，确认地址与配置一致。端口冲突时识别占用进程，再选用现有服务或改端口；不要直接停掉对方其他业务服务。

Docker 方式：安装并启动 Docker Desktop，填入 .env 的 MYSQL_ROOT_PASSWORD、MYSQL_DATABASE=smartops、MYSQL_USER=smartops，并让 MYSQL_USERNAME=smartops，MYSQL_PASSWORD 为该普通账户的密码。MYSQL_ROOT_PASSWORD 与普通账户密码是两个不同配置。

```powershell
docker compose --env-file .env -f deploy/docker/docker-compose.yml up -d
if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed' }
docker compose --env-file .env -f deploy/docker/docker-compose.yml ps
```

已有数据卷不会因修改环境变量自动更新数据库密码。Redis Compose 当前未配置密码认证；如需密码，需要同步修改 Redis 配置及健康检查，不能只填写 REDIS_PASSWORD。

原生 MySQL 新库初始化（将 MySQL 客户端目录加入 PATH，使用实际账户，-p 交互输入密码）：

```powershell
mysql -h 127.0.0.1 -P 3306 -u root -p --execute="source scripts/common/init-db.sql"
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed' }
./scripts/windows/migrate-local.ps1 -MysqlBin 'C:\Program Files\MySQL\MySQL Server 8.0\bin'
```

migrate-local.ps1 会先备份已有 smartops 库，再按内置顺序执行 7 个迁移并记录校验和；它不负责创建不存在的库。目前固定连接 127.0.0.1:3306，非默认地址需另行适配迁移流程。Docker 数据库也可使用宿主 MySQL 客户端连接映射端口执行此流程。已有数据库先备份并核对迁移账本，不要直接导入覆盖。

## 4. 安装依赖与分别启动

安装依赖（一次性）：

```powershell
Push-Location frontend
npm ci
if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
Pop-Location
```

仅交付 Python 独立服务时，再执行：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r ai-service/requirements.txt -r knowledge/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
```

SSH 隧道等附加工具按实际交付功能安装其 requirements；knowledge 依赖可能下载较大的模型相关库，提前准备网络及磁盘空间。

核心服务分别打开 PowerShell，在项目根目录加载第 2 节环境，然后执行下列对应命令。AI/知识服务两段仅在交付对应 Python 功能时执行。启动过程日志应保留：

```powershell
# 后端窗口
Set-Location backend
mvn spring-boot:run
```

```powershell
# 用户前端窗口
Set-Location frontend
npm run dev
```

```powershell
# 管理前端窗口
Set-Location frontend
npm run dev:admin
```

```powershell
# AI 窗口，从根目录执行，显式使用根配置的进程环境
./.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir ai-service --host 127.0.0.1 --port 8001
```

```powershell
# 知识服务窗口，从根目录执行
./.venv/Scripts/python.exe -m uvicorn knowledge.server:app --host 127.0.0.1 --port 8002
```

Mini 路径需要安装 Ollama 并准备模型：`ollama pull qwen3:1.7b`；确认服务监听 11434（已有服务时不再重复启动）。外部模型路径在产品中单独配置并验证。

## 5. 验收与交付清单

1. MySQL 实际登录成功；迁移脚本完成且账本存在。
2. 后端启动完成，检查 http://127.0.0.1:8080/actuator/health；Redis 缺失可能使聚合健康失败，按日志判断。
3. http://127.0.0.1:5173/login 与 http://127.0.0.1:5174/login 可访问；分别完成正确角色登录、人机验证和权限验证。
4. 验证业务 API 返回真实数据库数据，刷新后数据仍存在；只有静态登录页出现不算部署成功。
5. 如交付 Python 功能，检查 http://127.0.0.1:8001/api/health 与 http://127.0.0.1:8002/api/health，并做一次实际调用。
6. 如交付对话/RAG，验证所选模型真实回答及知识检索；mock 仅说明流程跑通。
7. 记录版本、启动命令、端口、账户交接方式、备份位置和停机方法。本文未重新探测本机实时端口，也不把历史运行状态作为当前事实。

源码包可排除 node_modules、backend/target、构建缓存、个人无关目录；先生成清单再打包，不删除原工程。默认排除 .env、.runtime/secrets、数据库备份、真实上传资料及工具会话数据。用户确需迁移的数据单独备份与交接。模型文件按离线运行需求决定是否另包。不要复制整个用户 .m2/settings.xml，以免携带私服凭据；离线依赖缓存单独准备。

现有脚本有 MySQL 安装路径和 Java 安装布局默认值；相对项目路径不意味着接收方无需配置这些工具路径。本指南是本地开发交接流程，公网部署另需反向代理、TLS、会话与访问控制配置。
