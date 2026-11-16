# 联网检索与时效雷达

## 1. 已落地范围

左侧「联网研究」菜单新增两个页面：

- `/web-research`：公开网页检索、GitHub 公开仓库检索、指定 URL 正文读取、来源纪要、本地 Ollama 状态和任务账本。
- `/radar`：登记公开来源、选择个人知识库、手动立即检查、自动检测开关、检测周期和变更快照。

检索页使用 DuckDuckGo 公开 HTML 入口和 GitHub 官方公开仓库搜索 API。指定 URL 读取复用项目现有的 `KnowledgeCrawlService` 安全出站链路，不另建无防护的 Python 爬虫。

搜索和 URL 读取只返回证据，不自动写入正式知识库；雷达中明确登记的来源发生新增或内容变化时，也只生成服务端任务快照与待审候选，未变化页面不重复生成候选。所有网页内容都必须经人工采纳后才创建正式知识条目，雷达不会自动新建或覆盖正式知识。

网页证据已接入现有 `/knowledge/review` 人工审核闭环：

1. URL 读取成功后，服务端保存与该任务绑定的正文快照，返回真实 `taskId`。
2. 用户点击「提交人工审核」后，后端从服务端快照生成 `PENDING_REVIEW` 候选；前端不能自行提交另一份 URL、正文或哈希替代该快照。
3. 同一网页任务重复提交返回同一候选，不重复堆叠知识。
4. 候选显示网页任务、原始 URL、抓取时间和正文 SHA-256；人工采纳后才创建个人知识条目，来源为 `WEB_RESEARCH + 原始 URL`。
5. 运维运行候选继续通过 `OPERATION_RUN + Trace ID` 关联，不伪造运行记录。
6. 雷达新增/变更页面复用同一 `web_research_task`、`web_research_page` 与候选服务；任务类型为 `RADAR`，只到待审候选为止。


## 2. 后端接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/web-research/search` | 网页 / GitHub / 两者检索，范围为 `WEB`、`GITHUB`、`ALL` |
| `POST` | `/api/web-research/fetch` | 读取公开 URL 的标题、正文、抓取时间和 SHA-256 |
| `GET` | `/api/web-research/runtime` | 获取本地模型运行时状态 |
| `GET` | `/api/web-research/tasks` | 获取当前用户的检索任务账本 |
| `POST` | `/api/knowledge/candidates/from-web-research/{taskId}` | 从当前用户的服务端网页快照生成或返回同一待审候选 |
| `GET/POST` | `/api/knowledge/crawl/sources` | 查询或登记检测来源 |
| `POST` | `/api/knowledge/crawl/sources/{id}/run` | 手动立即检查 |
| `PATCH` | `/api/knowledge/crawl/sources/{id}/monitor` | 开关自动检测并设置周期 |
| `POST` | `/api/web-research/evidence/compare` | 对当前用户的 2–4 个服务端任务快照做跨来源证据对比 |
| `GET` | `/api/knowledge/crawl/pages/{pageId}/diff` | 对比当前快照与同来源、同 URL 的相邻上一版 |
| `GET` | `/api/knowledge/crawl/sources/{id}/pages` | 查询新增、更新、未变化和失败快照 |

证据对比只从 `web_research_page` 读取当前用户的服务端快照，其他用户快照返回 404，不接受前端提交另一份正文或哈希。每个来源展示 HTTPS、正文哈希匹配、抓取时间、正文长度等可核验事实；发布时间、作者/机构/域名归属没有证据时标为 `UNKNOWN`，不自动认定“官方可信”。文本对比采用小写与字母数字归一化、8 字符 shingle 和 Jaccard 重合度，保留四位小数；`HIGH >= 0.75`、`PARTIAL >= 0.25`、其余为 `LOW`，并标明是否不同域名。文本重合只是人工核验线索，不证明事实一致、来源独立或内容真实，不输出真实性评分。

雷达差异展示标题、正文前 600 字符预览和正文 SHA-256 的前后值。正文行差异使用有界 LCS，最多计算双方各前 400 行，截断时明确标记；首个快照返回 `hasPrevious=false`。完整版本仍以快照和哈希为准，不自动判断哪个版本正确。第三阶段复用既有数据表，不需要新增迁移。

前端每次成功读取 URL 后将真实任务快照加入“证据篮”，按任务去重并最多保留 4 个；新检索清空旧证据篮。对比面板展示来源信号与两两文本重合度，固定提示“只做证据对比，不输出真伪评分；重合度高也可能是相互转载”。雷达每条快照提供“对比上一版”，可展开字段前后值与带行号的新增、删除正文行。

自动雷达每 30 秒扫描一次到期来源，应用启动后初始延迟 60 秒，每轮最多处理一个来源。单来源检测周期限制为 15–10080 分钟；既有采集上限仍为最多 50 页、深度 0–2、单轮 60 秒预算。

对应调度配置：

```properties
smartops.knowledge.radar.sweep-ms=30000
smartops.knowledge.radar.initial-delay-ms=60000
```

## 3. 数据迁移

`V20261115__web_research_radar.sql` 增加：

- `knowledge_crawl_source.monitor_enabled`
- `knowledge_crawl_source.monitor_interval_minutes`
- `knowledge_crawl_source.next_run_at`
- `web_research_task` 任务账本及用户时间索引

`V20261115.1__web_research_candidates.sql` 增加：

- `web_research_page`：任务级正文快照，包含用户、URL、标题、摘要、正文、哈希和抓取时间。
- `knowledge_candidate.source_task_id`、`source_url`、`source_content_hash`、`source_fetched_at`。
- 运维候选的 `source_run_id` 改为可空并保留原运行记录外键；网页候选将该字段留空，使用独立网页任务唯一约束，既有运维候选仍保留原 `source_run_id` 值与 Trace。

后端重启时由 Flyway 自动执行。已经运行的旧后端进程不会自动加载新类，需要按项目原方式重启。

## 4. 安全与真实性边界

- 仅支持公开 HTTP/HTTPS 页面、官方公开 API 或用户已授权的数据源。
- 不绕过登录、验证码、付费墙、反爬或网站访问控制，不包含逆向、渗透和无限爬虫。
- 沿用现有逐跳公网校验、DNS 校验、重定向限制、同域采集和页数限制。
- 网页正文按不可信资料处理，不进入 Agent 指令链；保存前沿用脱敏处理。
- 网页快照、候选与正式条目保存的 URL 去除 query/fragment，避免把链接中的 token 写入知识来源。
- 候选正文使用动态长度代码围栏保存网页快照；审核渲染器只接受同级或更长围栏作为结束标记，并继续转义 HTML，避免网页自带反引号破坏结构。
- 「读取正文」「提交候选」「采纳为知识」是三个独立动作；雷达自动检测也只会生成待审候选。知识积累不自动修改模型、权重或提示词。

- 任务账本保存状态和脱敏错误码，不以伪造结果填充失败响应。
- 搜索结果的发布时间缺失时显示「时间未提供」，检索时间与内容更新时间分开呈现。
- 本地模型状态只说明 Ollama 是否可用，不表示模型已经生成回答。本页检索与 URL 读取不消耗在线模型 token；外部搜索服务仍可能限流。

## 5. 神经网状前端

`RelationGraph.vue` 使用确定性 SVG 椭圆布局：

- 中心节点表示查询或雷达，外围节点表示真实来源和本地模型。
- 连线表示检索或监测关系，扫描状态显示脉冲，变更节点使用警示色。
- 点击节点联动来源详情；没有数据时不生成演示节点。
- 支持系统 `prefers-reduced-motion` 和项目减少动态效果模式。

视觉方向依据用户明确提出的「神经网状结构」和「H.D.D. 关系网状动态图」描述实现。三篇小红书笔记因浏览器控制连接超时未能读取，本文不声称复刻其具体画面、角色配色或动画参数。

## 6. 启动与验收

在项目根目录执行：

```powershell
# 后端；已有旧进程时先按项目原方式重启
mvn -f backend/pom.xml spring-boot:run

# 前端
npm --prefix frontend run dev
```

也可以使用项目已有的 `scripts/windows/start-all.ps1`。仅更新后端时，先执行 `mvn -f backend/pom.xml -DskipTests package`，再运行 `scripts/windows/restart-local-backend.ps1`；该脚本会校验 8080 进程归属并保留运行日志。

定向测试：

```powershell
mvn -f backend/pom.xml "-Dtest=KnowledgeCrawlServiceTest,WebResearchServiceTest,KnowledgeCandidateServiceTest,KnowledgeCandidateControllerTest,WebResearchEvidenceServiceTest,WebResearchEvidenceControllerTest,SmartOpsApplicationIntegrationTest" test
node --test frontend/src/components/research/relationGraph.test.js frontend/test/knowledge-review-graph.test.mjs frontend/test/knowledge-candidate-review.test.mjs frontend/test/web-research-evidence.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build

# 需先启动 5173 前端；脚本使用 API mock 检查页面状态，不访问真实外网
node frontend/test/web-research-visual-check.mjs
```

本次第二、三阶段验证结果：

- 后端定向测试与 Spring 集成测试合计 31 项通过；其中第三阶段证据服务 6 项、控制器 2 项，覆盖文本重合、哈希完整性、未知归属、跨用户快照隔离、字段/行差异、首个快照和差异接口越权。
- 前端关系图、审核回挂、网页溯源、动态代码围栏、证据篮和对比/差异界面测试合计 30 项通过。
- 前端生产构建通过；Lint 为 0 error，仅保留项目原有的 `FieldPlane.vue` 未使用变量警告；Vite 只有既有大 chunk 提示。
- Playwright 覆盖桌面检索、正文证据、提交人工候选、审核页网页溯源、双来源证据对比、雷达相邻版本行差异、390px 手机布局和减少动态效果模式，全部通过。第三阶段截图为 `evidence-comparison-desktop.png`、`evidence-overlap-desktop.png`、`evidence-comparison-mobile.png`、`radar-diff-desktop.png`，均位于 `test-artifacts/web-research/`。
- 最新后端已打包并通过项目脚本安全重启，运行副本为 `.runtime/backend/smartops-backend-20261116-011219-560.jar`，readiness 为 `UP`。
- 第三阶段不需要新增迁移；真实 MySQL 启动日志确认 `Schema smartops is up to date. No migration necessary.`。既有 `V20261115.1` 的运维外键、网页任务唯一约束与正文快照表保持有效。
- 新进程未登录访问雷达差异 GET 返回 401，证据对比 POST 返回 403；未新增认证绕过。旧有候选列表和检索任务 401、候选 POST 403 的行为保持不变。

浏览器验收脚本使用 mock 数据，只证明前端交互和布局，不证明外部网站始终可访问，也不把 mock 当作真实数据库记录或真实外网证据。真实公开搜索仍受网络、来源限流和页面结构变化影响。本轮未使用真实用户会话执行「外网读取 → 候选 → 采纳」或真实跨来源对比，避免在未指定测试网页与目标知识库的情况下污染真实数据；正确性由后端定向测试、H2 集成测试、前端 mock 验收和新进程安全/就绪检查支撑。

## 7. 下一阶段

当前版本不包含以下能力：

1. Browser MCP / Playwright 的 JavaScript 渲染与人工登录接续。
2. 百度、知乎等专用公开连接器，以及官方 API 凭证管理。
3. 跨来源自动事实裁决、来源独立性证明和自动可信度评分；当前仅提供可核验信号、文本重合线索和相邻版本差异。
4. 增量索引优化、长期多来源压力测试和调度竞争观测。
5. 模型在线自训练或权重自更新。

建议下一阶段优先做「JS 渲染只读工具 + 官方公开连接器 + 增量索引长期观测」，继续保留人工事实裁决，不要把未经审核的网页内容直接用于自动修改模型。
