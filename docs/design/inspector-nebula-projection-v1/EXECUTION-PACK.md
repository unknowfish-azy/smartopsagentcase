# 纠察星云投影 执行包 v1.0（工作包 T32）

> 交实现模型照做。前置阅读同目录 `DESIGN.md`。开工须用户明示；与工坊包 `agent-workshop-iso-v1`（T28–T31）并列，独占编号 T32。
> 所有硬约束、门禁纪律与工坊包一致：typecheck 0 / lint 0 error / 双端构建 / 全量单测不回退 / 浏览器实测 0 报错；零金额字样、零伪造繁忙、令牌化取色。

## 锚点（已核实，勿重勘察）

- 投影定义：`frontend/src/views/inspector/InspectorDeskView.vue:104` `projections` 数组（events/stats/runs 三项）。
- 渲染：`frontend/src/components/inspector/desk/DeskProjections.vue`；数据模型：`desk/deskModel.js`；抽屉：`DeskDrawer.vue`；选中态：`DeskSelection.vue`。
- 事件数据：`/api/inspector/events`（`id/createdAt/severity/taskId/category/target/traceId/...`）与 `/api/inspector/summary`，加载/空/错/DEMO 四态已在视图层就绪。
- 等级四色与维度八色：`frontend/src/components/inspector/dimensions.js` + 纠察中心既有令牌。

## T32 实施步骤

### a. 投影数学纯函数
- 新增 `frontend/src/components/inspector/desk/nebulaProjection.js`：
  - `buildNebula(events, window)` → 粒子数组 `{id, severity, category, theta(经度=窗口内时间比例), phi(纬度=等级环带), size, age}`，超 1000 条按时间均匀抽样并返回 `{sampled, total}`；
  - `project(particles, rotY, rotX, w, h)` → 2D 屏幕坐标 + 深度排序（画家算法，back→front 绘制）；
  - 纯函数、零 DOM 依赖。
- 单测 `frontend/test/nebula-projection.test.mjs`：抽样正确、四环带纬度互斥、经度随时间单调、投影往返、深度排序稳定。

### b. 渲染组件
- 新增 `frontend/src/components/inspector/desk/NebulaProjection.vue`：
  - Canvas 2D + 手写旋转矩阵透视投影；自转 ≈28s/圈（视觉调校自 40s） + 呼吸微光；不引 three.js；
  - `reduced` prop → 静态单帧；掉帧降采样 1000→500→250；`<768px` 由视图层隐藏 tab；
  - 等级四色/维度八色全部经令牌取色；背景 hairline 圆环 + 等级刻度，无渐变科幻底。
- `InspectorDeskView.vue`：`projections` 追加 `{ key: 'nebula', cn: '星云', en: 'NEBULA', desc: '每个事件是一颗星：等级是纬度 · 时间是经度' }`（排第 4，默认仍 events——D13）；`DeskProjections.vue` 加 nebula 渲染分支。
- 转场：切入星云时粒子从平面投影位置 600ms 汇聚成球（仅 transform/opacity）。

### c. 交互与联动
- hover：粒子放大 + tooltip（taskId/等级/维度/时间），其余降透明度；维度重着色"色环扫描"；
- click：开既有 `DeskDrawer`，选中态写回 `DeskSelection`（点/柱/条同步高亮）；
- 空态：复用视图层现成空/错态；DEMO 态星云核 `DEMO` 水印（双重虚构标注沿用）；
- a11y：容器 `role="img"` + aria-label（"星云投影，N 颗事件：A 级 x、B 级 y…"）；Tab 提供"下一事件"键盘遍历并聚焦对应粒子。

### d. 门禁收口
- 浏览器实测脚本 `frontend/test/nebula-desk.browser.mjs`：真实数据 ≥3 等级粒子可见、tooltip、点击开抽屉且联动、转场汇聚、DEMO 水印、0 报错（mock 路由锚定根 `/api/`，勿用 `**/api/**`——照片墙实测已踩过误匹配源码模块的坑）；
- 双主题截图入 `frontend/test-artifacts/nebula/`；
- a11y axe 复测 0 严重；
- 提交单笔：`feat(inspector): 洞察台第4投影「星云」T32（真实事件粒子云+证据联动）`。

## DoD 快查

- [ ] 投影纯函数单测全绿；四重降级（reduced/掉帧/抽样/窄屏）逐条验证
- [ ] 选中态三视图↔星云双向联动；证据抽屉零新契约
- [ ] 默认投影仍为「纠察」（省赛分镜口径零破坏）；demo-script 暂不改
- [ ] 无金额、无霓虹粉、无 three.js、无 blur；抽样有脚注；空态非空转球
