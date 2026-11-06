# 部署面实机验收：docker compose up -d --build（SEC-13 / PERF-08）

- 日期：2026-11-06 晚（22:10–24:00，Asia/Shanghai）
- 目的：把"可运行发布"从"文档里存在"推进到"真的起得来"，并验证 SEC-13 的端口/口令收敛在运行时确实生效。
- 结论：**四容器全部 healthy，backend readiness 200；SEC-13 三条部署断言（端口不发布、Redis requirepass、生产启动断言）全部实机通过。**过程中发现并修复 3 个导致发布面跑不起来的缺陷（下详）。

## 1. 执行环境

| 项 | 值 |
| --- | --- |
| Docker | Docker Desktop，engine `29.8.0`（WSL2 后端） |
| 宿主机 | Windows，仓库 `d:\SmartOpsAgent` |
| compose 文件 | `deploy/docker/docker-compose.yml` |
| 网络出口 | 本机 Docker Desktop **未配置 HTTPS 代理**，`registry-1.docker.io` 直连超时；基础镜像经 `docker.m.daocloud.io` 拉取后本地重打 tag |
| 端口 | 宿主机 8080 已被本机 local profile 后端占用，故 compose 后端改用 `BACKEND_PORT=18080` |
| 口令 | 随机强口令临时注入（未写盘、未提交），满足 `${VAR:?}` 必填 |

前置动作：

```bash
docker pull docker.m.daocloud.io/library/maven:3.9-eclipse-temurin-17
docker pull docker.m.daocloud.io/library/eclipse-temurin:17-jre
docker tag  docker.m.daocloud.io/library/maven:3.9-eclipse-temurin-17 maven:3.9-eclipse-temurin-17
docker tag  docker.m.daocloud.io/library/eclipse-temurin:17-jre eclipse-temurin:17-jre
```

- `mysql:8.4`、`redis:7.4`、`python:3.12-slim` 本机已有缓存，无需外网。
- 验证过的替代路径不改变仓库配置：镜像来源只是本机缓存，compose/compose 文件里仍是官方镜像名。

## 2. 发现的缺陷与修复（均由本次实机运行暴露，此前只有 `docker compose config` 的静态校验）

### 2.1 全新库无法完成 Flyway 迁移（backend 启动即失败）

- 现象：backend 首次启动 `Migration V20261104__platform_admin_catchup.sql failed`，`SQL State 42S02 / Error Code 1146`；`flyway_schema_history` 里只有 `20261103 baseline` 与一条失败的 `20261104`。
- 根因：`deploy/docker/mysql/init/01-init.sql` 在建库同时先建了 `server` / `server_metric` 并插入演示数据，使全新库在 backend 启动前就"非空"。`application.yml` 是 `baseline-on-migrate: true` + `baseline-version: 20261103`（设计意图见其注释："全新库（空 schema）仍会从 V001 开始全部执行"），于是 V001~V20261003 被视为已应用跳过，只跑 20261104 及之后；该脚本引用 `app_user` 时表根本不存在。
- 修复：`01-init.sql` 只保留建库，表结构一律交给 Flyway（`V20261002` 才真正建 `server`/`server_metric`）。
- 复验：清空数据卷后重启，`flyway_schema_history` 成功 60 条 / 失败 0 条，`app_user` 存在，backend healthy。

### 2.2 ai-service 镜像缺 `agent` 包（容器起不来）

- 现象：`ModuleNotFoundError: No module named 'agent'` at `app/services/chat.py`。
- 根因：`app/services/chat.py` 运行期 `from agent.runtime_events import ...`、`from agent.inspector...`，而 `agent/` 在**仓库根目录**；原先 compose 的 build context 只有 `ai-service/`，镜像里没有这个包。
- 修复：ai-service 构建上下文改为仓库根（`context: ../..`, `dockerfile: ai-service/Dockerfile`），Dockerfile 追加 `COPY agent ./agent`；新增根目录 `.dockerignore`，只放行 `ai-service/`、`agent/`，避免把 GB 级仓库整体发给 BuildKit。
- 复验：镜像重建后 `HEALTHCHECK` 持续 `GET /api/health 200`，容器 healthy。

### 2.3 生产启动断言读错属性，导致 prod 永远起不来

- 现象：prod profile 下（口令/密钥均已注入）仍报 `SECURITY_ASSERTION_FAILED: SMARTOPS_API_KEY_ENCRYPTION_KEY 未配置`。
- 根因：`SecurityAssertionConfig` 读的是 `smartops.attachments.api-key-encryption-key`，而 `application.yml` 实际定义与 `AesGcmCryptoService` 读取的路径都是 `smartops.security.api-key-encryption-key`。该属性恒为空，生产判定的"密钥为空"分支永远命中。
- 修复：断言改读 `smartops.security.api-key-encryption-key`。
- 复验：prod profile + 全量注入 → `SECURITY: 启动断言通过（production=true）`，`/actuator/health/readiness` 返回 `{"status":"UP"}`。

### 2.4 附：密钥格式要求（非缺陷，易踩）

`SMARTOPS_API_KEY_ENCRYPTION_KEY` 是 **Base64 编码的 32 字节**，不是任意 32 字符；填 32 个十六进制字符会报 `API Key 加密密钥必须为 32 字节`。

## 3. SEC-13 运行时验证结果

| 检查项 | 结果 |
| --- | --- |
| `docker compose config`（缺必填口令） | exit 1，8 处 `required variable ... is missing`（与 2026-11-06 早先静态校验一致） |
| `docker compose config`（注入强口令） | exit 0 |
| `docker port smartops-mysql` | 空（3306 未发布） |
| `docker port smartops-redis` | 空（6379 未发布） |
| `docker port smartops-ai-service` | 空（8001 未发布，SEC-01 网络层隔离） |
| `docker port smartops-backend` | 仅 `8080/tcp -> 0.0.0.0:18080` |
| `redis-cli ping`（无口令） | `NOAUTH Authentication required.` |
| `redis-cli -a <口令> ping` | `PONG` |
| `docker inspect smartops-redis .Config.Cmd` | 含 `--requirepass <口令>` |
| prod profile + `internal-bypass=true` | 进程 exit 1，`SECURITY_ASSERTION_FAILED: ... 必须为 false` |
| prod profile 正常注入 | 启动成功、断言通过日志、readiness `UP` |
| 四容器最终状态 | mysql/redis/ai-service/backend 全部 `Up (healthy)`；backend `http://127.0.0.1:18080/actuator/health/readiness` → HTTP 200 |

## 4. 回归

- 后端全量 `mvn -s .mvn/smartops-settings.xml test`：**769 项，0 失败，0 错误，1 skipped，BUILD SUCCESS**（含本次 `SecurityAssertionConfig` 改动）。
- 未跑 Python 全量（本次未改 Python 代码）。

## 5. 边界与未验证（不得据此声称已完成）

- `nginx -t` 仍未执行：本机无 nginx 二进制/镜像，网络出口受限无法拉取。
- Docker Hub 直连不可用属环境限制：本次以本机缓存 + 国内镜像重打 tag 绕过，**未修改** compose 的镜像名，也未把镜像加速器写入仓库。
- Windows 下 bind mount 的 `deploy/docker/mysql/conf/my.cnf` 权限为 world-writable，MySQL 启动警告 `World-writable config file ... is ignored` —— 该自定义 my.cnf 实际未生效（开发环境无实际影响，Linux 宿主机不会出现）。
- 数据卷：首次失败的数据卷（2026-10-04 创建，仅含 2 行演示数据 `server`/`server_metric`）已被 `docker compose down --volumes` 移除后重建；当前卷内为 Flyway 全量迁移结果，无业务数据。
- 公网出口下的真实 DNS rebinding 复验仍为 `NOT_RUN`（见 `安全整改-DNS-rebinding注入实验-20261106晚.md`）。

## 6. 变更文件

| 文件 | 变更 |
| --- | --- |
| `deploy/docker/mysql/init/01-init.sql` | 只建库，不再预建表/插演示数据（消除 Flyway baseline 误跳过） |
| `ai-service/Dockerfile` | `COPY ai-service/app` + `COPY agent`（运行期依赖） |
| `deploy/docker/docker-compose.yml` | ai-service build context 改为仓库根 |
| `.dockerignore`（新增） | 根上下文只放行 `ai-service/`、`agent/` |
| `backend/.../config/SecurityAssertionConfig.java` | 断言属性路径修正为 `smartops.security.api-key-encryption-key` |

复现命令（环境变量自备，勿提交口令）：

```bash
docker compose -f deploy/docker/docker-compose.yml up -d --build
docker compose -f deploy/docker/docker-compose.yml ps
docker port smartops-mysql; docker port smartops-redis; docker port smartops-ai-service
docker exec smartops-redis redis-cli ping                       # 期望 NOAUTH
docker exec smartops-redis redis-cli -a "$REDIS_PASSWORD" ping   # 期望 PONG
curl -fsS http://127.0.0.1:8080/actuator/health/readiness
```
