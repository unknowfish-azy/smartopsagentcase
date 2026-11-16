# 联网研究 阶段四 设计口径 v1.0

> 状态：**方案已定稿（D1–D6 用户已确认采纳默认建议）**。本文只定义"做什么、边界在哪、为什么这样做"。
> 动手步骤见同目录 `EXECUTION-PACK.md`。交实现模型照做，本方案不含编码/构建/测试执行。
> 前置阅读：`docs/web-research-radar.md`（阶段一至三交付说明）、`docs/development/整改执行清单与计划-20261105.md`（安全基线）。
> 工作包编号 T33–T36，承接工坊 T28–T31、纠察星云 T32，独占编号不冲突。

## 1. 目标与范围

阶段一至三已经把"联网检索 → 时效雷达 → 跨来源证据对比/版本差异"落地，并且守住了
"只产出可核验信号、不判真伪、不自动改写知识库与模型"的边界。阶段四沿用同一条安全链和人工审核闭环，
补上文档 `web-research-radar.md` 第 7 节列出的三项优先能力：

1. **JS 渲染只读工具**（T33）：让当前纯静态 HTML 抓取链路能处理需要 JavaScript 才能出正文的公开页面，
   并支持"用户主动登录接续"读取其**已授权**页面。核心是受控、隔离、只读，绝不绕过访问控制。
2. **官方公开连接器 + 凭证管理**（T34，用户裁决 D3：百度/知乎**全部启用**，且三种形态**各自独立、互不混用**）：
   在现有 DuckDuckGo HTML / GitHub 官方 API 之外，用统一的连接器抽象接入百度/知乎的三种合规形态——
   公开页面只读检索、官方 API + 凭证、指定 URL 读取扩展。三者拆为独立功能单元（独立类 / 独立开关 /
   独立凭证 / 独立错误码 / 独立测试），结果标注形态来源，不合并成一个"百度知乎大连接器"，
   不共享会话、凭证或正文缓存，任一形态受限不影响其他形态。
3. **增量索引 + 长期观测 + 调度竞争**（T35）：给雷达与检索快照加增量索引与保留策略，
   把"长期多来源压力行为"和"调度竞争"变成可观测、可核验的运行时指标，不改数据正确性语义。

T36 为门禁收口与材料同步（不新增功能）。

### 明确不做（红线，写入每个执行包首行）

- **不做自动事实裁决、来源独立性证明、自动可信度评分**：重合度/信号只作人工核验线索；归属未核实恒为 `UNKNOWN`；
  不输出任何"真实性分数/判定"。文档第 7 节第 3 项维持为"不做"。
- **不做模型在线自训练或权重自更新**：网页内容永不进入模型权重、提示词、微调或 RAG 索引的自动写入路径；
  知识积累只到"人工采纳的个人知识条目"为止。
- **不绕过登录、验证码、付费墙、反爬与访问控制**：JS 渲染的登录接续只能是"用户本人主动、显式、可见"的会话接力，
  工具不得自动破解、不得代填凭据、不得共享他人会话。
- **不改省赛提交材料口径**：本阶段为省赛（11-18 截止）之后的增强，不纳入已封版的技术文档 PDF、介绍稿、
  答辩合订本与 demo-script；如需入册由用户在国赛期单独裁决。
- **禁写"准确率 9X%"**：数据集仍全 DRAFT；任何指标一律标注样本量与采集窗口，不宣称泛化精度。
- 不引入 three.js、位图 sprite、霓虹粉、金额字样到前端可视化；沿用令牌取色与 reduced-motion 纪律。

## 2. 已核实锚点（勿重复勘察）

| 关注点 | 位置 | 现状要点 |
| --- | --- | --- |
| 检索/抓取服务 | `backend/.../knowledge/WebResearchService.java` | `search()` 走 DuckDuckGo HTML + GitHub 官方 API；`fetch()` 走爬虫安全链；`createTask/finishTask` 用 `GeneratedKeyHolder` |
| 安全出站链 | `backend/.../knowledge/KnowledgeCrawlService.java` | `fetch(url, accept)` 逐跳 `OutboundUrlPolicy.inspect` + `PinnedDns.pin` + 4 跳重定向上限 + 10MB 下载上限 + 60s 轮预算 + `Semaphore(4)` 并发闸；`htmlToText/pageTitle/sha256/normalizeUrl/stripQuery/errorCode` 均为 static 可复用 |
| DNS 防重绑 | `backend/.../security/PinnedDns.java`、`OutboundUrlPolicy.java` | HC5 `DnsResolver` 只返回已 pin 地址，fail-closed |
| 证据服务 | `backend/.../knowledge/WebResearchEvidenceService.java` | 8 字符 shingle + Jaccard（4 位小数，HIGH≥0.75/PARTIAL≥0.25）；有界 LCS（400 行）；跨用户 `user_id` 过滤后返回 404；`UNKNOWN` 归属 |
| 雷达调度 | `KnowledgeCrawlService.runDueMonitor()` | `@Scheduled`，`sweep-ms=30000`/`initial-delay-ms=60000`，`SELECT ... LIMIT 1` 每轮一个到期来源；`next_run_at` 推进 |
| 数据表 | `V20261115__web_research_radar.sql`、`V20261115.1__web_research_candidates.sql` | `web_research_task`、`web_research_page`、`knowledge_crawl_source(monitor_enabled/interval/next_run_at)`、`knowledge_crawl_page`；候选 `uq_knowledge_candidate_web_task` 唯一约束 |
| 凭证加密 | `backend/.../common/crypto/AesGcmCryptoService.java` | AES-256-GCM，`SMARTOPS_API_KEY_ENCRYPTION_KEY`（Base64 32 字节）；`encrypt/decrypt` 可直接复用；生产由 `SecurityAssertions` 断言非空 |
| 生产断言 | `backend/.../security/SecurityAssertions.java`、`SecurityAssertionConfig.java` | 生产拒绝空口令/空 key；新连接器若要求凭证，需纳入断言清单 |
| 配置中枢 | `backend/src/main/resources/application.yml` | `smartops.*` 分区；radar 两项调度键已在 `KnowledgeCrawlService` 用默认值内联，尚未在 yml 显式声明 |
| 前端页面 | `frontend/src/views/research/WebResearchView.vue`、`RadarView.vue` | Vue3 `<script setup>`；神经/关系网状图 `RelationGraph.vue` + `relationGraph.js`；证据篮 `evidenceSelection.js` |
| 前端 API | `frontend/src/api/webResearch.ts` | 8 个函数，统一 `unwrap = v => v?.data ?? v`；超时按接口分档 |
| 浏览器自动化 | `frontend/package.json` 含 `playwright ^1.63.0`；`frontend/test/*.browser.mjs` 约 70 个脚本 | Playwright 已作为**前端验收**依赖存在；mock 路由须锚定根 `/api/`，勿用 `**/api/**`（会误匹配 `/src/api/*.ts` 白屏，已踩坑） |
| 审核闭环 | `KnowledgeCandidateService.createFromWebResearch` / `/knowledge/review` | 网页快照→`PENDING_REVIEW` 候选→人工采纳；唯一约束防重复堆叠；采纳来源 `WEB_RESEARCH + URL` |

## 3. 架构与数据流

### 3.1 总体原则

```
公开网页 / GitHub / 连接器 API
        │  （唯一出站口：KnowledgeCrawlService.fetch 安全链 / 连接器适配器）
        ▼
  正文提取 + 脱敏 + SHA-256
        ▼
  web_research_page（服务端快照，按 user_id 隔离）
        ├──▶ 证据篮 ──▶ 跨来源证据对比（确定性文本重合，不判真伪）
        ├──▶ 雷达快照 ──▶ 有界 LCS 版本差异
        └──▶ PENDING_REVIEW 候选 ──▶ 人工审核 ──▶ 个人知识条目
                                          │
                                          └──（仅此路径）不触碰模型/权重/提示词/RAG
```

阶段四新增的三块都挂在这条链的**读侧或出入口侧**，不改动"候选→人工采纳"的下游语义：
- T33 替换/补强最左端"正文提取"这一环（静态 HTML → 可选 JS 渲染）。
- T34 扩展"连接器 API"这一环，并新增凭证保管。
- T35 给中间"快照表 + 调度"加索引、保留策略与可观测性。

### 3.2 T33 JS 渲染只读工具

**为什么需要**：`WebResearchService.fetch()` 目前依赖 `KnowledgeCrawlService.fetch()` 拿静态 HTML，
再 `htmlToText()` 提取。SPA / 客户端渲染页面（含部分文档站、社交平台）在静态 HTML 里没有正文，
只能拿到空壳。阶段二因浏览器控制连接超时未读取的三篇笔记，属于"用户主动提供的已授权内容"，
阶段四用受控浏览器补齐这一类读取，但**不宣称复刻其画面或参数**。

**安全设计（不可降级）**：
- 绝不让浏览器直连任意地址。渲染请求必须先过 `OutboundUrlPolicy.inspect()`，只接受公网 HTTP/HTTPS；
  与 Java 站内链共用同一策略，不新造白名单。
- 无头浏览器的网络出口必须受控：优先在**独立沙箱进程/独立浏览器 profile** 中运行，禁用本地文件访问、
  禁用自动下载、禁用扩展；导航只到已校验 URL，重定向逐跳重新校验（沿用 4 跳上限）。
- **只读**：渲染后只提取 DOM 正文与标题，不执行页面内的表单提交、不做自动点击、不读取浏览器已有 Cookie
  之外的凭据。页面内 JS 自由执行是浏览器固有行为，故必须假设其不可信——提取文本继续走 `OperationRedactor.redact`，
  且**不进入任何指令通道**。
- **登录接续**：仅当用户显式触发并自己完成登录时才保存会话；会话与 `user_id` 绑定、加密落库、
  有过期时间；跨用户使用直接 404；提供"清除会话"入口。工具不代填账号密码、不保存明文凭据、不在多用户间共享 profile。
- 保留现有大小/时间预算：单页正文 `MAX_CONTENT` 20,000、下载上限 10MB、轮预算 60s；渲染超时单独设 bounded 值并在配置暴露。

**产出契约（不改现有字段语义）**：渲染成功返回与 `WebPage` 同形的记录（title/excerpt/content/contentHash/fetchedAt），
额外加一个 `renderMode: STATIC | JS` 与 `renderNote`（说明用了渲染、是否有登录接续），前端来源纪要处如实展示。
渲染失败落 `WEB_RESEARCH_RENDER_FAILED` 错误码，不伪造正文。

### 3.3 T34 官方公开连接器 + 凭证管理（三形态独立启用）

**为什么需要**：现在 `WEB` 范围写死 DuckDuckGo HTML、`GITHUB` 写死官方 API。文档第 7 节要求
"专用公开连接器 + 官方 API 凭证管理"。用户裁决 D3：百度/知乎的三种合规形态**全部启用，但每个功能分开、互不混用**。

**形态清单（三个独立功能，不可合并）**：

| 形态 | 标识 | 出网方式 | 凭证 | 受限时行为 |
| --- | --- | --- | --- | --- |
| A 公开页面只读检索 | `BAIDU_PUBLIC` / `ZHIHU_PUBLIC` | 站点公开搜索/列表页 + 现有安全出站链 + T33 JS 只读渲染取正文 | 无 | 遇登录墙/验证码返回 `CHALLENGE_REQUIRED`，如实标注，不破解不代填 |
| B 官方 API + 凭证 | `BAIDU_OFFICIAL` / `ZHIHU_OFFICIAL` | 官方开放平台公开 API（仅在凭证与授权齐备时启用） | `AesGcmCryptoService` 加密 | 无凭证/未授权则 `configured=false`，启动断言或检索时跳过，不裸奔 |
| C 指定 URL 读取扩展 | `BAIDU_URL` / `ZHIHU_URL` | 用户自带公开链接，走现有 `fetch` + T33 渲染 | 无（或复用用户自己登录的 T33 会话） | 非公开/不可读 URL 返回明确错误码 |

**"每个功能分开"的硬约束（实现模型必须遵守）**：
- 六个形态标识（3 类 × 百度/知乎）各自是**独立连接器实例 + 独立配置开关 + 独立错误码 + 独立测试类**；
  禁止写成一个大类里 if-else 切换站点/形态。
- 每个连接器是**配置驱动**（`smartops.web-research.connectors.<标识小写>.*`），**默认全关**，显式开启才生效；
  三类形态互不为默认值、互不 fallback——A 失败不会偷偷切 B，B 无凭证不会偷偷用 A。
- 搜索结果 `SearchResult.kind` 用形态标识（如 `BAIDU_PUBLIC`、`ZHIHU_OFFICIAL`），前端来源纪要原样展示，
  让用户看得见"这条来自哪种形态"，不混在一个 `WEB` 标签下。
- 共享的是**底层能力**（同一 `KnowledgeCrawlService.fetch` 安全链、`OperationRedactor` 脱敏、`ResearchConnector` 接口），
  不共享的是**业务状态**（会话、凭证、正文缓存、开关）。底层复用 ≠ 功能混用。
- 需要凭证的形态 B：`apiKey` 由 `AesGcmCryptoService.encrypt()` 落库、读取时 `decrypt()`；响应只回
  `configured: true/false` 与掩码尾号，不回明文；凭证按 `user_id` 隔离。
- 生产断言：`SMARTOPS_API_KEY_ENCRYPTION_KEY` 缺失仍沿用既有启动失败；形态 B 若被显式开启但缺凭证/未授权，
  按 fail-closed 处理（启动失败或检索跳过，两者选一在 D3 复核时定，默认检索跳过并标记 `configured=false`，不影响其他形态启动）。
- 不做反爬对抗：三形态都只在"公开可达 / 官方授权 / 用户自带链接"范围内工作，不写绕过验证码、代填、伪装指纹的逻辑。

### 3.4 T35 增量索引 + 长期观测 + 调度竞争

**为什么需要**：`web_research_page.content` 是 LONGTEXT，每次抓取存整份正文与快照；
雷达多来源长期运行会持续膨胀。LCS 差异每次现算（双方前 400 行），重来源下开销可观测。
`runDueMonitor()` 的 `SELECT ... LIMIT 1` 在多副本部署时可能重复领取同一来源。

**设计**：
- **增量索引**：在 `web_research_page`、`knowledge_crawl_page` 已有 `(user_id, created_at)`、
  `(source_id, user_id, ...)` 索引基础上，按实际查询补组合索引（如 `(user_id, url, fetched_at DESC)` 支撑
  "同 URL 上一版"查询）；`diffCrawlPage` 的"上一版"查询要能被索引命中，避免全表扫。
- **保留策略**：为 `web_research_page` / `knowledge_crawl_page` 增加可配置"每 URL 保留最近 N 版"
  （默认保守，如 20，绝不默认删到只剩 1 版导致差异不可用）；清理只删旧快照，不动候选与正式知识，
  清理动作可审计（记录删除条数与窗口）。
- **调度竞争**：给到期来源领取加一次性 claim（如 `next_run_at` 条件更新 + 单副本持有标记），
  确保多副本同时扫描时同一来源一轮只被一个副本处理；`next_run_at` 仍按 `monitor_interval_minutes` 推进。
  领取失败/租约超时按既有 `UNCERTAIN` 语义处理，不自动重试、不伪造成功。
- **可观测性**：新增轻量指标（Micrometer，已在 `management.metrics` 暴露 prometheus）：
  每轮扫描到期来源数、实际处理数、跳过（被其他副本领取）数、渲染耗时 p95、快照写入数、清理数。
  指标只统计**真实事件**，无事件即零，不做假繁忙；不新增金额/评分类指标。
- **长期压力行为**：提供脚本化的多来源、长周期观测执行说明（采样窗口、样本量、p50/p95、失败率），
  结果以观测报告落盘，明确"仅本环境样本，不宣称泛化"。

## 4. 安全与隐私边界（继承并加强）

- 唯一出站口原则不变：浏览器/连接器都不得绕过 `OutboundUrlPolicy` 与 DNS pin 派生出的公网校验。
- 跨用户隔离：快照、会话、凭证、指标按 `user_id` 过滤；越权一律 404，不区分"不存在"与"无权"。
- 脱敏不变：`OperationRedactor.redact` 覆盖所有入库正文与标题；URL 去 query/fragment。
- 失败诚实：渲染/连接器失败只落自有错误码，不落原始异常（防内部主机/端口/IP 泄漏）。
- 登录会话加密：复用 `AesGcmCryptoService`，明文凭据不落库、不进日志、不进前端。
- 人工审核闭环与"三动作分离"（读取正文 / 提交候选 / 采纳知识）保持不变。

## 5. 验收门禁（沿用项目标准，缺一不可）

1. 后端全量单测不回退（当前基线 774 执行 / 0 失败 / 0 错误 / 1 跳过）；新增项见执行包。
2. 前端 `typecheck` 0 error、`lint` 0 error（仅保留既有 `FieldPlane.vue` 1 个 warning）、双端 `build` 通过。
3. 浏览器实测 0 pageError；mock 路由锚定根 `/api/`；覆盖桌面 + 390px + reduced-motion。
4. 安全越权矩阵：未登录渲染/对比/差异 401/403；跨用户快照/会话/凭证 404。
5. 真实性边界断言：归属 `UNKNOWN`、无真实性评分、无模型/权重/提示词写入路径。
6. Flyway：如需新迁移，H2 集成测试 + 真实 MySQL `Schema is up to date` 双验证；第三阶段的 `V20261115*` 保持有效。
7. 生产启动断言：`SMARTOPS_API_KEY_ENCRYPTION_KEY` 缺失启动失败；形态 B 显式启用但缺凭证/未授权时按 fail-closed
   （检索跳过 + `configured=false`，不阻断其他形态启动），两种情形各有单测。

## 6. 裁决结果 D1–D6（2026-11-16 用户已确认，方案定稿）

- **D1 ✅ 已确认**：JS 渲染纳入阶段四首发，但**默认关闭**、按页显式选择"用 JS 渲染重试"，非默认全量渲染。
- **D2 ✅ 已确认**：登录接续做**只读会话接力的最小版**（显式登录 + 加密会话 + 清除入口），不做自动登录、不代填凭据。
- **D3 ✅ 已确认**：三形态全部启用、每个功能分开（A 公开页面只读检索 / B 官方 API+凭证 / C 指定 URL 读取），
  百度与知乎各一套、共 6 个独立连接器标识；GitHub/DDG 仍迁到同一接口但保持既有行为。默认全关、显式开启。
  形态 B 若官方无可用公开 API 或缺授权 → `configured=false`，不伪造可用。
- **D4 ✅ 已确认**：快照保留 20 版/URL，可配置；清理默认关闭，需显式开启。
- **D5 ✅ 已确认**：调度竞争用 DB 条件更新做单副本 claim，不引入 Redis 锁新依赖。
- **D6 ✅ 已确认**：本阶段**不入省赛**（11-18）已封版材料，作为国赛期增强另行裁决。
