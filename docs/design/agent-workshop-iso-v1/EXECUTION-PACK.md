# Agent 工坊 · 等距工作室特效层 执行包 v1.0

> 交实现模型照做。前置阅读 `DESIGN.md`。**开工前须用户明示「开始实施」**——省赛（11-18）前默认只冻结设计。
> 编号接续：工作包 T28–T31（照片墙止于 T27）、待裁决 D9–D12（照片墙止于 D8）。

## 0. 硬约束（违反任一即打回）

- 红线：不出现任何金额/收益/余额字样与曲线；不伪造繁忙（无事件=静默）；DEMO 态标注 `REHEARSAL`。
- 零改动既有 Fable 组件（FableComposition/FableGaze/FatBlob/五面板）——只加分支，不改内部。
- 所有颜色经 CSS 变量令牌取色，禁硬编码 hex 到组件（几何路径坐标除外）。
- 全量门禁：typecheck 0 / lint 0 error / 双端构建 / 前端 733+ 单测不回退 / 浏览器实测 0 报错。

## T28 工坊几何与布局纯函数

- 新增 `frontend/src/views/agent/fable/workshop/workshopLayout.js`：
  - `buildWorkshop(tools, loopSteps, cols)` → 返回房间尺寸、每工位 `{id, x, y, tone, labelCn, labelEn}`、四站轨道坐标、墙屏/机柜锚点；
  - 等距换算 `iso(x, y, z)`（2:1 轴测）纯函数；
  - 布局须容 6 工位（2 行 × 3 列）+ 中央轨道，房间宽高比 ≈ 16:9。
- 单测 `frontend/test/workshop-layout.test.mjs`：工位不重叠、轨道四站闭合、iso 换算往返一致、窄屏退化阈值。
- 验收：纯函数单测全绿，无任何 Vue/DOM 依赖。

## T29 工坊渲染组件

- 新增 `workshop/IsoWorkshopRoom.vue`（房间骨架：地板网格、墙、墙屏、机柜、装饰）与 `workshop/IsoDesk.vue`（工位：桌台/终端/几何小人/灯态）与 `workshop/IsoCable.vue`（缆线 + 脉冲光点）。
- 状态机：`idle / lit / pulsing / rehearsal` 四态；props 只吃数据，不吃定时器。
- 小人 = SVG 几何拼装（圆头+梯形身），E6 注视 = 头部 group `rotate` 朝活跃工位。
- 动画仅 `transform/opacity`，经 `motionScheduler` 订阅；`reduced` prop 直通静态单帧。
- 验收：Storybook 式直开（dev 路由或临时页）肉眼走查四态 + 双主题截图。

## T30 真实事件绑定

- `AgentModuleView` 增视图 pill（`构成 / 工坊`），工坊分支从既有 `loops`/`loopsStats`/`liveField` 派生工位状态：
  - step→工具映射：感知→结果核查预备、规划→风险策略、执行→安全执行、核查→结果核查；审批命中→人工审批工位；知识命中→混合检索工位；闭环落账→审计留痕工位；
  - E1 亮灯 600–900ms 后自然熄灭；E2 光点沿缆线滑一次；E3 徽章沿轨道逐站；E4 墙屏折线接 `getDecisionLoopStats`；E5 机柜灯 = 拉取成功心跳。
- tooltip：闭环 id/step/耗时/时间；点击滚动并高亮「闭环记录」面板对应条目。
- 验收：浏览器实测——触发一次真实问答/任务，断言 ≥3 张工位依序点亮且 tooltip 可溯源；断网 → 全屋休眠 + REHEARSAL 标注。

## T31 门禁收口

- 窄屏 <768px 列表退化组件 `workshop/WorkshopFallbackList.vue`；
- axe 对比度复测（双主题）0 严重；键盘 Tab 遍历工位可达可激活；
- `docs/competition/demo-script.md` **暂不改**（省赛口径冻结）；国赛晋级后再补「工坊」演示段与答辩词；
- 双主题截图入 `frontend/test-artifacts/workshop/`（证据）；
- 提交拆两笔：`feat(agent): 工坊特效层 T28–T29`、`feat(agent): 闭环事件绑定与门禁 T30–T31`。

## 验收快查（DoD）

- [ ] T28 单测绿；T29 四态走查；T30 真实事件点亮可溯源；T31 十二条门禁全绿
- [ ] 构成视图零 diff（`git diff` 不含 Fable 三组件与五面板改动）
- [ ] reduced-motion 静态单帧；窄屏列表退化；DEMO 态 REHEARSAL 标注
- [ ] 无金额字样、无霓虹粉、无位图 sprite（代码评审核对）

---

## 实施记录（2026-11-15，T28–T31 已完工）

> 用户裁决：推翻「省赛期冻结」，当日实施。以下为实际落地情况与设计偏差。

**交付物**（全部按包路径落地）：
- T28：`workshop/workshopLayout.js`（iso/inverseIso、buildWorkshop、deskActivity、sparklineFromLoops、loopDuration、isNarrowViewport）+ `test/workshop-layout.test.mjs` 16 条单测。
- T29：`IsoWorkshopRoom.vue` / `IsoDesk.vue` / `IsoCable.vue` / `WorkshopFallbackList.vue`；动画经 `motionScheduler` 订阅（fps 30，id `workshop-room`），无事件时自动停表静默；reduced-motion 静态单帧。
- T30：`AgentModuleView` 增「构成 / 工坊」pill（默认构成，D9）；stage→工位映射落地为 ANALYZE→混合检索、MEMORIZE→审计留痕、DECIDE→风险策略（requiresHuman→人工审批、已出决策→安全执行）、REVIEW→结果核查、LEARNED→审计留痕（list 接口无 step 字段，按 stage 映射，比设计粒度略粗但全部真实可溯源）；tooltip 溯源 + 点击高亮「记忆尾迹」对应闭环条目。
- T31：窄屏退化（<768px 列表）、断网 REHEARSAL 水印、双主题截图入 `frontend/test-artifacts/workshop/`、`test/workshop-browser-check.mjs` 六项浏览器验收。

**门禁结果**：eslint 0 error / tsc 0 / 单测全量 749 全绿（733 存量 + 16 新增）/ 双端构建过 / 浏览器实测六项全过 / `git diff` 确认 Fable 三组件与五面板零改动 / 红线词扫描干净。

**实施偏差（3 处，均已验证）**：
1. 令牌：初版误用不存在的 `--ds-surface`，已改为 `--ds-surface-base/raised`（双主题截图验证）；
2. 墙屏：z=2.6 会穿墙沿，降为 z=1.1、高 42px（z+height ≤ 墙高 72px）；
3. 窄屏：`.stage-field` 窄屏仅 ~78px 高，工坊列表退回文档流自撑高度（`is-narrow` 置 relative + min-height 300px）。

**遗留**：`docs/competition/demo-script.md` 按包要求未动；两笔提交见 git log。
