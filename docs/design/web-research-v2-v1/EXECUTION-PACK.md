# 联网研究 阶段四 执行包 v1.0（工作包 T33–T36）

> 交实现模型照做。前置阅读同目录 `DESIGN.md` 与 `docs/web-research-radar.md`。
> **D1–D6 用户已确认采纳默认建议（2026-11-16），方案定稿，工作包 T33–T36 可按序开工。**
> 每个包首行红线（复述一遍）：不自动事实裁决/可信度评分；不模型自训练/权重提示词写入；不绕过登录付费墙反爬；
> 不改省赛已封版材料；禁写"准确率 9X%"；数据全 DRAFT 只报样本量与窗口。
> 门禁纪律：typecheck 0 / lint 0 error（仅既有 1 warning）/ 双端 build / 后端全量单测不回退（774 基线）/ 浏览器实测 0 pageError。
> 承接 T28–T32，独占编号 T33–T36，不冲突。

## 锚点（已核实，勿重勘察）

- 检索：`backend/src/main/java/com/smartops/knowledge/WebResearchService.java`（`search/fetch/createTask/finishTask`、`MAX_PAGE_TEXT=16000`、`parseWebResults/parseGithubResults` static、GitHub 仓库识别 `githubRepository()`）。
- 安全出站：`backend/src/main/java/com/smartops/knowledge/KnowledgeCrawlService.java`（`fetch(url,accept)` 逐跳 `OutboundUrlPolicy.inspect`+`PinnedDns.pin`、4 跳、`MAX_DOWNLOAD_BYTES=10MB`、`RUN_DEADLINE_SECONDS=60`、`CRAWL_PERMITS=4`、`htmlToText/pageTitle/sha256/normalizeUrl/stripQuery/errorCode/redact`）。
- 证据：`WebResearchEvidenceService.java`（shingle8+Jaccard、有界 LCS 400 行、跨用户 404）、`WebResearchController.java`（`/api/web-research/*`）。
- 调度：`KnowledgeCrawlService.runDueMonitor()`（`sweep-ms=30000`/`initial-delay-ms=60000`、`SELECT ... LIMIT 1`、`next_run_at`）。
- 快照表：`V20261115__web_research_radar.sql` + `V20261115.1__web_research_candidates.sql`（`web_research_task/page`、`knowledge_crawl_source/page`、候选唯一约束）。
- 凭证：`backend/src/main/java/com/smartops/common/crypto/AesGcmCryptoService.java`（`encrypt/decrypt`，key `SMARTOPS_API_KEY_ENCRYPTION_KEY` Base64 32B）；断言 `security/SecurityAssertions.java` + `config/SecurityAssertionConfig.java`。
- 配置：`backend/src/main/resources/application.yml`（`smartops.*` 分区；radar 两键尚未显式声明）。
- 前端：`frontend/src/views/research/{WebResearchView,RadarView}.vue`、`components/research/{RelationGraph,EvidenceCompare}.vue` + `relationGraph.js`/`evidenceSelection.js`、`api/webResearch.ts`（`unwrap=v=>v?.data??v`）。
- 测试设施：`frontend/package.json` 有 `playwright ^1.63.0`；`frontend/test/*.browser.mjs`；mock 路由**锚定根 `/api/`**（勿用 `**/api/**`，误匹配源码致白屏，已踩坑）。
- 后端测试：`WebResearchServiceTest.java`、`WebResearchEvidenceServiceTest.java`、`WebResearchEvidenceControllerTest.java`、`KnowledgeCrawlServiceTest.java`、`SmartOpsApplicationIntegrationTest`（H2）。

---

## T33 · JS 渲染只读工具（含显式登录接续最小版）

**裁决已定（D1/D2）**：D1=JS 渲染纳入但默认关、按页"JS 重试"；D2=做最小只读会话接力（显式登录+加密会话+清除入口，不代填）。均已确认，按此执行。

### a. 渲染抽象与策略复用（后端）
- 新增 `backend/src/main/java/com/smartops/knowledge/WebRenderService.java`：
  - `render(actor, url, useJs)`：静态分支直接委托 `crawler.fetch(url)` + `htmlToText`（等价现有 `fetch`）；JS 分支走受控渲染器（下 b）。
  - 入站前统一 `OutboundUrlPolicy.inspect(uri)`，`!allowed()` 直接 `BusinessException(400,"WEB_RENDER_URL_BLOCKED")`；**不新造白名单**。
  - 提取文本一律 `OperationRedactor.redact`，存前 `KnowledgeCrawlService.stripQuery(url)` 去 query/fragment；hash 用 `KnowledgeCrawlService.sha256`。
  - 返回在 `WebResearchService.WebPage` 基础上加 `renderMode(STATIC|JS)`、`renderNote`（如实说明是否渲染/是否用会话），字段语义不变。
- 复用现有 `createTask/finishTask` 记录任务；JS 失败落 `WEB_RENDER_FAILED:<code>`，走 `errorCode()` 派生，不落原始异常。
- 单测 `WebRenderServiceTest.java`：URL 阻断、静态/JS 分派、脱敏调用、hash 一致、失败错误码、空正文拒绝。

### b. 受控无头渲染器（后端 + 独立进程隔离）
- 新增 `backend/src/main/java/com/smartops/knowledge/HeadlessRenderer.java`（接口）+ `PlaywrightRenderer.java`（实现，可注入替换）：
  - 通过本地受控浏览器进程渲染，**只在隔离 profile 运行**：`--no-sandbox`（若容器要求）、禁本地文件访问、禁自动下载、禁扩展；导航目标必须是已由 a 校验的 URL。
  - 重定向逐跳回调复用 `OutboundUrlPolicy.inspect`，沿用 4 跳上限；出现内网/保留网段立即终止。
  - 超时与体量：新增 `smartops.web-research.render.timeout-ms`（默认 15000）、`render.max-content`（默认 20000），渲染体上限 10MB 与静态链一致；超时 `Thread.interrupt` 回收进程。
  - **只读**：渲染后仅取 `document.title` 与正文文本（去 script/style/nav/footer），不执行表单提交/自动点击；提取文本按不可信资料处理，不进 Agent 指令链。
  - 渲染器不可用时（无浏览器/驱动缺失）返回明确 `RENDERER_UNAVAILABLE`，**不回退伪造静态正文**；静态分支独立可用。
- 若本机无 Playwright 运行时，实现模型可先用"可注入的假渲染器 + 契约测试"覆盖逻辑，再在具备运行时的机器补真实渲染；**不得把假数据当真实验收**。

### c. 显式登录接续最小版（后端 + 前端，D2）
- 会话实体：新增表（迁移 `V20261116.1__web_render_session.sql`，D2 已确认通过）：
  `web_render_session(id, user_id, enc_storage_state TEXT, display_hint VARCHAR(64), created_at, expires_at, last_used_at)`，
  唯一键 `(user_id)`（一人一会话，重登覆盖）。storage state 用 `AesGcmCryptoService.encrypt()` 落库，`decrypt()` 载入；**明文 Cookie/token 不落库、不进日志、不回前端**。
- 接口（`WebResearchController` 或新 `WebRenderController`）：
  - `POST /api/web-research/render-session/start` → 返回一次性会话句柄与"请在弹出的受控窗口自行登录"提示（工具**不代填凭据**）；
  - `POST /api/web-research/render-session/finish` → 用户确认登录完成后，服务端读取隔离 profile 的 storage state 加密落库；
  - `GET /api/web-research/render-session` → 只回 `{configured, displayHint, expiresAt}`（掩码提示，无明文）；
  - `DELETE /api/web-research/render-session` → 删除并清空服务端会话。
  - 全部按 `actor.id()` 过滤，跨用户 404；未登录 401。
- 渲染时若 `useJs=true` 且存在有效会话，加载该用户 storage state；过期会话按 `SESSION_EXPIRED` 返回，不静默降级为匿名。
- 前端：`WebResearchView.vue` 在"读取正文"旁加"JS 渲染重试"与"会话状态/清除"入口（`webResearch.ts` 增 4 个函数，仍用 `unwrap`）；来源纪要展示 `renderMode/renderNote`。

### d. T33 门禁
- 单测：`WebRenderServiceTest` + 渲染器契约测试全绿；后端全量单测不回退（774 基线）。
- 安全：URL 阻断 400；未登录渲染/会话 401；跨用户会话 GET/DELETE 404；明文凭据不出现在任何响应/日志（grep 断言）。
- 浏览器实测（mock，`frontend/test/web-render.browser.mjs`）：JS 重试按钮态、会话状态掩码、清除后态、桌面 + 390px + reduced-motion，0 pageError。
- 截图入 `test-artifacts/web-research/`，注明"API mock，非真实外网证据"。

---

## T34 · 官方公开连接器 + 凭证管理（三形态独立启用）

**依赖裁决**：D3 **用户已裁决**——三形态全部启用、**每个功能分开、互不混用**。开工无需再等 D3。
默认：全部 `enabled=false`，显式开启才生效。

### a. 连接器抽象与既有迁移（后端）
- 新增 `backend/src/main/java/com/smartops/knowledge/connector/ResearchConnector.java`：
  `String id()`（形态标识，如 `BAIDU_PUBLIC`）、`String scope()`、`boolean isEnabled()`、
  `List<WebResearchService.SearchResult> search(SessionUser actor, String query, int limit)`、
  `WebResearchService.WebPage fetch(SessionUser actor, String url)`；出网一律经 `KnowledgeCrawlService.fetch` 或官方 API 适配，**不得自建裸 HTTP 客户端**。
- `WebResearchService.search()` 改为遍历已启用连接器聚合，`errors/status` 语义不变（全失败 FAILED、部分 PARTIAL）；
  每条 `SearchResult.kind` 填**形态标识**（不再笼统 `WEB`），前端原样展示来源形态。
- 迁移既有：`GithubConnector`（原 GitHub 分支，行为不变，id=`GITHUB`）、`DuckDuckGoConnector`（原 WEB 分支，id=`DDG`）。

### b. 六个独立形态实现（后端，每个独立类 / 独立开关 / 独立测试）
按类目 × 站点铺开，**共 6 个独立连接器实例，禁止合并成一个 if-else 大类**：

| 形态 | 独立类 | 出网 | 受限/失败错误码 |
| --- | --- | --- | --- |
| A 公开页面只读检索 | `BaiduPublicSearchConnector` / `ZhihuPublicSearchConnector` | 站点公开搜索/列表页 + 安全链 + 可选 `WebRenderService.render(useJs=true)` | `BAIDU_CHALLENGE_REQUIRED` / `ZHIHU_CHALLENGE_REQUIRED`（登录墙/验证码）、`*_PUBLIC_FAILED` |
| B 官方 API + 凭证 | `BaiduOfficialConnector` / `ZhihuOfficialConnector` | 官方开放平台公开 API，仅在凭证+授权齐备时启用 | `*_OFFICIAL_NOT_CONFIGURED`、`*_OFFICIAL_UNAUTHORIZED` |
| C 指定 URL 读取扩展 | `BaiduUrlConnector` / `ZhihuUrlConnector` | 用户自带公开链接走 `fetch` + T33 渲染 | `*_URL_UNREADABLE` |

- A 类实现要点：解析公开搜索结果页/列表页的条目（复用 `WebResearchService.parseWebResults` 思路），
  正文读取复用安全链；**遇登录墙/验证码/风控页面必须识别并返回 `CHALLENGE_REQUIRED`**，如实标注，绝不破解、代填、伪装指纹或自动点击绕过。
- B 类实现要点：官方 API 的 endpoint/参数写在各自类内，凭证经 `AesGcmCryptoService.decrypt()` 注入；
  无凭证或 `configured=false` 时该类 `isEnabled()` 直接 false，检索跳过，不回退到 A 形态。
- C 类实现要点：仅识别百度/知乎公开链接域名，复用 `WebRenderService.render`；不新增通用爬虫，不访问用户未提供的 URL。
- 前端：`WebResearchView.vue` 的"来源范围"下拉按启用情况动态加入形态项（如"百度·公开页""知乎·官方API（需凭证）"），
  只列 `configured/enabled` 的形态；`webResearch.ts` 复用 `searchWebResearch(payload)` 传 scope=形态标识，无需新增接口。

### c. 凭证加密与配置（后端）
- `application.yml` 按形态分节，统一 `smartops.web-research.connectors.<小写标识>.enabled`（全部默认 false）：
  ```
  smartops.web-research.connectors:
    github:        { enabled: ${SMARTOPS_WR_GITHUB_ENABLED:false} }
    ddg:           { enabled: ${SMARTOPS_WR_DDG_ENABLED:false} }
    baidu-public:  { enabled: ${SMARTOPS_WR_BAIDU_PUBLIC_ENABLED:false} }
    zhihu-public:  { enabled: ${SMARTOPS_WR_ZHIHU_PUBLIC_ENABLED:false} }
    baidu-official:{ enabled: ${SMARTOPS_WR_BAIDU_OFFICIAL_ENABLED:false}, api-key: ${SMARTOPS_WR_BAIDU_API_KEY:} }
    zhihu-official:{ enabled: ${SMARTOPS_WR_ZHIHU_OFFICIAL_ENABLED:false}, api-key: ${SMARTOPS_WR_ZHIHU_API_KEY:} }
    baidu-url:     { enabled: ${SMARTOPS_WR_BAIDU_URL_ENABLED:false} }
    zhihu-url:     { enabled: ${SMARTOPS_WR_ZHIHU_URL_ENABLED:false} }
  ```
  （键名拼写以实现为准；六个形态各有独立开关，不共用 enabled。）
- 形态 B 凭证用 `AesGcmCryptoService` 加解密；**API 响应只回 `configured` 布尔与掩码尾号**，禁回明文；凭证按 `user_id` 隔离。
- `SecurityAssertions.java`：`SMARTOPS_API_KEY_ENCRYPTION_KEY` 缺失沿用既有启动失败；形态 B 显式开启但缺凭证/未授权时
  按 DESIGN 3.3 的 fail-closed（默认检索跳过并 `configured=false`，不阻断其他形态启动）实现，并加对应单测。

### d. T34 门禁
- 单测（每形态独立测试类，不混断言）：连接器聚合（全成功/部分/全失败）、GitHub 迁移行为等价（对比旧 `parseGithubResults`）、
  六形态各自 `kind` 正确、A 类 `CHALLENGE_REQUIRED` 识别、B 类凭证加解密往返与未配置跳过、C 类域名白名单、
  配置关闭时不触网、形态间不 fallback（A 失败不切 B、B 无凭证不切 A）。
- 安全：明文 key 不出现在接口/日志（grep）；生产缺加密 key 启动失败；跨用户凭证不可读；无验证码/指纹绕过代码（代码审阅）。
- 浏览器实测（mock，`frontend/test/web-research-connectors.browser.mjs`）：下拉只列已启用形态、结果 `kind` 展示、桌面 + 390px + reduced-motion，0 pageError。
- 复跑 `web-research-visual-check.mjs` 确认无回归。

---

## T35 · 增量索引 + 保留策略 + 调度竞争 + 可观测

**裁决已定（D4/D5）**：D4=20 版/URL、清理默认关、可配置；D5=DB 条件更新 claim、不引 Redis 锁。均已确认，按此执行。

### a. 索引与保留（迁移 + 后端）
- 视实际慢查询补索引，候选：`CREATE INDEX idx_wr_page_user_url_time ON web_research_page(user_id,url,fetched_at DESC)`、
  `idx_crawl_page_source_url_time ON knowledge_crawl_page(source_id,url,fetched_at DESC)`；先 EXPLAIN 验证"同 URL 上一版"命中索引再定稿。
- `WebResearchEvidenceService.diffCrawlPage()` 的"上一版"查询改用带索引列，语义（相邻、`id<当前`）不变。
- 保留策略：配置 `smartops.web-research.retention.max-versions`（默认 20）、`retention.enabled`（默认 false）；
  新增 `WebResearchRetentionService.prune(actor/全局)`：按 `(user_id,url)` 分组保留最近 N 版，只删旧 `web_research_page`/`knowledge_crawl_page` 行，
  不动候选/正式条目；记录删除条数与窗口（可审计）。清理任务默认关，显式开启才由调度触发。

### b. 调度竞争 claim（后端）
- `runDueMonitor()` 领取来源改为条件更新 claim：例如 `UPDATE knowledge_crawl_source SET next_run_at=?, claim_token=? WHERE id=? AND monitor_enabled=TRUE AND (next_run_at IS NULL OR next_run_at<=?) AND (claim_token IS NULL OR claim_expiry<=NOW())`，
  受影响行数=1 才执行；多副本同时扫描同一来源仅一个成功，其余跳过并计入指标。
- claim 租约超时（如处理中断）按 `UNCERTAIN` 语义：记 `last_status`/`last_error`，不自动重试、不伪造成功；`next_run_at` 仍按 `monitor_interval_minutes` 推进。
- 配置 `smartops.knowledge.radar.claim-lease-ms`（默认略大于单轮 60s 预算），在 `application.yml` 与 T33 渲染超时一并显式声明 radar 两键。

### c. 可观测（后端，Micrometer）
- 新增 `WebResearchMetrics`（`MeterRegistry` 注入）：`radar.due`（Counter）、`radar.processed`、`radar.skipped`、
  `render.duration`（Timer）、`snapshot.written`（Counter）、`retention.deleted`（Counter）。**全部绑真实事件，无事件为零**。
- 指标名/标签在 `application.yml` 的 `management.metrics.tags.application` 体系下，prometheus 已暴露，无需新增依赖。
- 长期压力观测说明落 `docs/development/联网研究-长期观测执行说明.md`：采样窗口、并发来源数、p50/p95、失败率、内存；报告标注"本环境样本，不宣称泛化"。

### d. T35 门禁
- 单测：索引命中（EXPLAIN 断言或查询契约）、保留边界（N 版内不删/超限删旧/候选不受影响）、claim 竞争（并发两线程仅一成功）、指标随真实事件增减。
- H2 集成测试 + 真实 MySQL `Schema is up to date`（若有新迁移）；`V20261115*` 保持有效。
- 无错误码伪造、无假繁忙（指标零事件断言）；llint/build/全量单测不回退。

---

## T36 · 收口门禁与材料同步（不新增功能）

- 全量回归：后端 774+ 全绿、前端 typecheck/lint（仅既有 1 warning）/双 build、Playwright 桌面+390px+reduced-motion 0 pageError。
- 安全矩阵复跑：401/403/404、跨用户隔离、明文不泄漏、归属 UNKNOWN、无真实性评分、无模型写入路径。
- 真实 MySQL 启动确认；运行副本按 `scripts/windows/restart-local-backend.ps1` 安全重启，readiness `UP`。
- 竞赛材料：**不改**省赛已封版件；仅更新 `docs/web-research-radar.md` 增补"阶段四"小节（用户裁决入册时再做）。
- 提交：按包分笔，建议顺序 T33→T34→T35→T36，消息前缀 `feat(web-research)/perf(web-research)/docs(web-research)`。

## 全局 DoD 快查

- [x] D1–D6 已由用户明示确认（2026-11-16），全部采纳默认建议，方案定稿
- [ ] 出站唯一：浏览器/连接器均过 `OutboundUrlPolicy`，无裸 HTTP、无 DNS 绕过
- [ ] 登录会话加密落库、跨用户 404、有清除入口；明文凭据零出现
- [ ] 归属恒 UNKNOWN、无真实性评分、无模型/权重/提示词/RAG 自动写入
- [ ] 静态 HTML 与 JS 渲染两路独立可用，渲染不可用不伪造正文
- [ ] 三形态六连接器全部启用但各自独立：独立类/开关/凭证/错误码/测试，`kind` 标注形态来源；默认全关显式开启；A 类遇登录墙如实受限、B 类无凭证 `configured=false`、C 类只读用户自带链接；无验证码/指纹绕过代码
- [ ] 快照保留可配、默认保守；claim 竞争多副本单处理；指标绑真实事件
- [ ] 后端 774 基线不回退、前端 lint 0 error（仅 1 既有 warning）、双 build、浏览器 0 pageError
- [ ] 省赛材料口径零改动；所有截图标注 mock、非真实外网证据
