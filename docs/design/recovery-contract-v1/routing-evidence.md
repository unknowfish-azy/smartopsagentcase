# N01 真实请求路由证据（PLAN 只读核查）

- 核查方式：只读源码，定位文件与行号；**未启动服务、未运行测试、未发起真实请求**。
- 核查时间：2026-11-05（Asia/Shanghai）。
- 证据等级定义：
  - `SOURCE_OBSERVED`：本次直接读取源码/配置并记录行号。
  - `HISTORICAL`：仓库内历史文档或运行记录写明，本次未复验运行。
  - `INFERRED`：由已观察源码行推导出的结论，没有运行时 trace。
  - `UNKNOWN`：没有可核验证据。

> 本文件不把架构图、README、答辩材料当事实；只有源码行号是 `SOURCE_OBSERVED`。

---

## 1. 一条真实请求：浏览器流式聊天 → ai-service

触发路径：`AiChatPanel.vue` 提交表单 → Pinia `aiChat` store → `streamChat` → `fetch('/ai/api/chat/stream')` → Vite dev proxy（或生产网关）→ ai-service `POST /api/chat/stream`。

| # | 段 | 发起方 → 目标 | 证据（文件:行号） | 等级 | 说明 |
|---|---|---|---|---|---|
| 1 | 浏览器提交 | 表单 `@submit.prevent="sendMessage"` → `sendMessage` | `frontend/src/components/ai/AiChatPanel.vue:69`、`:309` | `SOURCE_OBSERVED` | 面板提交只调用流式路径 |
| 2 | 面板 → store | `chatStore.sendMessageStreaming(text, ...)` | `frontend/src/components/ai/AiChatPanel.vue:325` | `SOURCE_OBSERVED` | 不是 `/api/assistant` 阻塞路径 |
| 3 | store 方法 | `sendMessageStreaming` → `streamInto` → `streamChat` | `frontend/src/stores/aiChat.js:304`、`:353`、`:362` | `SOURCE_OBSERVED` | 组装 `correlation.request_id/task_id`（`:406`） |
| 4 | 浏览器 URL | `AI_SERVICE_BASE = import.meta.env.VITE_AI_SERVICE_URL \|\| '/ai'`；`fetch('/ai/api/chat/stream')` | `frontend/src/api/stream.ts:8`、`:93` | `SOURCE_OBSERVED` | 请求头含 `X-Request-ID`、`X-Task-ID`（`:97-99`） |
| 5 | 开发代理 | `/ai` → `http://127.0.0.1:8001`，去掉 `/ai` 前缀 | `frontend/vite.shared.mjs:19-24`；挂载于 `frontend/vite.config.js:30` | `SOURCE_OBSERVED` | 浏览器不直接连 8001，开发环境经 Vite |
| 6 | ai-service 路由 | `POST /api/chat/stream` | `ai-service/app/api/router.py:15-17`；`ai-service/app/api/chat.py:64-73` | `SOURCE_OBSERVED` | `chat_router` 前缀 `/chat`，总前缀 `/api` |
| 7 | ai-service 身份 | `chat_stream` 只有 `get_chat_service` 依赖；无身份/权限 `Depends` | `ai-service/app/api/chat.py:23-39`、`:64-73` | `SOURCE_OBSERVED` | 校验只来自客户端 `X-Request-ID`/`X-Task-ID`/`X-Run-ID` 与 body metadata，均为不可信标签 |
| 8 | SSE 生成 | `ChatService.chat_stream` 产出 `run/thinking/token/done/error` | `ai-service/app/services/chat.py:203-245` | `SOURCE_OBSERVED` | `done` 内嵌 `run_event`；SSE 结束不等于恢复 |
| 9 | RAG → Knowledge | `rag.retrieve` → `httpx.AsyncClient` → `POST {knowledge_service_url}/api/search` | `ai-service/app/services/chat.py:266`；`ai-service/app/services/rag.py:66-78` | `SOURCE_OBSERVED` | 默认 `knowledge_service_url = http://localhost:8002`（`ai-service/app/core/config.py:35-37`） |
| 10 | Knowledge 鉴权 | `/api/search` 使用 `Depends(require_api_key)`，按 `KNOWLEDGE_API_KEY` 可选校验 `X-API-Key` | `knowledge/server.py:284-288`、`:91-115` | `SOURCE_OBSERVED` | ai-service 侧仅在配置了 `knowledge_api_key` 时发送该头（`rag.py:59-63`） |
| 11 | Knowledge ready | `/api/ready` 用 `chunks>0` 且 manifest 非 `invalid_manifest` 判定；`/health` 是别名 | `knowledge/server.py:268-281`、`:262-265` | `SOURCE_OBSERVED` | ready 是知识索引状态，不是业务恢复证据 |

### 结论 1：浏览器流式聊天是否经 Java？

**否（开发环境已由源码证实）。** 流式路径从浏览器直接到 `/ai`，经 Vite 代理到 ai-service:8001；没有 Java controller 参与。证据链：#1-#9 全部是 `SOURCE_OBSERVED`。

### 结论 2：Java ↔ Python 调用链是否已证实？

**UNKNOWN（未证实）。**

- `backend` 的 Java 源码与本项目配置中未发现指向 `ai-service:8001` 的 HTTP 客户端调用；`MiniAssistantEngine` 的默认 baseUrl 是 `http://127.0.0.1:11434`，调用 `/api/chat`，是 Ollama，不是 ai-service（`backend/src/main/java/com/smartops/assistant/MiniAssistantEngine.java:47-51`、`:127-130`）。
- `backend/src/main/resources/application.yml:64` 的 `SMARTOPS_MINI_BASE_URL` 默认也是 `127.0.0.1:11434`。
- Java 侧的 `HttpClient` 还用于 Turnstile、模型连接、Knowledge 网页抓取；后者抓取外部 URL，不是 Python Knowledge 服务（`backend/src/main/java/com/smartops/knowledge/KnowledgeCrawlService.java:53-56`、`:92-110`）。
- 因此“Java 调 Python ai-service”或“Java 调 Python Knowledge”目前只能写 `UNKNOWN`，不能凭架构文档断言。

---

## 2. 另一条真实聊天路径：阻塞式 `/api/assistant`（经 Java）

`OpsSpiderPet.vue` 使用非流式 store 方法，走 Java Spring Boot：

| # | 段 | 证据（文件:行号） | 等级 | 说明 |
|---|---|---|---|---|
| 1 | 宠物组件 → store | `frontend/src/components/common/OpsSpiderPet.vue:277` → `chatStore.sendMessage(prompt)` | `SOURCE_OBSERVED` | 与 AiChatPanel 的流式路径不同 |
| 2 | store 阻塞方法 | `frontend/src/stores/aiChat.js:259-284` → `sendAssistantChat(...)` | `SOURCE_OBSERVED` | `:284` |
| 3 | 前端 API | `POST /api/assistant/chat`，超时 150s | `frontend/src/api/assistant.ts:11-12` | `SOURCE_OBSERVED` |
| 4 | 请求基址 | 开发 `baseURL=''`；生产 `VITE_API_BASE_URL \|\| ''`，相对 `/api` 同源 | `frontend/src/utils/request.ts:25-34` | `SOURCE_OBSERVED` |
| 5 | Java 入口 | `@RequestMapping("/api/assistant")`；`@PostMapping("/chat")`，`@AuthenticationPrincipal SessionUser` | `backend/src/main/java/com/smartops/controller/AssistantController.java:17-18`、`:33-34` | `SOURCE_OBSERVED` | 该路径有 Java 会话身份 |
| 6 | Java → 模型 | `MiniAssistantEngine` → `baseUri.resolve("/api/chat")`（默认 Ollama 11434） | `MiniAssistantEngine.java:47-51`、`:127-130` | `SOURCE_OBSERVED` | 不是 ai-service |

**结论 3：** 聊天入口存在两条互不相同的链路：
- `AiChatPanel`（流式）：浏览器 → `/ai` → ai-service:8001，不经 Java。
- `OpsSpiderPet`（阻塞）：浏览器 → `/api/assistant/chat` → Java:8080 → Ollama:11434（默认）；不经 ai-service。

---

## 3. 生产 / 网关配置核查

| 项 | 证据（文件:行号） | 等级 | 说明 |
|---|---|---|---|
| Nginx `/api/` → 8080 | `deploy/nginx/nginx.conf:156-180` | `SOURCE_OBSERVED` | Java 入口 |
| Nginx `/ai-api/` → `http://127.0.0.1:8001/api/` | `deploy/nginx/nginx.conf:199-201` | `SOURCE_OBSERVED` | 生产暴露的是 `/ai-api/`，不是 `/ai` |
| 前端默认流式基址 | `frontend/src/api/stream.ts:8` | `SOURCE_OBSERVED` | 未设置环境变量时使用 `/ai` |
| 环境变量示例 | `frontend/.env.example:7`：`VITE_AI_SERVICE_URL=`（空） | `SOURCE_OBSERVED` | 示例未给生产值 |
| 生产静态 `try_files` | `deploy/nginx/nginx.conf:136-143` | `SOURCE_OBSERVED` | `/ai` 未配置反向代理时可能落到前端 SPA |

**结论 4（INFERRED）：** 仓库内的 Nginx 只代理 `/ai-api/`，而前端默认请求 `/ai/`。若生产构建未显式设置 `VITE_AI_SERVICE_URL=/ai-api` 或完整 ai-service 地址，流式聊天在生产网关下会 404/落到 SPA。生产实际构建参数为 `UNKNOWN`，本次未读取部署环境变量，也没有运行请求。

---

## 4. 其他相关路由与语义

| 项 | 证据（文件:行号） | 等级 | 说明 |
|---|---|---|---|
| run-event schema 的定位 | `docs/development/run-event-v1.schema.json:19` | `SOURCE_OBSERVED` | `$comment` 明示“仅关联：永不作为身份、审批、成功验证或凭证传输”；N01 不改此 schema |
| ai-service 路由全集 | `ai-service/app/api/router.py:1-18` | `SOURCE_OBSERVED` | 只挂载 `/api/health` 与 `/api/chat` |
| ai-service 健康端点无鉴权 | `ai-service/app/api/health.py:9-18` | `SOURCE_OBSERVED` | 只有固定状态，不证明模型/RAG/知识可用 |
| `stream.ts` 对 `done` 的判定 | `frontend/src/api/stream.ts:127-137` | `SOURCE_OBSERVED` | 只把 SSE 完成/状态当链路完成，不涉及业务恢复 |
| Agent KnowledgeTool 默认地址 | `agent/tools/builtin/knowledge.py:87-98`、`:136-139` | `SOURCE_OBSERVED` | 默认 `http://127.0.0.1:8001` 且 POST `/api/search`；该路径不在 ai-service 已挂载路由中，属于待核验不一致项 |
| 历史启动说明 | `docs/HANDOFF-STARTUP.md:7`、`:16` | `HISTORICAL` | 文档称 Python 8001/8002 是可选独立服务，不是 `/api/assistant` 必需依赖；本次未复验运行 |

---

## 5. 未核验项（明确 UNKNOWN）

1. **生产构建是否设置 `VITE_AI_SERVICE_URL`**，以及值是否为 `/ai-api`、完整 URL 或其他网关前缀；未读取部署环境与构建产物。
2. **是否存在仓库外的网关/反代把 `/ai` 映射到 8001**；仓库内 Nginx 配置没有该映射。
3. **Java → Python（ai-service 或 Knowledge）的调用链**：源码与配置未证实；需要运行期 trace 或部署清单才能升级为事实。
4. **真实运行请求**：本 PLAN 未启动任何服务，未采集浏览器 DevTools、Nginx access log、ai-service 日志或 Knowledge 日志；所有路径均为静态源码证据。
5. **Knowledge 是否开启 `KNOWLEDGE_API_KEY`**：代码支持可选鉴权，默认空值不校验；部署环境实际值未知。
6. **ai-service 身份校验缺口在网关层是否被补偿**：`chat_stream` 无身份 `Depends`；Nginx 配置未见鉴权指令，是否存在外部认证网关未知。
7. **Agent KnowledgeTool 默认 8001 + `/api/search` 的真实部署目标**：ai-service 路由表无 `/api/search`，是配置错误、另有代理，还是指向独立 Knowledge 实例，未证实。
8. **`/api/assistant/chat` 的实际模型供应商**：默认 Ollama 11434，是否通过配置切换到其他 provider 未读取实际环境。

---

## 6. 对 N02-N05 的路由约束

- 不得把“浏览器流式聊天经 Java”写进设计或测试前提。
- 不得把 ai-service 的 `done`、run-event `succeeded`、Inspector `passed` 当作恢复证据。
- 证据采集必须走受控采集器；ai-service 的聊天/RAG 链路不是 N01-N05 的恢复探针。
- 若后续平台集成需要 Java 参与，先由 N06 在 `platform-integration.md` 登记真实调用证据，再修改路由前提。
