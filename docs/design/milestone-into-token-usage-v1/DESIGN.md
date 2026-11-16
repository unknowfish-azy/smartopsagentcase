# 里程碑战报并入「用量与额度」—— 信息架构优化方案

- 日期：2026-11-16
- 状态：**已执行**（15:15 用户切 Agent 模式并要求「按上面方案执行；现在都是种子集，后面都要发展起来的」；第六节为实测结果）
- 执行口径：全部档位/成就从真实账本 report 派生，零硬编码数字；演示数据走独立常量并显式标注，便于后续种子集换真实数据无缝衔接。
- 用户诉求：里程碑战报完全可以放在「用量与额度」里面；侧栏「里程碑战报」那个菜单项可以去掉。
- 目标：把战报从**独立一级页面**降级为**用量与额度页内的一个子视图**；侧栏移除入口；旧链接不 404；零新接口、零新数据契约、不碰真实数据红线。

---

## 一、现状取证（只读）

| 项 | 里程碑战报 | 用量与额度 |
|---|---|---|
| 路由 | `/milestones` → `MilestoneHall`（`router/index.js:69`） | `/token-usage` → `TokenUsage`（`router/index.js:110`，props `mode:'tokens'`） |
| 组件 | `views/celebrate/AchievementsView.vue`（263 行，独立整页） | `views/model/ModelAnalyticsView.vue`（同一组件兼 `mode:'strength'`） |
| 数据 | 自己调 `getModelAnalytics(month)`，只读 `summary.calls` / `month` / `timezone` | 同一个 `getModelAnalytics(month)`，消费整份 report |
| 导航 | `INSIGHTS / 洞察与战报` 的 child（`personalSystemNavigation.js:30`） | `MODELS / 模型中心` 的 child（`:76`） |
| 入口芯片 | — | `ModelAnalyticsView.vue:16-20`：真实达档才显示 `.milestone-link` → `/milestones` |
| 视觉 | 双栏「MilestoneRain 动效 + 袋口档位阶梯 / 成就卡（真实+演示）」，桌面端**视口锁定双栏各自滚动**（`calc(100dvh - 206px)`） | 页头上 + 两个 tab（模型强度 / Token 用量）+ 筛选条 + 长滚动内容 |

关键结论：
1. **两者同源**：战报只从用量账本里取 `calls`，没有任何专属后端接口。合并后可以直接复用用量页已加载的 `report`，省掉一次请求、并统一月份口径（战报原本用「当前月」，用量页有用户可选 `month`——合并后必须跟随用量页的月份，否则同一页出现两个月份会自相矛盾）。
2. **战报页的视口锁定是为独立页写的**：`206 = 顶栏 56 + 工作区条 54 + content 底部留白 96`（`AchievementsView.vue:234-254`）。嵌进用量页后这个高度计算不再成立，必须改为「tab 面板内的自然流 + 受限高度」，否则会出现双滚动条 / 画布被裁。
3. **MilestoneRain 生命周期完备**：`ResizeObserver` + rAF 在 `onBeforeUnmount` 有完整清理（`MilestoneRain.vue:408-456`），用 `v-if` 切换 tab 是安全的（离开即销毁、不空转）。
4. **已录制视频第 38 镜是 `/milestones`**（`传智杯AIWEB-功能介绍视频-录制执行方案-20261115.md:177`）；讲解稿第 12 项也是独立战报页。所以**旧 URL 必须保留可访问**（用 redirect），不能让已录内容失效。

---

## 二、目标结构

```
侧栏 MODELS / 模型中心
  ├─ 模型接入      /model-settings
  ├─ 统一模型网关  /model-gateway
  ├─ 模型强度      /model-strength
  └─ 用量与额度    /token-usage        ← 唯一入口，内部两档视图
       ├─ [tab] 用量总览   /token-usage
       └─ [tab] 里程碑战报 /token-usage?view=milestones

侧栏 INSIGHTS / 洞察与战报
  └─ 自然语言洞察  /insights            ← 删除 MILESTONES child（第 30 行）

/milestones  →  redirect  →  /token-usage?view=milestones   （兼容书签 / 视频 / 外链）
```

**URL 与参数契约**
- 用 `?view=milestones` 作为 tab 状态（可分享、可深链、浏览器前进后退可用）；默认无参数 = 用量总览。
- redirect 必须透传原 query：`/milestones?preview=1&ambient=0` → `/token-usage?view=milestones&preview=1&ambient=0`（`preview` 自动播一次庆祝、`ambient=0` 关持续动效的既有语义不丢）。
- 顶栏面包屑 `section` 对 `?view=milestones` 显示 `TOKEN USAGE / 用量与额度 · 里程碑战报`。

---

## 三、工作包（交实现模型）

### T1　路由与导航（最小骨架）
1. `src/router/index.js:69`：`/milestones` 改为函数式 redirect，透传 query：
   `redirect: to => ({ path: '/token-usage', query: { ...to.query, view: 'milestones' } })`，`name`/`component` 移除（避免同名路由与 meta 冲突）。
2. `src/navigation/personalSystemNavigation.js:30`：删除 INSIGHTS 的 MILESTONES child。删完该组只剩 1 个子项——**建议把 `insights` 由 `expandableGroup` 退化为 `directGroup`**（单子项展开组是冗余交互）；若要最小改动也可保留，但需明确记录为待裁决。
3. `src/navigation/routeMetadata.js:24`：删除 `MilestoneHall` 条目（redirect 路由不再需要 meta；留着反而制造「幽灵导航项」，`findPersonalSystemGroup('MilestoneHall')` 应返回 `null`）。
4. 命令面板 `navigationDiscovery.js` 自动从导航生成条目 → 删掉菜单项后搜索里也不会出现战报。**这是副作用**：建议给 `navigationEntries` 加一条固定别名 `{ to:'/token-usage?view=milestones', title:'里程碑战报', label:'MILESTONES', group:'模型中心' }`（不改侧栏、只恢复可搜索性）；是否加列为待裁决 D1。

### T2　把战报抽成面板组件
新建 `src/components/model/MilestoneReportPanel.vue`，从 `AchievementsView.vue` 搬运模板/逻辑/样式，做三处适配：
1. **props 驱动**：`report`（用量页已加载的账本）、`month`、`ambientOn`、`preview` 由父级传入；组件内**不再自己调 `getModelAnalytics`**，删掉 `loadReport/loading/error/disposed`。`achievements`、`callProgress`、`callTiers`、`vesselReadout` 的计算原样保留，只是把 `report.value` 换成 `props.report`。
2. **去掉页级壳**：删 `<h1>里程碑战报</h1>`、eyebrow、intro、右上角「查看用量明细」按钮（已在用量页里，按钮无意义）；保留子区块标题（`THIS MONTH / 本月进度`、`MOUTH TIERS / 袋口档位`、成就卡、演示分隔与 demo 卡、footer 来源说明）。
3. **布局去视口锁定**（关键）：删 `AchievementsView.vue:238-254` 整段 `@media(min-width:1101px)` 的 `height:calc(100dvh - 206px)` + 双栏 `overflow-y:auto`；改为 `.hall-layout { display:grid; grid-template-columns:minmax(300px,5fr) minmax(0,7fr); align-items:start }`，画布容器保留 `position:relative`、`overflow:visible`（`MilestoneRain` 绝对定位铺满 stage 的宿主契约不能破）。窄屏 `@media(max-width:1100px)` 单列保持不变。
   - 若坚持保留「左右两栏各自滚动」手感，改为 `max-height:min(62dvh, 620px)` + `overflow-y:auto` + `overscroll-behavior:contain`，**不要**再按 206px 常量算。
4. `AmbientOn` / `raining` / `statusText` / `onFinished` / `celebrate(item)` 等交互状态保留在面板内；`ambient=0` 的初始值由父级解析 query 传入。

### T3　用量页接入子视图
`src/views/model/ModelAnalyticsView.vue`：
1. 在现有 `.analytics-tabs`（第 10-13 行）下方加第二级 tab（或用同一行扩展为三档：`模型强度 | Token 用量概览 | 里程碑战报`）。**推荐同一行三档**，避免两级 tab 叠床架屋：
   ```
   <RouterLink to="/model-strength">模型强度</RouterLink>
   <RouterLink to="/token-usage" :aria-current="!isMilestoneView">Token 用量与额度</RouterLink>
   <RouterLink :to="{ path:'/token-usage', query:{view:'milestones'} }" :aria-current="isMilestoneView">里程碑战报</RouterLink>
   ```
   `isMilestoneView = computed(() => isTokens.value && route.query.view === 'milestones')`。
2. `?view=milestones` 时：
   - 隐藏 `.milestone-link` 芯片（已在目标页，避免自指；或把芯片改成「回到用量总览」——二选一，建议直接隐藏）、筛选条、demo 控件、所有用量图表/额度表单、footer——即把 `<template v-else-if="report">` 整段包在 `v-if="isTokens && !isMilestoneView"`，另一分支渲染 `<MilestoneReportPanel :report="report" :month="month" ... />`。
   - `h1` 文案切为「用量与额度 · 里程碑战报」，`route-context` 由 meta 提供。
   - **分享同一个 `report`**：面板只读 `report.summary.calls`，与用量总览完全同源；月份筛选条隐藏后，`month` 保持当前值，面板底部来源说明显示同一月份。
3. **demo 模式**：`isDemo` 为 true 时也允许切到战报 tab，但面板内必须沿用「演示实例 · DEMO — 非真实账本数据」标注；且**禁止把 demo 的 250 次调用喂给真实档位庆祝**（现有 `achievements.js` 的 `DEMO_ACHIEVEMENTS` 是独立常量，不要混用）。若实现成本高，可在 demo 模式下禁用战报 tab 并提示「返回真实数据后查看里程碑」——列为待裁决 D2。
4. tab 切换用 `v-if`，让 MilestoneRain 正确卸载（生命周期已完备见取证 3）。

### T4　测试契约同步
| 文件 | 改动 |
|---|---|
| `frontend/test/personal-system-navigation.test.mjs:57-67` | 把「milestone hall lives inside insights」改为「milestone hall is not a top-level navigation item」：`assert.equal(findPersonalSystemGroup('MilestoneHall'), null)`，并断言 insights 子项只剩 `['Insights']`（若退化为 directGroup 则 `[]`）。 |
| 同文件 `:118` | models 子项断言**保持不变**（战报不在侧栏 models 里，只在该页 tab 里）。 |
| `frontend/test/milestone-rain.browser.mjs` | 所有 `page.goto('/milestones...')` → `/token-usage?view=milestones...`；芯片用例（300-313 行）改为：点击 `.milestone-link` 后 `waitForURL('**/token-usage?view=milestones')` 且面板 heading 可见；新增「旧链接兼容」用例：`goto('/milestones')` 后 URL 变为 `/token-usage?view=milestones` 且内容可见。 |
| `frontend/test/zz-debug-milestone.mjs` / `zz-debug-timeline.mjs` / `zz-diag-rain.mjs` / `zz-measure.mjs` | 临时调试脚本，`/milestones` 由 redirect 兜底可不改；若顺手改统一走新 URL。 |
| 新增（建议）`test/milestone-tab.browser.mjs` | 三档 tab 切换、query 前进后退、`view=milestones` 下不再发起第二次 `getModelAnalytics`、画布切换无 pageerror、reduced-motion 单帧。 |
| `frontend/test/home-orbit.browser.mjs:33` | 不变（用量链接仍 `/token-usage`）。 |

### T5　材料口径同步（低优先，用户裁决后执行）
- `docs/competition/演示讲解稿-4分钟-逐页.md:154`（第 12 项「里程碑战报」）与第 13 项模型中心的顺序描述：合并后改为「模型中心 → 用量与额度 → 里程碑战报子视图」的口播顺序。
- `docs/competition/传智杯AIWEB-功能介绍视频-录制执行方案-20261115.md:177`（第 38 镜 `/milestones`）：**视频已录制，不改画面**；仅在脚本/讲解稿文字层标注「URL 现重定向到 `/token-usage?view=milestones`，画面内容不变」。
- `docs/competition/fact-sheet*`（若有导航项数量口径）：同步「一级导航项 −1」。

---

## 四、验收门禁

1. **纯函数 / 静态**：`npm test`（含改后的导航契约，全绿）、`npm run typecheck`、`npm run lint`（0 error）。
2. **构建**：`npm run build` 通过；`MainLayout` 分包不变（不要因新增组件把 echarts / three 拉进首屏）。
3. **浏览器实测**（dev server 5173，带 session mock）：
   - 侧栏搜索「里程碑」→ 命令面板仍可直达（若采纳 D1）；侧栏 DOM 中无「里程碑战报」链接。
   - `/token-usage` 三档 tab 可点、`aria-current` 正确；`?view=milestones` 深链直达；浏览器后退回到用量总览。
   - 战报面板：真实档位阶梯、成就卡、演示卡分区标注不变；`MilestoneRain` canvas 有内容、非 0 尺寸。
   - tab 往返切换 3 次：无 pageerror、`document.querySelectorAll('canvas').length` 不累积（验证卸载）。
   - `/milestones?preview=1&ambient=0` 重定向后 query 完整保留。
   - 移动 375px：tab 不溢出、面板单列、画布不裁切。
4. **可访问性**：`npm run test:a11y` 0 serious/critical；tab 用原生 `<a>`/`RouterLink`，键盘可达、焦点可见。
5. **红线**：面板不出现收益 / 回撤 / 金额；演示项始终带 DEMO 标注；月份与用量总览一致。

---

## 五、风险与待裁决

**风险**
- **视口锁定迁移**是本次最大实现风险：原页双栏独立滚动依赖整页高度常量，嵌入后必须改成面板内高度，否则画布被裁或双滚动条。门禁 3 的 canvas 实测是硬门槛。
- **同一组件双模式**：`ModelAnalyticsView.vue` 同时服务 strength / tokens，改动要包在 `isTokens` 里，避免污染「模型强度」页。
- **已录制视频**：只靠 redirect 保护，不改画面；如裁决 D3 不保留 redirect，需用户单独确认（会导致视频第 38 镜 404）。
- **已达成档位的庆祝动效**：切 tab 后 `v-if` 重建，若 `preview=1` 会自动播一次；需确认不因 tab 切换重复播放（用 `route.query` watch 而非组件mounted 触发）。

**待裁决**
- **D1**：命令面板是否保留「里程碑战报」搜索别名？（推荐：保留，删侧栏不等于删可发现性）
- **D2**：demo 模式下战报 tab 是「可看但演示标注」还是「禁用并提示返回真实数据」？（推荐：可看 + 强化 DEMO 标注，保持演示链路完整）
- **D3**：`/milestones` 是否一定保留 redirect？（推荐：必须保留，视频与外链兼容）
- **D4**：`insights` 分组是否退化为 `directGroup`？（推荐：退化，单子项展开组冗余）
- **D5**：三档 tab 与两档 tab + 二级 tab 的取舍？（推荐：三档同一行，最省交互层级）

---

## 六、决策摘要（一句话版）

> 战报本来就是用量账本的「成就视图」，没有独立数据；把它收进 `/token-usage?view=milestones` 的子视图，侧栏删项、旧链接重定向、面板复用同一份 report，唯一要小心的是把原整页的视口锁定改造成面板内布局。

---

## 七、执行结果（2026-11-16 15:15–15:35）

**落地决策**（用户未逐项裁决，按方案推荐执行）：D1 保留命令面板别名 ✓｜D2 demo 模式**禁用真实档位**、只显示「虚构数据不生成里程碑」说明卡（比原推荐的「强化标注」更保守，避免种子集阶段把演示数当成就）｜D3 `/milestones` 保留 redirect ✓｜D4 insights 退化为 directGroup ✓｜D5 三档同一行 tab ✓。

**改动文件（10 个）**
| 文件 | 改动 |
|---|---|
| `src/router/index.js` | `/milestones` → 函数式 redirect 透传 query |
| `src/navigation/personalSystemNavigation.js` | 删 MILESTONES child，insights 退化为 directGroup |
| `src/navigation/routeMetadata.js` | 删 `MilestoneHall` 条目 |
| `src/navigation/navigationDiscovery.js` | 加固定别名，命令面板仍可搜「里程碑」 |
| `src/components/model/MilestoneReportPanel.vue`（新增） | props 驱动面板，复用父级 report；去页级壳、去视口锁定；保留双栏独立滚动（受限高度 `min(62dvh,620px)`）与画布宿主契约 |
| `src/views/celebrate/AchievementsView.vue` | 改为兼容薄壳，不再重复档位计算 |
| `src/views/model/ModelAnalyticsView.vue` | 三档 tab + `?view=milestones` 分支；标题/intro 跟随视图；战报视图隐藏筛选条、demo 控件与 chip；demo 模式显示说明卡 |
| `test/personal-system-navigation.test.mjs` | 断言战报不再是导航项、insights 无子项 |
| `test/navigation-discovery.test.mjs` | 别名可搜索 + 不重复路径 |
| `test/milestone-rain.browser.mjs` | URL 改子视图、芯片改切 tab、新增旧链接 redirect 与 tab 往返用例、页面滚动断言改为「两栏互不影响」 |

**门禁结果**

| 命令 | 结果 |
|---|---|
| `npm test` | ✅ **806 / 806 pass**（含 2 条新静态契约） |
| `npm run typecheck` | ✅ 0 error |
| `npm run lint` | ✅ 0 error / 4 warning（均在 TRAE 并行改的文件：`KnowledgeAtlasView` / `FieldPlane` / `cloud-engineering-tools`） |
| `npm run build` | ✅ 32.34s，仅既存 chunk >500kB 提示 |
| `node test/milestone-rain.browser.mjs` | ✅ **7/7 PASS**：真实账本动效 / ambient 暂停恢复 / 375px / reduced-motion / 芯片切 tab / 旧链接 redirect 透传 query / tab 往返 3 次 canvas 恰好 1 个且无 pageerror |
| `npm run test:a11y` | ✅ 0 serious/critical、0 overflow、0 pageErrors、axe 无违规 |
| 真实浏览器（5173） | ✅ 三档 tab 正确、当前 tab 高亮、面板高 558px、画布 1 个、`/milestones?preview=1` 落 `/token-usage?preview=1&view=milestones`、0 page error |

截图：`frontend/test-artifacts/milestone-tab-usage.png`、`milestone-tab-report.png`（该目录已 gitignore）。

**关键坑（实现侧注意）**
1. `.vessel-panel { overflow: visible }` 是画布宿主契约，必须写在 `@media(min-width:1101px)` 的 `overflow-y:auto` **之前**；反过来简写会把滚动重置成 `visible`，浏览器测试直接挂。
2. 战报嵌入后页面本身可滚动，不能再用独立页的 `document.body.scrollHeight <= innerHeight` 断言；改为只断言「两栏互不干扰」。
3. 真实环境 mock 必须返回合法 report 形状（`summary`/`models`/`daily` 齐全），否则 `ModelAnalyticsView` 渲染会因 `undefined.length` 抛错——这是 mock 问题，不是代码 bug。
4. 截图复核发现标题与筛选条在子视图下语义不符，已补 `isMilestoneView` 条件（标题切换 + 筛选条隐藏）。

### T5　材料口径同步（2026-11-16 15:33 续做完成）

用户「继续」= 授权执行方案剩余的 T5。三处同步，**视频画面零改动**：

| 文件 | 改动 |
|---|---|
| `docs/competition/演示讲解稿-4分钟-逐页.md` | 原第 12 项「里程碑战报」与第 13 项模型中心合并：改为第 12 组（模型中心 12a–12d + 12e 战报 tab），口播强调「与用量总览同一份账本、同一统计月份、不单独请求」，旧 `/milestones` 自动重定向。 |
| `docs/competition/传智杯AIWEB-功能介绍视频-录制执行方案-20261115.md` | 第 38 镜仅补注「旧 URL 现重定向到 `/token-usage?view=milestones`，已录制画面零改动、内容不变」；镜号 / 画面 / 旁白 N19 全部保留。 |
| `docs/competition/时序预测模块-逆向与TRAE执行包-20261119.md` | 导航顺序快照更新为当前分组结构，删除已移除的 CLOUD NATIVE / PLUGINS / SKILLS / 连接中心 / HARBOR / HEALTH CENTER / MILESTONES；注明战报新入口，SENTINEL 落位结论不变。 |

未发现需要同步的其他材料：`fact-sheet.md`、作品介绍稿（4 分钟 / 详细版）、`demo-script.md`、`defense*.md`、`technical-document.html`、四件套打印版均无战报 / 导航项数量口径。

**至此 T1–T5 全部完成。**
