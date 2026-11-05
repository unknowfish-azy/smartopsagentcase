# SmartOpsAgent 项目体检与优化建议

> 体检日期：2026-11-04
> 范围：frontend / backend / knowledge / ai-service / agent / deploy
> 方法：仓库静态盘点 + 实际运行测试 + GitHub 同类开源项目对标

---

## 一、体检总览

### 1.1 规模

| 模块 | 文件数 | 代码行数 | 测试 |
|---|---|---|---|
| frontend（Vue 3 + Vite） | 263 | 25,650 | 470 项（`node:test`） |
| backend（Spring Boot） | 220 | 15,922 | Maven 全量通过 |
| knowledge（Python 混合检索） | 77 | 4,094 | 13 项 |
| ai-service（FastAPI） | 26 | 1,544 | 47 项 |
| agent（planner/executor/inspector/policies/插件） | — | — | 含策略与执行链路测试 |
| 数据库迁移 | 41 个 SQL | — | 无迁移工具 |

界面规模：**63 个视图 / 75 条路由**。

### 1.2 分维度评分

| 维度 | 分数 | 依据 |
|---|---|---|
| 功能完整度 | 8 / 10 | 监控→分析→检索→审批→执行→审计闭环确实存在，不是 PPT |
| 测试覆盖 | 7 / 10 | 真实可运行的测试量（470 + Maven 全量 + 60），但缺组件级与端到端 |
| 检索质量 | 4 / 10 | 向量分支是哈希词袋，不是语义向量；无评测集 |
| 工程化 | 4 / 10 | 无 CI、无 lint、无迁移工具 |
| 可观测性 | 3 / 10 | 有 thinking 过程与 trace collector，但无统一 trace/eval 平台 |
| 安全边界 | 5 / 10 | 后端有鉴权与审批，但 knowledge 服务 HTTP 接口无鉴权 |
| 前端结构 | 5 / 10 | 视图过多且存在 1199 行单文件；布局与交互契约分散 |
| 文档与规范 | 8 / 10 | AGENTS.md、docs、CHANGELOG、部署说明较完整 |

**结论：产品骨架和"可信闭环"叙事是项目最强的部分；最弱的是"检索质量可证明"和"工程自动化"这两块——这恰好也是同类开源项目投入最多的地方，也解释了为什么你会觉得"还不够好"。**

---

## 二、值得肯定的部分（不要推翻重做）

1. **闭环设计完整**。风险策略 → 人工审批 → 受控执行 → 结果核查 → 审计留痕，这条链路在开源 SRE Agent 里普遍缺失（HolmesGPT 强在调查、弱在执行治理）。这是差异化资产。
2. **知识快照防漂移**。`knowledge:export` + `knowledge:check` 在 `prebuild` 里强制校验，737 条资料改动必须重导出——这个机制比多数项目做得好。
3. **只读安全默认**。MiniAssistantEngine 强制回环地址、拒绝 cloud 模型；工具权限有 manifest/permissions.yaml。
4. **测试真的在跑**。前端 470 项、后端 Maven 全量、Python 60 项均通过，不是空壳。
5. **迁移文件按业务演进编号**，演进历史可读。

---

## 三、关键问题清单

### P0-1 向量检索名不副实（最影响"专业度"观感）

**现象**：[hash_embedding.py](file:///d:/SmartOpsAgent/knowledge/embedding/hash_embedding.py#L29-L79) 用 sha256 把 token 映射到 256 维做计数，本质是**词袋哈希**。中文还做了单字 + bigram 展开，所以能工作，但与 BM25 高度同源。

**后果**：
- `vector_weight=0.6 / bm25_weight=0.4` 的"混合检索"实际上是把两路近似同质的词法信号加权融合，语义召回（同义词、改写问法）几乎没有收益。
- 宣传"向量检索/语义检索"时经不起追问。

**对标**：RAGFlow 使用真实 embedding 模型 + 向量库；Dify 支持 embedding 模型可配置。

**建议**：`knowledge/embedding/sentence_transformer.py` 已经存在但没接入。分两步走：
1. 接 `BAAI/bge-small-zh-v1.5`（约 100MB，中文效果好，CPU 可跑）作为可选 embedding backend，保持 HashEmbedding 作为零依赖 fallback；
2. 用配置项 `embedding_backend: hash | bge` 切换，避免破坏"零依赖启动"这一卖点。

### P0-2 没有检索评测集 → 无法证明"优化有没有变好"

**现象**：[sample_dataset.json](file:///d:/SmartOpsAgent/knowledge/evaluation/sample_dataset.json) 只有 **460 字节**（1 条样例）。`evaluator.py` / `metrics.py` 有实现但没数据喂。

**后果**：任何检索层改动（切分、权重、阈值、换 embedding）都无法做 A/B，只能靠感觉——这正是"感觉不够好"的根源之一。

**建议**：先建 100–200 条黄金集（query → 期望命中的 chunk/条目 id），指标用 `recall@5`、`MRR`、`nDCG@10`。数据可直接从现有 737 条资料里反向生成：每条资料出 1 条"用户会怎么问"的口语化 query。

### P0-3 数据库迁移无工具，40+ SQL 手工注册

**现象**：没有 Flyway / Liquibase（`pom.xml` 无相关依赖），全部靠 20+ 个 Config 类手工 `ResourceDatabasePopulator` 注册：

- [AssistantWorkspaceConfig.java](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/config/AssistantWorkspaceConfig.java#L33-L41)
- [TeamGovernanceSchemaConfig.java](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/config/TeamGovernanceSchemaConfig.java#L17-L19)
- [DecisionLoopSchemaConfig.java](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/config/DecisionLoopSchemaConfig.java#L21)

**后果**：执行顺序靠类加载顺序、幂等靠 SQL 自身 `IF NOT EXISTS`、回滚无记录、生产升级易漏脚本。

**建议**：落任意一种即可（推荐 Flyway，Spring Boot 原生集成）：
- 把 `db/migration/V*.sql` 改成 Flyway 命名规范，加 `flyway_schema_history`；
- 保留 H2（测试）与 MySQL（生产）双 profile，Flyway 支持多方言；
- 迁移完成后逐步删除手工 Config 类。

### P0-4 knowledge 服务 HTTP 接口无鉴权

**现象**：[server.py](file:///d:/SmartOpsAgent/knowledge/server.py#L96) 的 `POST /api/documents` 可直接写入索引，`POST /api/search` 可直接读全量知识，无 API Key、无来源校验、无请求体大小上限。

**后果**：只要端口可达（默认 0.0.0.0:8002），任何人都能污染知识库或拉走全部资料。这是"可信"叙事上的硬伤。

**建议**：加 `X-API-Key`（环境变量注入）+ 默认只绑定 127.0.0.1 + `content` 长度上限；`/api/documents` 默认关闭（`KNOWLEDGE_ALLOW_INGEST=0`）。

### P1-1 无 CI、无 lint

**现象**：
- `.github/` 目录存在但**没有任何 workflow 文件**；
- `frontend` 的 `lint` 脚本只是 `node --check` 单个文件，无 ESLint/Prettier 配置；
- Python 侧无 `ruff` / `pyproject.toml`；Java 无 checkstyle。

**建议**：一个矩阵 workflow 覆盖三件事——`npm test + npm run build`、`mvn -q test`、`pytest tests/knowledge ai-service/app/tests`。先跑通再谈覆盖率门槛。lint 用 ESLint flat config + ruff（改动最小、噪音最低）。

### P1-2 前端"宽而不深"

**现象**：63 视图 / 75 路由，最大的 [ConnectionsView.vue](file:///d:/SmartOpsAgent/frontend/src/views/operations/ConnectionsView.vue) 1,199 行、[ServerDetailView.vue](file:///d:/SmartOpsAgent/frontend/src/views/server/ServerDetailView.vue) 863 行、[RunHistoryView.vue](file:///d:/SmartOpsAgent/frontend/src/views/operations/RunHistoryView.vue) 772 行。后端同样有 [SentinelService.java](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/SentinelService.java) 1,148 行。

**后果**：新增一个能力要在多个视图里找落点；样式契约（固定高度、双栏滚动）分散在每个文件里，容易再次出现"界面太挤/怪"的问题。

**建议**：
1. 只拆最痛的 3 个文件（Connections / ServerDetail / RunHistory），按"数据层（composable）+ 视图层 + 子组件"三段切；
2. 把布局契约抽成 2–3 个基础模板（列表页 / 详情页 / 工作台），新页面不再各写一套高度与滚动；
3. 视图数量不再增加前，先做一轮"入口收敛"（合并低频页面）。

### P1-3 前端浏览器测试没进 `npm test`

**现象**：`test/` 下有大量 `*.browser.mjs`（视觉/交互验证脚本），但 `npm test` 只匹配 `test/**/*.test.mjs`。这些脚本需要人工/单独命令运行，实际处于"写了但不常跑"的状态。

**建议**：把关键 5–8 个 browser 脚本纳入一个 `npm run test:visual`，CI 里可选跑（或 nightly）。

### P2-1 缺统一 AI 链路观测

**现状**：有 `trace_collector`、thinking 步骤、trust_score，但它们是项目自定义格式，无法与业界工具对接。

**对标**：Langfuse（MIT，OTel 原生）提供 tracing / prompt 管理 / evaluation / 数据集实验。

**建议**：不引入整套平台，先按 OTel GenAI 语义导出 span（LLM 调用、检索、工具执行），保证字段可被 Langfuse/Phoenix 直接消费；后续再决定是否自建看板。

### P2-2 three.js 仍为强依赖

**现象**：`package.json` 里 `three` 常驻，源码仍有 2 处引用。知识页已移除着色器背景。

**建议**：评估剩余 2 处是否为装饰性效果；若是，改为动态 `import()` 懒加载或直接替换为 CSS，把首包再削一块。

---

## 四、GitHub 对标清单

> 星标数为体检当日通过 GitHub API 实测，未标注的不写数字以免失真。

### 4.1 Agent / AIOps

| 项目 | 定位 | 可借鉴 | 你缺的部分 |
|---|---|---|---|
| [HolmesGPT](https://github.com/HolmesGPT/holmesgpt)（3,738★，Apache-2.0，CNCF Sandbox） | SRE Agent，跨 K8s/VM/云/DB 的故障调查 | ① 按故障类型注册的"工具箱 + runbook 集"；② Operator Mode 后台 7×24 主动发现问题；③ 调查结论强制带证据链 | 你目前是"用户提问驱动"，缺主动巡检与告警触发入口 |
| [K8sGPT](https://github.com/k8sgpt-ai/k8sgpt)（CNCF Sandbox） | K8s 扫描器 + LLM 解释 | analyzer 插件模型、结构化结果对象、离线可解释 | 你的 agent 工具是命令式插件，缺"扫描器/分析器"这一层抽象 |
| [RCAEval](https://github.com/phamquiluan/RCAEval) | 根因分析评测：9 数据集 / 735 真实故障 | 评测框架 + 指标定义（可直接对表你的 inspector 判定） | 无 RCA 评测 |

### 4.2 RAG / 知识库

| 项目 | 定位 | 可借鉴 | 你缺的部分 |
|---|---|---|---|
| [RAGFlow](https://github.com/infiniflow/ragflow)（93,147★，Apache-2.0） | 深度文档理解的 RAG 引擎 | ① chunk 可视化与人工校正；② 检索测试台（同一 query 看多策略结果）；③ 真正的 embedding + 向量库 | 无 chunk 校正、无检索测试台、embedding 是哈希 |
| [Dify](https://github.com/langgenius/dify) | LLM 应用平台 | dataset 检索参数化（top_k / score_threshold / 权重 / 元数据过滤）——你已完成这一项 | 元数据过滤只到 `source` 子串，未做结构化字段 |
| AnythingLLM | 文档问答工作台 | citation 按文档合并、工作区隔离 | 已借鉴（引用分组） |

### 4.3 基础设施 / 运维底座

| 项目 | 定位 | 可借鉴 |
|---|---|---|
| [NetBox](https://github.com/netbox-community/netbox) | CMDB / IPAM | 设备—IP—服务—变更的关系模型；你的"服务器"实体目前偏扁平，缺拓扑与依赖关系 |
| [Uptime Kuma](https://github.com/louislam/uptime-kuma) | 自托管监控 | 轻量状态页与告警规则设计 |
| [Langfuse](https://github.com/langfuse/langfuse)（MIT，OTel） | LLM 可观测 | trace / eval / prompt 管理 / 数据集实验 |

### 4.4 数据集（用来补"可证明"这一环）

| 数据集 | 内容 | 用法 |
|---|---|---|
| [LogHub](https://github.com/logpai/loghub) | 17 个系统日志数据集，总量 77GB+ | 日志解析与异常检测基线；可用于你 knowledge 服务的日志类资料生成 |
| [RCAEval](https://github.com/phamquiluan/RCAEval) | 9 数据集 735 个真实故障 | 根因分析精度评测 |
| OpsEval | 7,334 道选择题 + 1,736 道 QA（公开 20% 专家子集） | 运维领域 LLM 能力基线 |
| ITBench | AI Agent 端到端运维任务评测 | 任务级（不只是问答）评测 |
| [AIOps 2025 多数据集 benchmark](https://www.aiops.cn/gitlab/aiops-live-benchmark/agenticopseval) | 微服务故障诊断 + 推理过程标注 | 需要"推理过程可评"的场景 |

---

## 五、分阶段优化路线

### 阶段 A：让"检索质量"可证明（最高优先）

1. 建黄金集（100–200 条），跑通 `recall@5` / MRR 输出；
2. 接 BGE-small-zh 作为可选 embedding（保留 hash fallback）；
3. 用黄金集对比 hash vs bge、不同 chunk_size（800 → 512/1024）、不同权重，产出对比表；
4. 把对比结果写进 README 的"检索能力"一节，替换现有模糊描述。

**验收**：`python -m knowledge.evaluation` 一条命令输出指标表；bge 相对 hash 的 recall@5 有可量化提升。

### 阶段 B：工程自动化与安全边界

1. 加 CI（三套测试 + 构建）；
2. 加 ESLint flat config + ruff；
3. Flyway 接管迁移，删除手工 Config 注册；
4. knowledge 服务加 API Key + 默认本地绑定 + 关闭开放摄入。

**验收**：PR 自动跑全量测试；`mvn test` 在干净库上可重建全部 schema；未带 Key 的 `/api/documents` 返回 401。

**进度（2026-11-05）**：

| 项 | 状态 | 证据 |
|---|---|---|
| CI 三套测试 + 构建 | 已完成 | [ci.yml](file:///d:/SmartOpsAgent/.github/workflows/ci.yml)：frontend / lint / backend / python 四 job |
| ruff 最小规则 | 已完成 | [.ruff.toml](file:///d:/SmartOpsAgent/.ruff.toml)（`E9,F`），全仓 `ruff check .` 通过，顺带清掉 12 处未使用导入/变量 |
| knowledge 鉴权 + 关闭开放摄入 | 已完成 | `KNOWLEDGE_API_KEY` → 401；默认 `/api/documents` → 403（`KNOWLEDGE_ALLOW_INGEST=1` 才放开）；ai-service 同步发送 `X-API-Key` |
| ESLint flat config | 已完成 | [eslint.config.mjs](file:///d:/SmartOpsAgent/frontend/eslint.config.mjs)：`eslint-plugin-vue` flat/essential + 浏览器/Node globals；`npm run lint` 0 error / 31 warning（`--max-warnings 31` 防回退） |
| Flyway 接管迁移 | 已完成 | `flyway-core` + `flyway-mysql`；`db/migration` 38 个脚本版本号唯一（重复日期拆为 `.1/.2`）；主配置 `baseline-version: 20261103`、测试配置 `0`；删除 11 个纯建表 Config 并收敛 3 个混合类；`V20261104__platform_admin_catchup.sql` 幂等补齐存量库治理表；`mvn test` 457 项通过（H2）。存量 MySQL 库未实测 |
| 浏览器回归纳入 npm | 已完成（部分） | 新增 [visual-suite.mjs](file:///d:/SmartOpsAgent/frontend/test/visual-suite.mjs) → `npm run test:visual`：统一起 Vite、串行跑 7 个自带 API mock 的脚本（visual-check / diagnostic-tools / model-analytics / product-quality / chat-retry / chat-focus / chat-diagnostics），7/7 通过；依赖真实后端的 browser 脚本仍需 `start-all` + `SMARTOPS_BROWSER_BASE_URL` 手工跑 |
| 超大前端视图拆分（P1-2 前两项） | 已完成 | [ConnectionsView.vue](file:///d:/SmartOpsAgent/frontend/src/views/operations/ConnectionsView.vue) 1363 → 105 行、[RunHistoryView.vue](file:///d:/SmartOpsAgent/frontend/src/views/operations/RunHistoryView.vue) 778 → 177 行；逻辑入 [useConnectionsWorkspace.js](file:///d:/SmartOpsAgent/frontend/src/composables/useConnectionsWorkspace.js)（provide/inject 共享）与 [useRunHistory.js](file:///d:/SmartOpsAgent/frontend/src/composables/useRunHistory.js)，模板拆为 14 个 `components/operations/` 子组件；行为不变，`npm test` 475 项、`lint` 0 error/31 warning、`build`、`test:visual` 4/4 全过；直接读视图源码的两个契约测试改为指向拆分后的新文件。布局模板抽取待后续 |
| 超大前端视图拆分（P1-2 第三项） | 已完成 | [ServerDetailView.vue](file:///d:/SmartOpsAgent/frontend/src/views/server/ServerDetailView.vue) 1202 → 63 行；逻辑入 [useServerDetail.js](file:///d:/SmartOpsAgent/frontend/src/composables/useServerDetail.js)，格式化纯函数入 [serverMetricFormat.js](file:///d:/SmartOpsAgent/frontend/src/components/server/detail/serverMetricFormat.js)，模板拆为 `components/server/detail/` 下 5 个子组件（Header/InfoCard/MetricOverview/NetworkCard/MetricHistory，props/emits）；[build-optimization.test.mjs](file:///d:/SmartOpsAgent/frontend/test/build-optimization.test.mjs) 的 Element Plus 按需导入契约改指 composable；行为不变，`npm test` 475 项、`lint` 0 error/31 warning 持平、`build` 通过；P1-2 三个超大视图全部拆完 |
| three.js 装饰场景按路由懒加载（P1-PERF-02 前半） | 已满足（核验） | 核验发现现状已符合契约，未改代码：ParticleWhale/MilkyWay 经 `defineAsyncComponent` + Canvas fallback 加载（[MainLayout.vue](file:///d:/SmartOpsAgent/frontend/src/layouts/MainLayout.vue)），[milky-way.vue](file:///d:/SmartOpsAgent/frontend/src/components/ui/milky-way.vue) 内 `await import('./milky-way-scene.js')`，仅 Dashboard 非轻量模式触发；契约测试 4 项与 `test:visual` 4/4 通过；vendor-three 519.73 kB 为独立异步 chunk（gzip 129.57 kB），不进首屏 |
| Codex 清单轨道 A 骨架（人工依赖项） | 进行中（仅骨架） | 新增 [P0-DATA-01 标注协议模板](file:///d:/SmartOpsAgent/docs/development/P0-DATA-01-Golden标注协议模板-v1.md)、[P0-DATA-02 许可血缘登记表模板](file:///d:/SmartOpsAgent/docs/development/P0-DATA-02-许可血缘登记表模板-v1.md)、[preflight-readiness.ps1](file:///d:/SmartOpsAgent/scripts/windows/preflight-readiness.ps1)（环境探测 + fixture/real 标签 + 日志落盘；fixture 退出 0，Real 遇 FAIL/SKIP 退出 1 阻断真实段；无固定 sleep）；**未生成或批准任何 Golden 数据**，语料/账号摘要为占位 SKIP |
| P1-PERF-02 大块拆分和长会话治理 | 已完成 | ECharts/Knowledge 懒加载核验：ECharts 四组件均为 `echarts/core` 模块导入且仅被懒加载路由视图引用（ModelAnalyticsView/Dashboard），knowledgeCatalog 30+ 领域模块仅被 KnowledgeView/QuizView/异步 SmartInquiryDrawer 引用，两者不进首屏（首屏 index 28.14 kB）；[AiChatPanel.vue](file:///d:/SmartOpsAgent/frontend/src/components/ai/AiChatPanel.vue) 全量 `v-for` 改为窗口渲染（`MESSAGE_BATCH=30` + 顶部按批示早 + 换会话重置，加载更早不触发滚底）；防回退契约 +2 项；**20 分钟同一会话 soak**：1097 轮、278,190 帧中掉帧 79 次（0.028%）、最大帧间隔 108.3 ms、pageErrors=0、答案渲染 p95 120 ms，300 条消息注入后 DOM 仅 30 个节点；`npm test` 477 项、`lint` 31 持平、`build`、`test:visual` 4/4 全过 |
| P1-PERF-01 前端性能基线 | 已完成（fixture 边界） | 新增 [performance-baseline.browser.mjs](file:///d:/SmartOpsAgent/frontend/test/performance-baseline.browser.mjs) + `npm run perf:baseline`；本机 Edge 1440×1000、`fixture=true` / `provider_e2e=false`、2 预热 + 20 采样：FCP/LCP p50 324 / p95 540 / p99 632 ms，页面就绪 p50 1501 / p95 1717 / p99 1809 ms，应答渲染 p50 67 / p95 95 / p99 96 ms（SSE 为静态 fixture，**不是真实首 token 延迟**）；20 分钟 soak 堆内存 p50 38.71 / p95 57.76 / p99 61.80 MB（首 24.28 → 末 27.95 MB，GC 锯齿非单调增长）；chunk 无新增 >500kB（唯一超限 vendor-three 519.73 kB 为既有异步 Dashboard chunk）；原始数据 [baseline.json](computer://d:\SmartOpsAgent\.runtime\performance-20261105T050450\baseline.json) |
| P1-UX-02 无障碍与响应式 | 已完成（自动化） | 新增 [accessibility.browser.mjs](file:///d:/SmartOpsAgent/frontend/test/accessibility.browser.mjs) + `npm run test:a11y`（axe-core 仅 devDependency）；4 页 × 375/768/1440 × 浅深色 24 组 + 200% 缩放代理 4 组 + 键盘 + reduced-motion：axe serious/critical **0**、横向溢出 **0**、键盘可达输入框与发送按钮且焦点环可见、违规动画 **0**、pageErrors **0**；修复 4 个真实缺陷：深色实心主按钮白字对比度 3.15 → 4.54:1（[global.css](file:///d:/SmartOpsAgent/frontend/src/assets/styles/global.css#L217-L220)）、服务器状态筛选补 `aria-label`、运行历史浅色主题 `status-failed/status-running/guide-banner` 改深色系（[RunHistoryListPanel.vue](file:///d:/SmartOpsAgent/frontend/src/components/operations/RunHistoryListPanel.vue#L162-L166) / [RunHistoryDetailPanel.vue](file:///d:/SmartOpsAgent/frontend/src/components/operations/RunHistoryDetailPanel.vue#L245-L249)）、聊天输入框补 `:focus-within` 焦点环（[AiChatPanel.vue](file:///d:/SmartOpsAgent/frontend/src/components/ai/AiChatPanel.vue#L271)）；人工读屏复核仍待人工；`npm test` 477、`lint` 31 持平、`build`、`test:visual` 4/4；原始数据 [report.json](computer://d:\SmartOpsAgent\.runtime\accessibility-20261105T053858\report.json) |
| P1-UX-02 补充：输入框自动聚焦与快捷键 | 已完成（fixture 边界） | [AiChatPanel.vue](file:///d:/SmartOpsAgent/frontend/src/components/ai/AiChatPanel.vue)：进入 /chat、新建/切换会话后自动聚焦输入框，`(pointer: coarse)` 触屏跳过以免弹软键盘；`Alt+C` 全局聚焦输入框（输入框声明 `aria-keyshortcuts="Alt+C"`），弹窗可见或焦点在其他输入控件（如侧边栏搜索）时不抢焦点；`Esc` 在草稿为空时把焦点交还消息区（`role="log"` + `tabindex="-1"`），避免焦点落到 body；输入框 `title` 提示"Enter 发送 · Shift+Enter 换行 · Alt+C 聚焦"；新增契约 [chat-focus.browser.mjs](file:///d:/SmartOpsAgent/frontend/test/chat-focus.browser.mjs)（纳入 `test:visual`，6/6 通过）：进页聚焦、标题点击后 Alt+C 回收、搜索框内 Alt+C 不抢、Enter 发送后回收、Shift+Enter 只换行、输入法组合 Enter 不误发、Esc 到消息区、新建会话后回收、切换回历史会话后回收、命令面板（原生 `dialog[open]`）打开时 Alt+C 不抢焦点，`pageErrors=0`；顺带修复真实缺陷：[CommandPalette.vue](file:///d:/SmartOpsAgent/frontend/src/components/navigation/CommandPalette.vue) 的 `Ctrl+K` 守卫只判断 `dialog[open], [aria-modal="true"]` 是否存在，而聊天页隐藏的 Element Plus 抽屉常驻 DOM（`el-overlay-dialog` 不可见），导致命令面板在该页一直打不开，改为仅遮罩可见（`getClientRects().length`）时拦截；`Alt+C` 用 `event.code === 'KeyC'` 兜底键盘布局与 macOS Option+C；`npm test` 478、`lint` 0 error/31 warning、`build` 通过、a11y 复核 serious/critical=0（[report.json](computer://d:\SmartOpsAgent\.runtime\accessibility-20261105T065911\report.json)）；仅桌面精确指针设备自动聚焦，未做真实触屏设备实测 |
| P1-UX-01 失败恢复手感 | 已完成（fixture 边界） | 新增 [chat-retry.browser.mjs](file:///d:/SmartOpsAgent/frontend/test/chat-retry.browser.mjs)（纳入 `test:visual`）：第 1 次 SSE 502 → 错误旁"重试"、草稿保留、焦点回输入框、错误含 502；原地重试后消息仍 1 问 1 答、错误消失、显示"重试成功（第 2 次尝试）"、焦点回输入框，`retrySuccessRate=100%`、`streamCalls=2`、`pageErrors=0`；实现为 [aiChat.js](file:///d:/SmartOpsAgent/frontend/src/stores/aiChat.js#L330-L407) 的 `retryMessageStreaming` + 抽取 `streamInto`（`attempt` 递增、成功后 `recovered=true`）、[AiChatPanel.vue](file:///d:/SmartOpsAgent/frontend/src/components/ai/AiChatPanel.vue#L17-L21) 的重试行/恢复状态/`focusComposer()`；修复焦点守卫缺陷：新会话发送时 `conversationId` 为 null，原 `activeId === conversationId` 判断使收尾聚焦从未执行；顺带修复 `focus()` 在输入框仍 disabled 同帧被忽略（改为等一帧）；再补场景 2（partial）：首个 token 后收到 `error` 事件中断 → 已输出内容与上游中断原因都保留、草稿保留、焦点回收，持久化 `metadata.run_event.status=failed`（`run_id=run-partial`、`attempt=1`）→ 原地重试后消息仍 2/2、partial 被完整回答替换、`attempt=2`、`recovered=true`、`run_event.status=succeeded`（`run_id=run-retry-2`），`retries=2`、`streamCalls=4`、`retrySuccessRate=100%`、`pageErrors=0`；再补场景 3（刷新）：再次 502 后刷新页面 → 3/3 条消息与 502 原因仍还原、重试按钮 `aria-label` 说明尝试次数且可点 → 原地重试成功（消息仍 3/3、`attempt=2`、`recovered=true`、焦点回收），`retries=3`、`streamCalls=6`；顺带修复两个真实缺陷：(1) [history.ts](file:///d:/SmartOpsAgent/frontend/src/domain/chat/history.ts) 的 `restoreHistory` 丢弃 `prompt/attempt/recovered/images`，刷新后错误旁重试按钮存在但点不动，现随历史还原，且 `retryMessageStreaming` 在 prompt 缺失时回退到上一条用户消息；(2) `onDone` 只合并 `payload.metadata`，而 [stream.ts](file:///d:/SmartOpsAgent/frontend/src/api/stream.ts) 允许最终 run 事件落在顶层 `payload.run_event`，导致成功回答残留 `started`，现两处都读取；`npm test` 478、`lint` 0 error/31 warning、`build`、`test:a11y` 复核 serious/critical=0；**真实 Provider 故障注入未覆盖，归 P0-E2E-02** |
| P1-RUN-02 完成运行诊断 | 已完成（fixture 边界） | 诊断区新增 effective provider、降级/原因、RAG 状态/top_k/原因、引用数、inspection、首 token/总耗时，并提供 run_id/request_id 复制（含"已复制/复制失败"反馈）与"打开运行记录"入口（[AiChatPanel.vue](file:///d:/SmartOpsAgent/frontend/src/components/ai/AiChatPanel.vue)、耗时记录见 [aiChat.js](file:///d:/SmartOpsAgent/frontend/src/stores/aiChat.js) 的 `streamInto`）；[history.ts](file:///d:/SmartOpsAgent/frontend/src/domain/chat/history.ts) 白名单持久化上述字段（字符串截断、布尔/数字校验、inspection 仅安全子字段），刷新后诊断仍完整；新增 [chat-diagnostics.browser.mjs](file:///d:/SmartOpsAgent/frontend/test/chat-diagnostics.browser.mjs)（纳入 `test:visual`，7/7）：成功场景显示 `openai-compatible:qwen2.5-7b`/未降级/`rag_status=ok`+`top_k 5`/引用 2 条/`PASS`/`n ms`，复制 `run_id`/`request_id` 写入剪贴板；降级场景显示回落 `mock-local`、降级原因、`rag_status=empty`、检索降级原因、引用 0 条、`REJECTED`；刷新后字段仍完整，`fixture=true` / `provider_e2e=false`、32 项断言、`pageErrors=0`；"打开运行记录"仅跳 `/operations/runs`，**不带 run_id 参数**（运行记录页无该过滤口径，不伪造匹配）；**真实 Provider 与真实 run 关联未覆盖，归 P0-E2E-01/P0-RUN-01** |
| P0-RUN-01 跨层 run 对照表 | 进行中（AI/Knowledge/执行器已打通） | 新增 [P0-RUN-01-跨层run对照表-20261105.md](file:///d:/SmartOpsAgent/docs/development/P0-RUN-01-跨层run对照表-20261105.md)：前端 [stream.ts](file:///d:/SmartOpsAgent/frontend/src/api/stream.ts) 头/体同一组 ID；AI [correlation.py](file:///d:/SmartOpsAgent/ai-service/app/core/correlation.py) 解析/回显并在 [chat.py](file:///d:/SmartOpsAgent/ai-service/app/services/chat.py) 记录 `chat.start`/`chat.rag`/`chat.terminal`；[rag.py](file:///d:/SmartOpsAgent/ai-service/app/services/rag.py) 转发；[server.py](file:///d:/SmartOpsAgent/knowledge/server.py) 回显并记录 `knowledge.search`；[executor.py](file:///d:/SmartOpsAgent/agent/executor/executor.py) 记录终态。五类终态各 1 条真实记录（success `req-live-2`/`a36548bf…`、degraded `req-degraded-1`/`6601f164…`、failed `CHAT_PIPELINE_FAILED`、interrupted `LLM_STREAM_INTERRUPTED`、denied 执行器拒绝），AI+Knowledge 真实进程日志与 SSE ID 一致；AI 53 通过、Knowledge 全过、前端 13/13；日志含 ID/状态/结果数，不含 Prompt/密钥/query/异常栈；**未闭环**：聊天直连 AI 不经 Java、Java `trace_id`↔`run_id` 无映射、Provider 无 trace、本机 JDK21 不兼容未重跑 Maven、真实 Provider 故障注入归 P0-E2E-02 |
| P1-OBS-01 可观测性对照表 | 进行中（只读核查完成） | 新增 [P1-OBS-01-可观测性对照表-20261105.md](file:///d:/SmartOpsAgent/docs/development/P1-OBS-01-可观测性对照表-20261105.md)：浏览器/SSE/Java/AI/Knowledge/Provider 六层对照、脱敏字段白名单、成功/失败时间线与“一次失败可复盘”边界；真实证据：`run_event` 9 字段与 schema 集合一致、`additionalProperties=false`、未知状态 `ValueError`；`node --test` 10/10（白名单会丢弃任意 metadata）；AI→Knowledge 关联头与 Knowledge 请求标识已由 P0-RUN-01 补齐；**跨层仍未闭环**：浏览器直连 AI 不经 Java、Java `trace_id` 与 AI `run_id` 无映射、Provider 无 trace；依赖 ARCH-P0-01/05 / P0-E2E-01/02 |

> 401/403 口径：未配置 key 时摄入返回 403（表示功能关闭）；配置 key 后缺失/错误 key 返回 401。

### 阶段 C：结构与观测

1. 拆分 3 个超大前端文件，抽 3 个布局模板；
2. OTel 语义导出 AI 链路 span；
3. 入口收敛，控制视图数量。

### 阶段 D：产品能力对标（差异化）

1. 告警驱动调查（参考 HolmesGPT Operator Mode）：把 sentinel 告警 → 自动发起调查 → 生成证据与建议；
2. CMDB 关系模型（参考 NetBox）：服务器/服务/依赖，支撑"影响面分析"；
3. 用 RCAEval / ITBench 做一次端到端评测，作为对外可信度证据。

---

## 六、明确不建议做的事

1. **不要为了压包而拆知识点 meta/content**。实测正文仅占原始体积 39%，收益不到预期的三成，代价是重构约 40 个数据源模块 + 9 个测试文件。
2. **不要引入完整 RAGFlow / Dify**。你的价值在"执行治理闭环"，把检索引擎换成第三方会丢掉与审计链路的耦合；只抄它们的评测与 chunk 治理方法。
3. **不要继续加视图**。当前 63 视图已超过可维护密度，新增能力优先在现有页面内扩展。
4. **不要在"向量检索"上只改文案**。要么接真 embedding，要么把措辞改成"词法 + 哈希向量混合检索"，避免可信度质疑。

---

## 七、附：本次体检使用的命令

```powershell
# 规模统计
Get-ChildItem frontend/src -Recurse -File | Where-Object { $_.Extension -in '.js','.vue' } | ...
# 测试
cd frontend; npm test; npm run build
cd backend; mvn -q test          # 需 JDK 17
python -m pytest tests/knowledge ai-service/app/tests -q
```

> JDK 说明：本机 `JAVA_HOME` 指向损坏的 openjdk21，可用 `C:\Users\33908\scoop\apps\openjdk17\17.0.2-8` 替代（绕开 scoop shims）。
