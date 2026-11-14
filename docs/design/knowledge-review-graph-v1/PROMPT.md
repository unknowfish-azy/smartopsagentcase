# 实现提示词：把知识审核界面改成图谱工作台

把下面整段发给 Trae（或任何能读写本仓库的 agent）。它要求宿主已有 `docs/design/knowledge-review-graph-v1/` 这份设计资料。

---

## 任务

把 `/knowledge/review`（`frontend/src/views/knowledge/KnowledgeCandidateReviewView.vue`）的主交互元素，从「候选列表 + 详情两栏」换成「一张泳道图 + 右侧证据侧栏」，视觉语言照 `index.html` 这份单文件参考原型。

**先设计、后实现**：第一步只输出调研结论、概念映射表和分阶段计划，等我确认后再动代码。

## 第 0 步：先读这些（读完再动手）

| 文件 | 你要从中拿到什么 |
| --- | --- |
| `docs/design/knowledge-review-graph-v1/DESIGN.md` | 概念映射、布局几何、状态编码、交互规则、数据缺口 A/B/C/D、视觉令牌、验收清单 |
| `docs/design/knowledge-review-graph-v1/index.html` | 参考原型（播种数据，双击可看）。可以直接读它的 CSS/JS 拿坐标算法和组件写法 |
| `frontend/src/views/knowledge/KnowledgeCandidateReviewView.vue` | 现状：390px 队列 + 详情、`guideMode`、`renderKnowledgeMarkdown`、`DecodeText` |
| `frontend/src/assets/styles/variables.css` | 全部 `--ds-*` / `--smart-*` 令牌，禁止自己编色值 |
| `design-system/MASTER.md` §Revision 2026-11-12 | 工具层约束：半径 4-8、1px 发丝线、零 `backdrop-filter`、无粒子 |
| `frontend/src/api/operations.ts` | 现有 `getKnowledgeCandidates` / `getKnowledgeCandidate`，以及 `promote` / `reject` 契约 |
| `backend/.../KnowledgeCandidateService.java` | `PENDING_REVIEW / PROMOTED / REJECTED`，`promote` 只新建 entry，`reject` 把原因追加到 summary |
| `frontend/src/components/knowledge/knowledgeCandidateGuide.js` | 演示引导数据与 `guideMode` 语义（不许写库、不许计入统计） |

## 硬约束（违反了就是错）

0. **先看仓库现状**：`KnowledgeCandidateReviewView.vue` 已有一版未提交改造，右侧是 ECharts 力导向图 `components/knowledge/KnowledgeReviewGraph.vue`（画单条候选的证据关系）。**不要删它**——把它从主位挪到侧栏作为「证据关系」。主视图换成泳道图，两者是两层，见 DESIGN §16。另外 `frontend/vite.config.js` 的 `host: true` 与本次无关，先确认是否为有意改动。
1. **不动后端契约**、不动路由、不动导航、不动 `api/operations.ts` 的函数签名。这次只改前端表现层。
2. **不引入新色相族**。泳道色只允许 `--ds-lane-1..4` 这一组（见 DESIGN §11.2），第 5 个来源工具起用中性灰 + 首字母区分。琥珀 `#d29922` 与红 `#f85149` **永远不准进入泳道色**，它们只表达「待审 / 驳回」。
3. **零 `backdrop-filter`、零粒子、零 WebGL、零每帧 JS 重绘**。状态环的呼吸/旋转只用 CSS `transform`/`opacity`，并遵守 `prefers-reduced-motion`。
4. **行高与泳道坐标必须出自同一份数据**。一次算出 `rows[]` 的 `y`，DOM 和 `<svg>` 都读它。**禁止**用 `getBoundingClientRect()` 反推泳道位置。
5. `<svg>` **不要写 `viewBox`**，直接 `width=padLeft height=bandHeight`，让 1 用户单位 = 1 CSS 像素，否则缩放会错位。
6. **不呈现假状态**。缺口 C（生成中）没有数据时，这一行不显示，不要用占位数据凑效果。缺口 B 未落地时，按钮文案必须是「采纳并新建条目」，**不能**写「合并入 v4」。
7. **演示数据（`guideMode`）**：图上标「演示数据」chip，禁用所有写操作，不计入顶栏统计。
8. 菜单里**不允许**出现「能点但会失败」的项。不能做就置灰 + 写原因（DESIGN §7 给了一张对照表）。

## 概念映射（照这个建视图模型）

| 上游 | 本项目 | 来源字段 |
| --- | --- | --- |
| 项目 | 知识库 | `personal_knowledge_library` |
| main | 已入库主干（lane 0） | `personal_knowledge_entry`（VERIFIED） |
| 分支 | 知识条目（一条泳道） | `entry.version` 即提交序 |
| worktree | 来源运行 | `operation_run_record` |
| agent | 知识候选（一行） | `knowledge_candidate` |
| 子行 | 证据/步骤 | `operation_run_evidence`、`operation_run_output` |
| harness | 来源工具 `tool_id` | 同左 |
| 提交 | 审核事件（快照/采纳/驳回） | `status` + `updated_at` |
| 等你 / 完成 / 运行中 / 空闲 | 待审 / 已采纳 / 生成中 / 已驳回 | `PENDING_REVIEW` / `PROMOTED` / run `RUNNING` / `REJECTED` |

## 分阶段实现（每阶段结束等我确认）

### 阶段 1：视图模型 + 只读渲染

- 新建 `frontend/src/views/knowledge/reviewGraph/useReviewGraph.js`：把候选列表聚合成 `{ lanes[], nowRows[], histRows[] }`，其中每行带 `{ id, kind, lane, h, y }`，`y` 由累加得出。
- 新建 `reviewGraph/ReviewGraph.vue`：渲染行 + 泳道层 + 头像层，三种层（`.lanes` / `.nodes` / `.row`）的 `z-index` 分别是 3 / 4 / 2。
- 行高：候选 56、条目 34、提交 30、子行 28、组间 gap 10，泳道宽 22，`padding-left = 12 + lanes*22 + 12`。
- 本阶段不接动作，只把图渲染对：**1440 / 1024 / 768 / 375 四个宽度下，滚动后泳道与行仍像素级对齐**。
- 验收：截图 + 一段说明「坐标是怎么算的」。

### 阶段 2：状态与视觉

- 四种状态环（待审呼吸 + `!`、生成中旋转弧 + 用时、已采纳去饱和 + 绿勾、已驳回灰且无环）。
- 待审行左侧淡琥珀渐隐；组间 1px 发丝线；待审段虚线、历史段实线 + 底部回弧。
- 着色切换（按来源工具 / 按条目）、来源工具筛选（筛掉的变淡不隐藏）、图例（用绘制图表的同一套数据生成）。
- 验收：去掉颜色后，只看文字仍能读出每个状态。

### 阶段 3：侧栏与就地动作

- 侧栏 400px，复用 `renderKnowledgeMarkdown` + `DecodeText`，头部是事实栅格（工具 / Trace / 运行记录 / 生成时间 / 目标条目）。
- 待审行「采纳 / 驳回」就地打开 popover：采纳要选目标条目，驳回原因必填。
- 调 `promote` / `reject`。**每次提交前重新校验**：捕获 `409 KNOWLEDGE_CANDIDATE_NOT_PENDING`，不报错弹窗，而是刷新该行成真实状态并提示「该候选已被处理」。
- 成功后 toast 里要写清结果与**实际请求**（方法 + 路径 + 写入目标）。
- 验收：`409` 路径有截图或测试。

### 阶段 4：菜单与键盘

- 右键 / `Shift+F10` 打开审核快捷菜单，结构照 DESIGN §7：可用项写「将要执行的请求」，不可用项写「根本原因」。
- 键盘：`↑↓` 行导航、`Enter` 开关侧栏、`A` 采纳、`R` 驳回、`Esc` 逐级退出、`F` 聚焦条目链、`?` 图例。
- 验收：只用键盘能走完一次采纳和一次驳回。

### 阶段 5：接真数据 + 缺口落地

- 把 `reviewGraph` 接到 `getKnowledgeCandidates`，并把缺口 A/B/C/D 的结论写进实现说明：
  - A：候选挂哪条条目泳道（A1 待归类兜底 / A2 加 `target_entry_id`）
  - B：`promote` 只能新建条目 → 文案措辞
  - C：`生成中` 需要 run 状态 → 并行拉 `GET /api/operations/runs?status=RUNNING` 或后端补字段
  - D：图需要跨页聚合 → `pageSize=200` 或新增聚合端点，否则图底部必须写「仅显示最近 20 条」
- 验收：图上没有任何假状态；缺口处理方式可指回代码行。

## 组件拆分建议

```
views/knowledge/
  KnowledgeCandidateReviewView.vue      ← 只保留编排：取数 + 布局 + 事件分发
  reviewGraph/
    useReviewGraph.js                   ← 行模型与 y 计算（与渲染无关，可单测）
    ReviewGraph.vue                     ← 行 + 泳道层 + 头像层
    ReviewGraphRow.vue                  ← 四种行
    ReviewLaneLayer.vue                 ← <svg> 泳道（无 viewBox）
    ReviewSidePanel.vue                 ← 证据与正文（复用现有 KnowledgeReviewGraph 作为「证据关系」）
    ReviewActionMenu.vue                ← 快捷菜单
    reviewGraph.css                     ← 只新增，不改全局
components/knowledge/
  KnowledgeReviewGraph.vue              ← 保留，挪进侧栏
```

`useReviewGraph.js` 要有单测：给定种子数据，断言行数、每行 `y` 连续、同泳道行共用同一 `x`。

## 自检（提交前逐条打勾）

- [ ] 1440 / 1024 / 768 / 375 四宽度泳道对齐（滚动、切密度后仍对齐）
- [ ] 四状态不看颜色也能读
- [ ] 采纳含目标条目选择；驳回原因必填
- [ ] `409` 后该行刷新为真实状态且有提示
- [ ] 菜单无「能点但会失败」项；每个置灰项有原因
- [ ] 缺口 A/B/C/D 的处理方式写在实现说明里
- [ ] `guideMode` 不写库、不计统计、写操作禁用
- [ ] `↑↓ Enter A R Esc F ?` 全通
- [ ] `prefers-reduced-motion` 下无循环动画
- [ ] 代码里搜不到 `backdrop-filter` / 新增色相 / `viewBox`
- [ ] 200 行时首屏布局 < 100ms，滚动不掉帧（附测量方式与基线）

## 交付格式

1. 改动文件清单 + 每个文件一句话作用
2. 概念映射表（可复用上面的，但要补上「实际字段名」）
3. 四个宽度的截图
4. 缺口 A/B/C/D 的结论与对应代码行
5. 自检清单逐条结论（含未通过项的说明）
