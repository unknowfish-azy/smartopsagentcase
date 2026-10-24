# SmartOpsAgent 当前项目真实状态

> 最近扫描：2026-09-18（Phase 0）  
> 扫描范围：`AGENTS.md`、`README.md`、`docs/`、`backend/`、`frontend/`、`ai-service/`、`agent/`、`knowledge/`、`infrastructure/`、`scripts/`、`deploy/`、`tests/`  
> 原则：仅记录从当前工作区源码或本次命令中得到的事实；历史结果与本次实测分开记录。

> Phase 1 更新：2026-09-18 已修复本文记录的遗留 `shell=True` 与 Runtime Key 暴露风险，并新增 Inspector API/DB/UI、配置文档和训练 dry-run 基础。完整差异和最新测试结果见 `docs/OPTIMIZATION-CHANGES.md`；下文 Phase 0 内容保留作为修改前基线。

## 1. 扫描边界与目录现状

- `rg --files`（排除 `.git` 与 `frontend/node_modules`）发现约 955 个文件，包含缓存和构建产物。
- 当前目录不是可识别的 Git 工作树，`git status --short` 返回 `fatal: not a git repository`；因此无法通过 Git 判断已有改动归属或生成可靠 diff 基线。
- 要求中的主要目录均存在，但训练数据目录目前名为 `date/`，不存在 `data/`。`date/` 内已有 `demo/`、`documents/`、`evaluation/` 和 `logs/`。
- 已有 `docs/architecture/current-state.md`，本次在原有真实信息基础上扩充；未删除任何项目目录。

```text
SmartOpsAgent/
├── agent/          Agent Runtime、Policy、Sandbox、Tool、Plugin、Skill、Inspector
├── ai-service/     FastAPI AI 服务
├── backend/        Spring Boot API 与 MySQL/MyBatis 数据访问
├── date/           现有 Demo、文档、评测集和日志（目录名确为 date）
├── deploy/         Docker/Kubernetes/服务器部署文件
├── docs/           架构、API、比赛、开发、实验文档
├── frontend/       Vue 3 前端
├── infrastructure/ 基础设施配置
├── knowledge/      摄入、混合检索、版本过滤、证据、评测
├── scripts/        Windows/Linux/Common 脚本
└── tests/          API、E2E、集成、Agent、Inspector 测试
```

## 2. 技术栈与可运行状态

| 模块 | 当前技术栈 | 2026-09-18 实测 |
|---|---|---|
| Backend | Java 17、Spring Boot 3.3.5、MyBatis 3.0.4、MySQL；H2 用于测试 | `mvn test`：16 passed，BUILD SUCCESS |
| Frontend | Vue 3、Vite 7、Pinia 3、Vue Router 4、Element Plus、ECharts、Axios | `npm run build` 未执行成功：本地找不到 `vite` 命令，依赖未就绪 |
| AI Service | FastAPI、Pydantic、httpx | `python -m pytest app/tests -q`：7 passed，2 warnings |
| Knowledge | Python，内存向量检索 + BM25 + Hybrid + Version Filter + Reranker + Evidence | 可导入；本次根测试未包含独立 Knowledge 测试文件 |
| Agent | Python，Registry、Lifecycle、EventBus、Policy、Sandbox、Tools、Skills、Plugins | 根测试连同 Inspector：21 passed，24 skipped |
| Inspector | Rule Judge、Evidence Judge、AI Judge 占位实现、State Verifier、Pipeline、EventBus Trace Collector | Inspector 用例包含在根测试的 21 passed 中 |

本次测试出现的警告：Pytest 无法更新已有 `.pytest_cache`；AI Service 另有 Starlette `TestClient`/httpx 弃用警告。它们未导致测试失败。

## 3. 已冻结的现有 API 契约

以下是 Phase 0 从控制器、Pydantic Schema 与前端调用中提取的冻结基线。后续不得修改已有 URL、HTTP Method、必填字段、响应字段含义或现有调用方式；只能兼容扩展或新增 API。

### 3.1 Backend API

| Method | Path | 当前输入 | 当前输出 |
|---|---|---|---|
| POST | `/api/servers` | `name, host, port?, os?, description?` | `ApiResponse<ServerVO>` |
| PUT | `/api/servers/{id}` | `name, host, port, os?, description?` | `ApiResponse<ServerVO>` |
| GET | `/api/servers/{id}` | Path `id` | `ApiResponse<ServerVO>` |
| GET | `/api/servers` | 无 | `ApiResponse<List<ServerVO>>` |
| DELETE | `/api/servers/{id}` | Path `id` | `ApiResponse<Void>` |
| POST | `/api/servers/{serverId}/metrics` | `cpuUsage, memoryUsage, diskUsage, networkIn?, networkOut?, loadAverage?` | `ApiResponse<ServerMetricVO>` |
| GET | `/api/servers/{serverId}/metrics/latest` | Path `serverId` | `ApiResponse<ServerMetricVO>` |
| GET | `/api/servers/{serverId}/metrics` | Path `serverId` | `ApiResponse<List<ServerMetricVO>>`，最多 100 条 |
| GET | `/api/model-connections` | Header `X-User-Id`，默认 `1` | `List<ModelConnectionResponse>` |
| POST | `/api/model-connections` | `name, provider, baseUrl, modelName, apiKey, enabled, timeoutSeconds` | `ModelConnectionResponse` |
| PUT | `/api/model-connections/{id}` | 上述字段均可选；空 API Key 表示保留原值 | `ModelConnectionResponse` |
| DELETE | `/api/model-connections/{id}` | Header + Path `id` | HTTP 204 |
| GET | `/api/model-connections/{id}/runtime` | Header + Path `id` | 当前为 `ModelConnection` 实体，供内部 Runtime 使用 |

服务器 API 的统一包装为 `{ code, message, data }`，成功码为 `200`。Model Connection API 当前直接返回 HTTP JSON/204，不使用该包装；这是必须兼容的既有差异。

### 3.2 AI Service API

| Method | Path | 当前输入/输出 |
|---|---|---|
| GET | `/` | 服务名、版本、运行状态 |
| GET | `/api/health` | `{status, service, version}` |
| POST | `/api/chat` | 输入：`message, conversation_id?, use_rag, top_k, version?, metadata`；输出：`answer, conversation_id, model, provider, trust_score, citations, evidence, metadata` |

### 3.3 Knowledge API

| Method | Path | 当前输入/输出 |
|---|---|---|
| GET | `/api/health` | 状态、服务名、版本、内存 chunk 数 |
| POST | `/api/search` | 输入：`query, top_k, version?`；输出由 `KnowledgeService.search` 生成 |
| POST | `/api/documents` | 输入：`content, source, version, document_id?`；输出：`added, total_chunks` |

## 4. 当前数据库

`scripts/common/init-db.sql` 是当前 MySQL 初始化入口，包含 3 张表：

| 表 | 用途 | 关键约束/索引 |
|---|---|---|
| `server` | 服务器资产 | PK `id`；唯一 `name`；索引 `status`、`host` |
| `server_metric` | 服务器指标 | FK `server_id -> server.id`；索引 `server_id`、`collected_at`、组合时间索引 |
| `model_connections` | 用户模型连接 | AES-GCM 密文 `api_key_ciphertext`、`api_key_last4`；索引 `user_id`、`enabled`、`provider` |

目前没有 `inspector_event`、`inspector_issue`、`inspection_evidence`、`inspection_verification`、`training_dataset`、`training_run`、`evaluation_run` 或 `model_registry` 表。后续应使用兼容 migration 追加，不能删除或重建现有表。

`docs/database/schema.sql` 与运行初始化脚本不是同一事实源，后续数据库变更需同步检查，避免重复建表或文档漂移。

## 5. 当前 Frontend

### 5.1 已注册路由

| Path | 页面 | 加载方式 |
|---|---|---|
| `/` | Dashboard | 同步导入 |
| `/servers` | Server List | 同步导入 |
| `/servers/:id` | Server Detail | 同步导入 |
| `/model-settings` | Model Settings | 懒加载 |
| `/:pathMatch(.*)*` | 404 | 同步导入 |

`views/marketplace/` 下已有 Plugin Marketplace、Skill Marketplace、Skill Detail、Installed Skills 页面，但尚未注册到路由。当前共有 9 个 View 与 9 个 Component。

### 5.2 请求层与 UI 现状

- 同时存在 `frontend/src/api/http.js` 与 `frontend/src/utils/request.js` 两套 Axios 实例，超时和错误规范不同。
- Server/Metric/Model API 均保留现有 URL；后续统一请求层时必须保持调用契约。
- Main Layout 当前仅显示总览、服务器菜单和静态“系统正常”；该状态不是来自 Health API，不能作为真实运行状态。
- Dashboard、Server、Model Settings 已存在；AI Chat、Knowledge、Inspector、Agent Command Center、Trace、Training、Evaluation、Replay、System Health 尚未形成已注册页面体系。
- Model Connection 卡片读取 `apiKeyMasked`，页面没有展示完整 Key。

## 6. 当前 Agent Runtime、Registry 与安全链路

- Runtime 包含 Loader、Lifecycle、Dependency Resolver、Context、Registry 与 EventBus。
- EventBus 已定义 Plugin/Skill/Tool、Approval、Execution、Verification、Audit 事件；Inspector Trace Collector 有对应集成测试。
- Policy 包含 Permission、Risk、Policy Engine；Sandbox 包含 Process/Docker 等实现。
- 插件清单共 6 个：builtin server，以及 installed nginx、redis、mysql、docker、kubernetes。
- Skill 定义存在 builtin 与 installed 两份 `nginx-troubleshooting`；本地 Skill Loader 测试覆盖发现、加载和去重。
- 工具覆盖 server/knowledge/filesystem/shell 以及 Nginx、Redis、MySQL、Docker、Kubernetes 运维工具。

安全扫描发现一个必须后续修复的遗留实现：`agent/tools/shell.py` 调用 `subprocess.run(..., shell=True)`。新版 `agent/tools/builtin/shell.py` 明确禁用 `shell=True`，但旧文件仍在源码中；当前不能宣称全项目满足“No shell=True”。

## 7. 当前 Model Provider 与 API Key 处理

- AI Service 全局配置支持 `mock` 与 `ollama` 分支；默认是 `mock`。
- `ollama` 的真实 HTTP 调用当前被注释，实际返回明确的模拟文本，因此不能标记为真实远程模型调用成功。
- `ModelGateway` 实现 OpenAI-compatible `/chat/completions` 调用，并通过 Backend Runtime API 取得连接配置。
- Backend 使用 AES-256-GCM 存储 API Key，仅在响应中返回 `****` 加最后四位；更新时空 Key 会保留原密钥。
- 数据库字段保留 `api_key_ciphertext` 与 `api_key_last4`，符合现有 Model Connection 数据模型。
- 风险：`GET /api/model-connections/{id}/runtime` 当前返回放入明文 API Key 的实体，而 `SecurityConfig` 又允许所有 `/api/**` 匿名访问。该接口虽被注释为内部使用，但代码层尚无内部 Token 或访问控制，必须在保持内部调用兼容的前提下优先加固。

## 8. 当前 Inspector

Inspector 已实现四级流水线：

```text
Rule Judge
→ Evidence Judge
→ AI Judge（当前为可替换的占位/规则式实现）
→ State Verifier
→ InspectionResult
```

现有能力包括：

- Target：Server、Service、Knowledge、Model、Agent、Skill、Tool、Workflow、Security、Session。
- Severity：INFO、NOTICE、WARNING、HIGH、CRITICAL。
- Category：Planning、Evidence、Tool、Risk、Permission、Approval、Verification、Knowledge、Model、Security、Performance、Loop、Hallucination、Version。
- Evidence Label：SUPPORTED、PARTIALLY_SUPPORTED、UNSUPPORTED、CONTRADICTED。
- 已测场景包含 Risk Misclassification、Approval Bypass、Tool Loop、Premature State-changing Action、Evidence Insufficient、Hallucination、Version Mismatch、False Success 和 EventBus Trace。

Inspector 目前是 Python 内部服务，没有 Backend Inspector API、持久化表或 Frontend Inspector Center。

## 9. 配置与环境变量现状

- 根 `.env.example` 已存在且密钥值留空；`.gitignore` 忽略 `.env`/`.env.*` 并显式保留 `.env.example`。
- 源码实际使用的核心变量包括：`MYSQL_URL`、`MYSQL_USERNAME`、`MYSQL_PASSWORD`、`REDIS_HOST`、`REDIS_PORT`、`REDIS_DATABASE`、`REDIS_PASSWORD`、`SERVER_PORT`、`SMARTOPS_API_KEY_ENCRYPTION_KEY`、`LLM_PROVIDER`、`LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`、`KNOWLEDGE_SERVICE_URL`、`VITE_API_BASE_URL` 及 `SMARTOPS_*` 测试变量。
- `SMARTOPS_INTERNAL_TOKEN` 已在 `.env.example` 声明，但当前扫描未发现服务端实际校验逻辑。
- 未发现源码实际读取 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY` 或 `QWEN_API_KEY`；因此在后续手动配置文档中不应把它们写成当前必填项。
- `application-local.yml` 与 `application-dev.yml` 仍为 MySQL 密码提供 `root` 默认值，并内置开发专用 AES Key；可用于本地开发，但必须确保生产 profile 不继承这些默认值。
- `application-prod.yml` 的 MySQL 密码与 AES Key 无生产默认值，但用户名、主机等仍有非密钥默认值。
- `docs/MANUAL-CONFIGURATION.md` 当前不存在，是 Phase 2 的必做交付物。

## 10. 本次真实测试结果

| 范围 | 命令 | 结果 |
|---|---|---|
| Backend | `cd backend && mvn test` | **PASS：16 tests，0 failures，0 errors，0 skipped** |
| AI Service | `cd ai-service && python -m pytest app/tests -q` | **PASS：7 passed，2 warnings** |
| Root / Agent / Inspector | `python -m pytest -q` | **PASS：21 passed，24 skipped，1 warning** |
| Frontend | `cd frontend && npm run build` | **NOT RUN：`vite` is not recognized；前端依赖未安装/不可用** |

根测试的 24 个 skip 是真实结果，原因包括 Backend/AI Service 未运行、未设置 `SMARTOPS_AGENT_URL`、缺少 `mysql.connector` 和 `redis` Python 包。不能将这些集成/E2E 用例记为通过。

历史文档在 2026-09-17 记录过 Backend 16/16、AI Service 7/7、根测试 18 passed/24 skipped。本次根测试增长为 21 passed/24 skipped；这不是伪造的覆盖率提升，仅是当前测试收集与执行结果。

## 11. Phase 0 结论与后续优先级

### 已具备

- Backend 核心 Server/Metric API 与 Model Connection 存储。
- Knowledge 摄入、版本感知检索、证据和评测基础模块。
- Agent Registry、Plugin/Skill/Tool、Policy、Sandbox、EventBus 基础。
- Inspector 四级纠察核心与测试。
- Server/Dashboard/Model Settings 前端基础页面。

### 关键缺口

1. 建立可审查的 API 冻结文档或契约测试，保护上述既有接口。
2. 修复 Runtime Model API 的鉴权与明文密钥暴露风险。
3. 迁移或隔离旧 `shell=True` 实现，验证所有状态修改工具的 Permission → Risk → Approval → Sandbox → Verification 链路。
4. 创建并验证 `docs/MANUAL-CONFIGURATION.md`，区分 Local/Test/Dev/Prod。
5. 安装/恢复前端依赖后再开始比赛级 UI 增量改造，并首先保证现有构建通过。
6. 新增 Inspector API/持久化/前端，再扩展 Agent Trace、Knowledge Evidence、Training、Evaluation、Registry 与 Replay。
7. 明确 `date/` 与目标 `data/` 的迁移策略；未经确认不得删除或重命名现有目录。

## 12. 本轮未做事项

- 未修改任何现有 API、数据库表、业务源码或环境密钥。
- 未安装前端、训练或 GPU 依赖。
- 未启动 MySQL、Redis、Backend、AI Service 或 Knowledge Service 做在线联调。
- 未声称 Ollama、远程模型、训练、评测、GPU 或 E2E 已运行成功。
