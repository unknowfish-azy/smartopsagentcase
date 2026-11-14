# 实现提示词：知识库的立体空间视图

把下面整段发给 Trae（或任何能改本仓库的模型）。它要求仓库里已有 `docs/design/knowledge-spatial-ia-v1/`。

---

## 你的任务

给知识库加一个**空间视图**：把 737 条条目铺成一张能缩放的地图——域是街区，条目是卡片，连线是关系，缩放就是导航。默认仍保留现有列表/网格视图，三态可切换。

**先读、再核对数据、后实现。** 第一步只输出：数据核对表 + 布局算法伪代码 + 分阶段计划，等我确认后再动代码。

## 开工前必读

| 文件 | 从中拿到 |
| --- | --- |
| `docs/design/knowledge-spatial-ia-v1/REVERSE.md` | 逆向报告：Expo Mode 的模型、HTML-in-Canvas 的真实能力与限制、为什么我们不选 WebGL |
| `docs/design/knowledge-spatial-ia-v1/DESIGN.md` | 全案：真实数据统计、三档 LOD、布局算法、相机、连线规则、性能预算、**四个数据缺口**、验收清单 |
| `docs/design/knowledge-spatial-ia-v1/index.html` | 参考原型（CSS 3D，10 域 + 真实条目标题），可直接读布局与相机代码 |
| `frontend/src/views/knowledge/knowledgeCatalog.js` | `knowledgeDomains`(7) 与 `knowledgeEntries`(**737**) 的真实数据 |
| `frontend/src/views/knowledge/knowledgeLibrary.js` | `knowledgeReadApi`（tree/node/path/search）——**契约不改** |
| `design-system/MASTER.md` | 工具层契约：零 WebGL、零 blur、半径 4-8、语义色收敛 |

## 硬约束

1. **不改 `knowledgeCatalog.js` 的数据结构**。缺字段就按 DESIGN §9 的缺口方案处理，不要偷偷加字段。
2. **不用 `three`、不用 WebGL、不用 `html2canvas`**。渲染路线是 CSS 3D（`perspective` + `translate3d` + `scale`），卡片保持真实 DOM。理由见 REVERSE.md §5——卡片一旦变成纹理，就丢了可选中文本、读屏与 Ctrl+F，那正是我们要复刻的那套技术的价值所在。
3. **动画只用 `transform` / `opacity`**；`will-change` 只在动画期间挂，结束摘掉；禁止 `filter: blur`、禁止 `backdrop-filter`。
4. **域坐标在会话内恒定**。布局只在数据变化时重算，容器 resize 只改相机。抖动会让人失去空间记忆。
5. **必须做 LOD + 虚拟化**：737 条不可能全挂 DOM。L0 只挂域块；L1/L2 只挂视口内域（≤3 个）；同时挂载卡片 ≤120 张。
6. **标签走屏幕空间**（HUD），不随相机缩小；域在屏幕上窄于 92px 时只留色条不写字，避免相邻标签打架。
7. **连线必须在图例里写明「由 platform/service/type 推断，不是人工确认的关系」**。
8. **三视图共享同一份数据与语义**：空间 / 网格 / 列表，切换不丢选中项，键盘与读屏都能完成「检索 → 打开正文」。

## 分阶段执行（每阶段结束等我确认）

### 阶段 1：布局纯函数 + 单测

- 新建 `views/knowledge/space/useSpaceLayout.js`：`(entries, domains) → { zones[], cards[] }`，**不 import Vue、不碰 DOM**。
- 算法按 DESIGN §3.2：面积 `√n` 归一 → 递归切块 → 街道内缩 → 域内网格。
- 单测（沿用 `frontend/test/*.test.mjs`）：
  - 737 条真实数据跑一遍，10 个域都有矩形，互不重叠；
  - 同输入两次调用结果**完全一致**（坐标恒定）；
  - `linux` 面积 / `centos` 面积 ≈ `√225 / √1`（容差 5%）；
  - 单域布局耗时 < 3ms。
- 验收：`node --test` 通过，并贴出耗时。

### 阶段 2：相机 + LOD

- `useSpaceCamera.js`：`{k, tx, ty}`、锚点缩放、`flyTo(zone)`、`centerOn(x,y,k)`、`Esc` 三级回退、`0` 回总览。
- LOD 判定 `k < 0.42 → L0；< 1.05 → L1；否则 L2`，写进 `data-lod`。
- 标签 HUD：屏幕空间定位，`font-size` 恒定，`w<92` 跳过。
- 验收：滚轮缩放时指针下的卡片位置不动（录 3 秒或截图前后坐标）；跨档不跳变。

### 阶段 3：卡片、连线、检索

- `SpaceCard.vue`：三档内容（L0 无色块正文 / L1 标题+type chip / L2 加摘要）。
- `SpaceLinks.vue`：单 SVG，线宽按 `1/k` 补偿；单域连线 >400 条时只保留同平台与 `INCIDENT↔RUNBOOK` 两类。
- `SpaceSearchBar.vue`：接 `knowledgeReadApi.search`；命中点亮、其余 25% 不透明（不隐藏）；命中首个自动 `flyTo`。
- 验收：检索「nginx」命中数正确，图例写明推断关系。

### 阶段 4：虚拟化与性能

- 域级虚拟化 + `IntersectionObserver` 卡级可见性；离开域 500ms 后卸载卡片 DOM、保留坐标。
- 实测 DESIGN §6.2 六项预算，写进 `docs/design/knowledge-spatial-ia-v1/PERF.md`（**设备、分辨率、Chrome 版本、前后对比**）。
- 验收：737 条数据下同时挂载卡片 ≤120、L0 首屏 ≤300ms、稳态帧时 ≤8ms。

### 阶段 5：三视图 + 无障碍 + 缺口

- 空间 / 网格 / 列表切换；`aria` 语义与键盘路径一致。
- 落地缺口 A（10 个域都有名字）、缺口 C（31 条 `type` 缺失标「未分类」），缺口 B/D 在实现说明里写清现状。
- 验收：只用键盘完成「`/` 检索 → `Enter` 打开正文」；`prefers-reduced-motion` 下无动画无惯性。

## 交付格式

1. 改动文件清单 + 每文件一句话
2. 数据核对表：设计里用到的每个字段 ← `knowledgeCatalog.js` 的哪个属性（缺哪个标红）
3. 四张截图：L0 总览 / L1 域内 / L2 卡片+侧栏 / 列表视图
4. 单测输出 + `PERF.md` 六项预算
5. `DESIGN.md §11` 验收清单逐条打勾，未通过项写原因
6. 已知限制（例如小域不显示名字、推断关系不是真依赖）

## 一句话判据

用户打开这个视图 5 秒内应该说出：**「哪些域最重、哪条和我现在的事最近、我怎么进去看它。」**
如果 3D 效果很好看但看完还是不知道知识库长什么样，就是没做成。
