# 知识审核泳道图 · 实现说明（阶段 5：接真数据与缺口收口）

本文件记录四个数据缺口的实际处理方式、可指回的代码位置、验证命令与自检结果。
设计依据：`DESIGN.md`；实施约束：`PROMPT.md`。

## 1. 数据来源（没有演示数据兜底时）

| 图上元素 | 真实来源 | 取数方式 |
| --- | --- | --- |
| 候选行 | `GET /api/knowledge/candidates` | 首屏 `pageSize=100`，**不传 `status`**（后端把 status 当等值条件，传 `ALL` 会得到空结果）；页脚「加载更早」再翻页 |
| 条目泳道 | `GET /api/knowledge/personal/libraries/{id}/entries` | 每个知识库翻页取全（`pageSize=100`，上限 10 页） |
| 知识库名 / 采纳目标 | `GET /api/knowledge/personal/libraries` | 与候选并行加载 |
| 审核事件（演化史） | 候选自身的 `status=PROMOTED/REJECTED` | 采纳时间取条目的 `created_at`，驳回没有事件时间，标签写「候选生成于 …」 |

代码：`frontend/src/views/knowledge/KnowledgeCandidateReviewView.vue:268`（loadCandidates）、`:286`（loadEntries）、`:326`（loadMore）。

## 2. 缺口 A：候选挂到哪条条目泳道

**结论：A1 + `source_ref` 回挂，零后端改动。**

- 连接键：`entry.source_ref === candidate.trace_id`。`KnowledgeCandidateService#promote` 建条目时会把候选的 `traceId` 写进 `source_ref`，所以已采纳候选一定能找回自己的条目。
- 未匹配到的候选（含所有待审候选）固定落在最右一条「待归类」泳道，条目行写「尚未关联知识条目」。
- 条目侧必须翻页到底：只取第一页时，第 101 条之后的条目匹配不到候选，会把**已有条目**的候选误标成「待归类」（这是假状态）。上限 10 页，超出时页脚如实写「条目超过 1000 条，超出部分未参与泳道匹配」。

代码：`frontend/src/views/knowledge/reviewGraph/useReviewGraph.js:138`（entryByTrace）、`:147`（分组）；`KnowledgeCandidateReviewView.vue:280`。

**残留限制（如实说明，不做假象）**：`source_ref` 只在 promote 时写入。手工创建或导入时没带 `sourceRef` 的条目，其历史候选会一直显示「待归类」，直到后端支持按条目反查候选。

**演示模式**：候选与条目为空时注入 8 条演示候选 + 1 条演示条目，条目的 `source_ref` 对齐演示候选 `demo-trace-k8s-service`，所以演示图里也能看到条目泳道与采纳事件；文案统一写「演示 · 已采纳」「演示 · 待审」「未写库」，不冒充真实写入。代码：`frontend/src/components/knowledge/knowledgeCandidateGuide.js:822`（`knowledgeEntryGuides`）、`KnowledgeCandidateReviewView.vue:200`（`graphEntries`）。

## 3. 缺口 B：`promote` 只能新建条目

**结论：不承诺「并入已有条目」，全部文案只描述新建。**

- 侧栏 popover 提示：「将在所选知识库新建条目 v1（未验证）。后端 promote 只能新建，不能并入已有条目。」`KnowledgeCandidateReviewView.vue:104`
- 快捷菜单「并入已有条目」永久置灰，原因写「当前后端只支持新建条目，条目合并需要 target_entry_id」。
- 成功 toast 与行内第二行一律写「新建条目 v1（未验证）」，不写「已更新条目」。

代码：`frontend/src/views/knowledge/reviewGraph/ReviewActionMenu.vue:111`（merge 项）、`ReviewGraphRow.vue`（secondLine）。

## 4. 缺口 C：不显示「生成中」

**结论：不显示，也不并行拉 run 状态。**

理由：候选表只存已落库的候选，生成中的运行没有候选行，图上也就没有它的位置；额外拉 `GET /api/operations/runs?status=RUNNING` 会引入第二个时间源，且无法证明某次运行对应某条候选，等于用推测补状态。

处理：拿到后端契约外的状态时，行与侧栏都写「未知状态」，不把原始枚举直接当标签，更不写成「生成中」。

代码：`ReviewGraphRow.vue:118`（statusLabel）、`KnowledgeCandidateReviewView.vue:258`（侧栏 statusLabel）。
测试：`frontend/test/knowledge-review-realdata.browser.mjs` 注入 `status=GENERATING` 的候选，断言页面出现「未知状态」且全页不含「生成中」。

## 5. 缺口 D：图需要跨页聚合

**结论：首屏 100 条 + 「加载更早」，页脚明写已加载量。**

- 首屏 `pageSize=100`（后端 `KnowledgeCandidateService#list` 把上限钳到 100）。
- 截断时页脚显示「已加载 100 / 200 条候选」+「加载更早」；补齐后提示自动消失，不留静态假文案。
- 演化史只保留最近 40 条事件（`HISTORY_LIMIT`），超出时单独标注。

代码：`KnowledgeCandidateReviewView.vue:172`（PAGE_SIZE）、`:207`（truncated）；`ReviewGraph.vue` 待审区页脚；`useReviewGraph.js:35`（HISTORY_LIMIT）。

## 6. 缺口 E：不画「已入库」主干泳道

**结论：不画。**

后端没有任何把 `personal_knowledge_entry.verification_status` 写成 `VERIFIED` 的路径：创建时固定 `UNVERIFIED`（`PersonalKnowledgeService.java:99`），归档写 `ARCHIVED`（`:129`）。所以图上不出现「已入库 / 已验证」主干，条目行只写 `vN` + 「新建条目 v1（未验证）」。

单测锁死：`frontend/test/knowledge-review-graph.test.mjs` 断言泳道只有 `entry` 与 `unassigned` 两种 `kind`。

## 7. 验证方式

```powershell
cd frontend
npm test                                             # 单测（含行模型 11 条断言）
node test/knowledge-review-actions.browser.mjs       # 409 / 原因必填 / 成功提示 / 新条目回挂
node test/knowledge-review-keyboard.browser.mjs      # 纯键盘采纳 + 驳回、Shift+F10 菜单
node test/knowledge-review-realdata.browser.mjs      # 缺口 A/C/D/E + 四宽度对齐 + 性能基线
node test/knowledge-review-zoom.browser.mjs          # 缩放（按钮 / Ctrl+滚轮）、拖动平移、缩放后泳道对齐
npm run typecheck && npm run lint && npm run build
```

### 真实后端联调（不 mock /api）

```powershell
# 后端 8080、MySQL 3306、前端 5173 已在运行
C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe scripts/e2e/knowledge_review_live_seed.py
cd frontend
node test/knowledge-review-live.browser.mjs
# 跑完清理夹具（候选 / 运行记录 / 条目 / 知识库）
C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe scripts/e2e/knowledge_review_live_seed.py --cleanup
```

夹具账号 `e2e_knowledge`，脚本用真实登录拿到 `JSESSIONID` 写入 `frontend/test-artifacts/live-session.json`（已加入忽略），
条目走真实接口创建（带 `source_ref`），候选因为依赖知识生成链路、不重跑 AI，所以直接按表结构写入并补最小运行记录；
用例覆盖真实计数、`source_ref` 回挂、侧栏事实、UI 采纳/驳回落库，以及「接口侧先采纳 + UI 再确认」时被重新校验拦住、不重复建条目。

性能基线（`knowledge-review-realdata.browser.mjs`，Edge headless，1440×1000，dev server，多次运行区间）：

- 200 行首屏到达（文档开始 → 首行渲染）：417–732ms（含 dev 环境模块加载与 mock 取数）
- 200 行强制重排（切紧凑密度改字号 → 读全部行几何）：**22–39ms**，断言 < 100ms
- 测量方式：`addInitScript` 用 `requestAnimationFrame` 轮询首行出现时间；重排用切密度后 `offsetHeight` + 逐行 `getBoundingClientRect` 强制同步布局

## 8. 自检（PROMPT 提交前清单）

| 项 | 结果 |
| --- | --- |
| 1440 / 1024 / 768 / 375 泳道对齐（含切密度） | `knowledge-review-realdata.browser.mjs`：四个宽度断言无横向溢出、200 行头像中心均压在泳道线上；密度切换有单测 |
| 四状态不看颜色也能读 | `!` / `✓` / `–` 角标 + 标签文字，颜色只作辅助 |
| 采纳含目标知识库选择 | popover 内 `<select>`，空库时禁用并说明原因 |
| 驳回原因必填 | 空值就地报错，不发请求（有 browser 用例） |
| `409` 后刷新真实状态且有提示 | 关弹层 + toast 写 `409 KNOWLEDGE_CANDIDATE_NOT_PENDING` + 重新拉列表 |
| 菜单无「能点但会失败」项 | 7 项中 3 项置灰，均写根本原因 |
| 缺口 A/B/C/D/E 写在实现说明 | 本文件第 2–6 节 |
| `guideMode` 不写库、不计统计 | `isGuide` 行无可写入口，统计标签写「演示数据 · 不计统计」 |
| `↑↓ Enter A R Esc F ?` | 通过（`knowledge-review-keyboard.browser.mjs`） |
| `prefers-reduced-motion` 无循环动画 | 呼吸环在 reduced-motion 与 `data-motion-degraded` 下 `animation:none` |
| 搜不到 `backdrop-filter` / 新增色相 / `viewBox` | 已 grep：`reviewGraph/` 与视图内均无 |
| 200 行首屏布局 < 100ms | 38.6ms（见第 7 节） |
