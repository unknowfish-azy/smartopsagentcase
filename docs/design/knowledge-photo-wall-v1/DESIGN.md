# 知识库 · 照片式密铺排布（Photo Mosaic Wall）方案 v1.1 · 项目实参校准

日期：2026-11-14（v1.0 方向确立 → v1.1 项目实参校准 → 22:00 裁决确认）
状态：**方案定稿，D5–D9 已由用户确认**（本智能体只出方案，未改代码、未跑构建/测试、未提交）
执行指令：`docs/design/knowledge-photo-wall-v1/EXECUTION-PACK.md`（T23–T27 逐包，实现模型以此执行）
适用路由：`/knowledge/space`（不新增路由）
参考图：用户 2026-11-14 的手机系统相册截图（密集缩略图墙 + 年份浮标签 + 底部视图切换）
用户确认："对是这种效果，但是这个是知识库，你根据这个项目设计方案然后调整"
约束基线：`design-system/MASTER.md`、`frontend/src/assets/styles/variables.css`、T11 门禁基线

> **v1.1 校准依据**：直接 `import` 项目 `knowledgeCatalog.js` 跑只读统计（`node --input-type=module`，无写文件、无构建），并读码核对令牌、相机、组件与测试契约。以下所有数字为 **observed**，不是引用旧文档、不是推断。

---

## 0. v1.0 → v1.1 变更摘要（实现模型务必按 v1.1 做）

| # | v1.0 的假设 | 实测 / 读码结论 | v1.1 修正 |
|---|---|---|---|
| 1 | 从 `searchableKnowledgeEntries` 取全量 | 该常量在 `knowledgeCatalog.js:323` 是**未导出的 const** | 改用 **`searchKnowledgeEntries({})`**（导出，返回 737 条且带 `directory`）；不改 catalog |
| 2 | 格子角标用 `reviewStatus` | 737/737 全是 `UNVERIFIED`，恒灰、零信息量 | **移除状态点**，改用 `risk`（READ_ONLY 376 / REFERENCE 144 / APPROVAL_REQUIRED 72 / HIGH 52 / MEDIUM 19 / 长句 29） |
| 3 | 格子/详情显示证据数 | `evidenceRefs` **737 条全不存在** | P0 一律 `—`；证据数若做只能 P1 从 `bindingIndex.js` 派生并标注来源 |
| 4 | 复用 `FieldPlane.vue` 的 8 色 `TYPE_COLORS` | `type` 实测 **57 种取值**，8 色表覆盖不到 → 大半墙会变灰 | 新增 `mosaicType.js` 归一化成 7 个上位类 + 用 `--ds-chart-1..5` 着色；**详情窗仍显示原始 type** |
| 5 | S3 显示摘要 2 行 | `summary` **缺 188 条（25.5%）** | 缺失沿用项目现有文案「当前资料暂未记录摘要。」/ `—`，**不拿 `content` 冒充摘要** |
| 6 | 详情显示 `applicableVersion` | 737 条全为占位符「未注明适用组件版本」 | 识别占位符并按缺失显示 `—`，禁止把占位符当真实版本 |
| 7 | 配色写死 `#05090D` / `#071018` | `variables.css` 是 `:root` 深色 + `[data-theme='light']` 浅色**双主题** | **全部改用 `var(--ds-*)` 令牌**，双主题都要过对比度 |
| 8 | 新建 `useMosaicZoom.js` | `useSpaceCamera.js` 已有 `zoomAt / centerOn / fitOverview / apply`，`K_MIN=0.16`、`K_MAX=2.2` | **直接复用**，删掉新建文件；只在 mosaic 侧定义 4 档 `k` 与世界尺寸 |
| 9 | 分组只映射"域" | 项目 `directory` 是 `domain/service/section` **三级**，且 section 极碎（linux 域就 174 节） | 相册「年 / 月 / 日」→ 域大胶囊 / service 小标签 / 详情面包屑；section 不画标签 |
| 10 | 只改 3 处 `KnowledgeSpaceView.vue` | `:780` 的 `aside` 会同时弹出右侧抽屉；`:546` Esc 会切回 space；`:536` `/` 与 `:540` `0` 误触旧相机；顶栏 `:596` stat 是 space 统计 | 裁决确认后集成改动扩到 **8 处**，完整 diff 见 `EXECUTION-PACK.md` §6.1 |
| 11 | 域清单"10 vs 7 历史缺口" | 登记域 = 数据域 = **10**，完全一致；测试还写死了登记顺序 | 不需要补齐域；`build-data.mjs` 的 `EXTRA_DOMAINS` 补齐逻辑已过期，**不要引用** |
| 12 | 首屏约 1000 格 | 737 条 ÷ 49 列 ≈ 15 行 | S0 档 **正好一屏放满 737 条**（约 435px 高），密度结论更精确 |

---

## 1. 需求裁决（不变，方向已由用户确认）

> **照片式排布 = 在一个正交二维平面上，用紧贴的规则网格把知识库全量条目密铺成一整块马赛克；每一格就是一条知识、就是一张"照片"；缩放改变格子大小与信息层级，点击任意格在原位弹出悬浮详情窗。**

| 用户说法 | 唯一解释 | 可验收判据 |
|---|---|---|
| "网状、很密集" | 连续规则网格，**格间隙 ≤ 2px**，域内无留白 | 首屏是一整块连续色块矩阵，不是几簇散落方块 |
| "每个就是一个模块，像一个照片一样" | 1 条知识 = 1 格 = 1 个正方形模块 | tile 数 === `searchKnowledgeEntries({}).length`，一一对应 |
| "可以放大、可以放小" | 缩放 = 格子边长 + LOD 内容变化，**不是 3D 相机推进** | 4 档；缩放前后同一格相对位置不变 |
| "有可观性" | 域色带 + 类型色条 + risk 角标 + 全域同屏形成整体图案 | S0 档 1440 视口首屏可见 ≥ 400 格 |
| "点进去也能看到详细的悬浮窗信息" | **悬浮详情浮层**，不跳页 / 不换路由 / 不推相机 | 点击后世界不动，邻居降饱和，浮层锚定该格 |

### 1.1 反模式黑名单（实现前逐条自检）

1. 不是 3D 空间场：禁 `perspective` / `rotateX/Y` / `translateZ` / yaw / pitch / `dist` / 三机位。
2. 不是现有 `field` 视图：它是 CSS 3D + 每域 6 列 + 域间距 1160px + ≤480/180 预算截断的散落卡片簇；`FieldPlane.vue` 注释自称"照片墙风格"但既不密铺也不全量同屏 —— **这正是被纠偏的对象**。
3. 不是 Bento / 大卡片 / 卡片列表 / treemap 分区：不要大小不一的格子、不要"街道"留白、不要 √n 切块。
4. 不是真照片：格子是**程序化视觉指纹**，禁位图 / 随机占位图 / 爬取图 / AI 生成图。
5. 不是右侧抽屉 / 整页详情：`FieldPlaneDrawer.vue` 是 `fpd-overlay` 全屏遮罩 + 右侧抽屉，只能参考字段渲染，**不能复用容器**。
6. 不是"照抄截图配色"：截图只参考几何与密度，配色走项目双主题令牌。
7. 不是"改 catalog 补字段"：`evidenceRefs` 等不存在就如实显示 `—`，禁止为了好看造字段。

---

## 2. 项目实参（v1.1 新增，全部 observed）

### 2.1 数据总览 —— `searchKnowledgeEntries({})`

| 指标 | 实测值 |
|---|---|
| 条目总数 | **737**（`id` 唯一 737，无重复） |
| 域数量 | **10**（登记域与数据域完全一致，无未登记域） |
| 登记顺序（测试写死） | linux, cloud-operations, docker, mysql, nginx, ubuntu, centos, network, web-lamp, linux-services |
| 域分布 | linux **225** · network **195** · web-lamp **104** · linux-services **88** · cloud-operations **73** · mysql **34** · nginx **14** · docker **2** · ubuntu **1** · centos **1** |
| 集中度 | 前 4 域 612 条 = **83%** → 密铺后天然形成大段色带，这就是"可观性"的来源 |
| `type` 取值 | **57 种**；Top: ENGINEERING KNOWLEDGE 218 / INCIDENT 77 / WRONG_ANSWER 50 / QUESTION 49 / **空 31** / RUNBOOK 19，其余为各知识包自定义长名 |
| `risk` | 737 条**全有**：READ_ONLY 376 / REFERENCE 144 / APPROVAL_REQUIRED 72 / HIGH 52 / MEDIUM 19 / 中文长句说明 29 |
| `title` | 737 全有，长度 4–77 字（均值 24） |
| `tags` / `platform` / `source` / `version` / `content` | 737 **全有** |
| `directory` | 737 全有：`{ domainId, serviceId, sectionId, pathKey }` |
| 缺失 | `summary` **188** · `relatedIds` **272** · `level` 701 · `verification` 605 · `category` 348 · `evidenceRefs` **737** |
| 恒值 / 占位符 | `reviewStatus` 恒 `UNVERIFIED` · `visibility` 恒 `BUILTIN` · `applicableVersion` 恒占位符「未注明适用组件版本」 |

服务/章节粒度：linux 13 服务 / 174 节；cloud-operations 27 服务 / 36 节；network 3 服务 / 71 节；docker·ubuntu·centos 各 1 服务。**section 太碎，不能做分组标签。**

### 2.2 取数入口（写死，避免实现模型 import 失败）

```js
// frontend/src/views/knowledge/space/mosaic/ 下的相对路径
import { searchKnowledgeEntries, knowledgeDomains } from '../../knowledgeCatalog.js'

const entries = searchKnowledgeEntries({})   // 737 条、每项含 directory；无 query 时不过滤不重排
const domains = knowledgeDomains             // 10 个，顺序即分组顺序
```

- ❌ `searchableKnowledgeEntries` **未导出**（`knowledgeCatalog.js:323`），不能 import。
- ❌ `knowledgeEntries` 虽导出，但**未经 `normalizeKnowledgeEntry`、无 `directory`**，不要用。
- ❌ 不新增导出、不改 catalog：`frontend/test/knowledge-catalog.test.mjs:22-33` 断言域顺序与"每个 domain 都已登记"，改了会红。
- 检索复用 `searchKnowledgeEntries(filters)`（支持 `query/service/platform/domain` 过滤，alias 与排序逻辑已内置），`FieldSearch.vue` 的 `select` 回调拿到条目后按 `id` 定位格子。

### 2.3 双主题令牌（`frontend/src/assets/styles/variables.css`）

`:root` = 深色（`color-scheme: dark`），`[data-theme='light']`（159 行起）= 浅色覆盖，**同名令牌两套值**。因此照片墙**禁止写死任何 hex**：

| 用途 | 令牌 |
|---|---|
| 舞台底 / 格子底 / 悬浮窗 | `var(--ds-surface-base)` / `var(--ds-surface-raised)` / `var(--ds-surface-overlay)` |
| 文字 / 次级文字 / 边框 | `var(--ds-color-text)` / `var(--ds-color-muted)` / `var(--ds-color-border)` |
| 强调 / 发丝线 / 阴影 | `var(--ds-color-primary)` / `var(--ds-hairline)` / `var(--ds-elevation-2)` |
| 类型与域色（T20 最多 5 色） | `var(--ds-chart-1..5)` + `var(--ds-chart-neutral)`，做格子底时 opacity 0.18–0.42 |
| 圆角 / 字阶 / 动效 | `var(--ds-radius-sm/md)` / `--ds-font-xs(12) · --ds-font-sm(13) · --ds-font-md(14)` / `var(--ds-duration-micro)` 150ms / `var(--ds-ease-out)` |

### 2.4 现状差距（读码确认）

| 维度 | `field` 场域（现默认） | `grid` 网格 | `space` 空间 | **照片墙** |
|---|---|---|---|---|
| 几何 | CSS 3D 透视 + yaw±35°/pitch 8–52° | 域分组横向卡 | 2D 缩放世界 3200×2000 | **正交 2D，零透视零旋转** |
| 密度 | 每域 6 列、域间距 1160px | 卡片列表，间隙大 | treemap + 街道留白 | **间隙 ≤2px，域间仅 1 条 hairline** |
| 同屏量 | ≤480 挂载 / ≤180 可见（截断 + warn） | 全量但松散 | 分区块 + LOD 裁剪 | **737 全量同屏**（靠缩小实现） |
| 缩放 | `dist` 520–2600 相机推进 | 无 | `k/tx/ty` + `zoomAt` | **格子边长 4 档 + LOD 语义切换** |
| 详情 | 相机聚焦 + 右侧抽屉 | 右侧 aside | 侧栏 | **锚定格子的悬浮窗，世界不动** |
| 文字 | 屏幕空间 DOM（沿用） | DOM | DOM | **DOM，可选中/可搜索/可读屏** |

---

## 3. 落地形态（不变）

- 新增第 5 个视图模式 **`mosaic`**，`KnowledgeSpaceView.vue` 加 pill + 分支；**现有 4 个视图代码一行不改**。
- 不新增路由 / 后端接口 / npm 依赖，不改 `catalogProjection` 白名单。
- **不需要 MASTER 新增 scoped exception**：完全落在 tool surface 基线内（零 WebGL / Canvas / 粒子 / blur / 位图）。
- **推荐 `viewMode` 默认改 `'mosaic'`**（D5 待确认）。省赛 11-18 截止仅 4 天，纯增量分支是唯一不炸回归的做法。

---

## 4. 视觉规格（按项目实参重写）

### 4.1 一格"照片" = 真实字段的四层配方

| 层 | 数据来源 | 缺失 / 异常降级 |
|---|---|---|
| ① 域色底 | `entry.directory.domainId` → `knowledgeDomains` 顺序映射 `--ds-chart-1..5` 循环（10 域 → 5 色 × 2 明度档） | 中性 `--ds-chart-neutral` |
| ② 类型色条（顶 2–3px） | `normalizeKnowledgeType(entry.type)` → 7 类 | 空值（31 条）→ 灰条 |
| ③ 中心短码 / 标题 | 短码取 7 类缩写（RB / INC / ENG / Q / WA / RULE / REF）；S2 起显示 `entry.title`（2 行截断，完整标题进 `aria-label` 与 tooltip） | 标题全有，无缺失 |
| ④ 右下 risk 角标 | `risk` 归一化：`READ_ONLY` / `REFERENCE` / `APPROVAL_REQUIRED` / `HIGH` / `MEDIUM` / `OTHER`（长句 29 条归入 OTHER，不显示长文） | 无（737 全有） |

**`mosaicType.js` 归一化规则（纯函数，可单测）** —— 只用于着色与短码，**不改写原值**：

| 上位类 | 匹配关键词（对 `type` 大写后 includes） | 短码 |
|---|---|---|
| RUNBOOK | `RUNBOOK` / `STANDARD` | RB |
| INCIDENT | `INCIDENT` / `PRODUCTION DIAGNOSIS` | INC |
| ENGINEERING | `KNOWLEDGE` / `ENGINEERING` / `OPERATIONS` / `MODULE` / `AUTOMATION` / `SPECIFICATION` / `GUIDE` / `PATH` / `工程知识卡` | ENG |
| QUESTION | `QUESTION` / `BANK` | Q |
| WRONG_ANSWER | `WRONG_ANSWER` / `WRONG` / `ANTI-PATTERN` | WA |
| RULE | `RULE` / `DECISION` / `POLICY` / `SAFETY` | RULE |
| REFERENCE | 其余 + 空值 | REF |

> 匹配优先级按表自上而下；`DIAGNOSIS RUNBOOK` 归 RUNBOOK（与 `knowledge-catalog.test.mjs` 里 `type === 'DIAGNOSIS RUNBOOK'` 的原始值互不干扰）。**详情窗必须显示原始 `entry.type`**，图例写明「色条为展示分类，非原始类型」。

### 4.2 尺寸档位与相机复用

基准 tile `BASE = 108px`，`GAP = 1px`，世界 `worldW = cols*(BASE+GAP)`、`worldH = rows*(BASE+GAP)`。复用 `useSpaceCamera.js`（`K_MIN=0.16` / `K_MAX=2.2`，正好覆盖）：

| 档 | `k` | 实际边长 | 1440 视口约列数 | 显示层 | 可点 |
|---|---|---|---|---|---|
| **S0 全景** | 0.26 | 28px | 49 列 | ① 域色底 + ② 类型色条（纯马赛克） | 否（只读，hover/focus 出 tooltip） |
| **S1 缩略** | 0.52 | 56px | 24 列 | + ③ 短码 + ④ risk 角标 | 是（≥44px） |
| **S2 标准** | 1.00 | 108px | 13 列 | + 标题 2 行 + tag[0] | 是（默认进入档） |
| **S3 细看** | 1.85 | 200px | 7 列 | + 摘要 2 行（缺则项目文案）+ 原始 type + 版本 | 是 |

**密度校验**：S0 时 1440/29 ≈ 49 列，737 条 → 15.1 行 × 29px ≈ **435px 高，一屏全放满**，与相册截图"一整块矩阵"一致。

**防掉帧**：tile 的 DOM 尺寸固定 `BASE`；缩放只对单一 `#mw-world` 写一次 `transform: translate3d(tx,ty,0) scale(k)`（`useSpaceCamera.apply` 已实现）。档位只改变容器上的 **`data-size="s0|s1|s2|s3"` 一个属性**，由 CSS 后代选择器控制各层显隐。
⚠️ `useSpaceCamera.apply()` 会同时写 `dataset.lod`（3 档 L0/L1/L2），**与照片墙 4 档语义不同**：mosaic 侧只用它的 transform 写入能力，`data-size` 由 mosaic 自己按 `k` 计算并写入，**不要复用它的 `lod` computed，也不要改写该文件**。

### 4.3 三级分组标签 = 相册的「年 / 月 / 日」

| 相册 | 项目 | 呈现 |
|---|---|---|
| 年份胶囊（2026年 / 2025年） | **域**（10 个） | 段首上方浮白色/raised 胶囊「域名 · n 条」，屏幕空间字号恒定（独立 overlay 层，不随 `scale` 缩小），点击跳域首格 + 切 S2 |
| 月份 | **service**（每域 1–27 个） | S2 起、且连续段 ≥4 格才显示次级小标签（避免刷屏） |
| 单张照片 | **section / entry** | section **不画标签**（linux 域就有 174 节）；只在详情窗显示 `directory.pathKey` 面包屑，tooltip 显示 service |
| 底部「照片 / 图集」 | 视图切换 pill | `照片墙 / 空间 / 场域 / 网格 / 列表` |

**小域折叠**：`docker(2) / ubuntu(1) / centos(1)` 各只有 1–2 格，单独配胶囊会挤成一团 → 合并成一枚「其他域 · 4 条」标签；**格子仍各占一格、颜色仍按各自域**，只是标签合并，不合并数据。
**排序键**：`knowledgeDomains` 顺序 → `directory.serviceId` → `directory.sectionId` → `id` 升序（与 `knowledgeTree` 分组逻辑一致，稳定可记忆）。**不要按 type 优先级排**（那是 treemap 的做法，会打散域色带）。

### 4.4 顶部 HUD / 缩放控件

顶栏：标题「知识库 / KNOWLEDGE WALL」+ 全量计数（运行时 `entries.length`）+ `Ctrl+K`（复用 `FieldSearch.vue`，emits `update:query / select / close`）+ 域筛选 chips（用 `searchKnowledgeEntries({ domain })` 的结果做高亮，不重排）。
缩放条：`− 滑块 +` + 「总览」（`cam.fitOverview(worldEl, stageEl, { w: worldW, h: worldH })`）；滚轮 `cam.zoomAt(mx, my, Math.exp(-deltaY*0.0015), worldEl)`，沿用项目现有灵敏度。
筛选默认**不重排**：非命中格降饱和 + 保留原位（位置记忆是照片墙核心资产），"紧凑重排"若提供必须显式开关。

### 4.5 悬浮详情窗（按真实字段重排）

| 项 | 规格 |
|---|---|
| 形态 | 锚定格子的浮层（stage 内 `absolute`，**非全屏遮罩、非右侧抽屉**），宽 420–480px，最大高 70vh 内部滚动，≤768 转底部 sheet |
| 外观 | `var(--ds-surface-overlay)` + `--ds-hairline` 1px + `var(--ds-elevation-2)` + `--ds-radius-md`；**零 backdrop-filter** |
| 字段 | 域 banner · `title` · **原始 `type` chip** · `platform` · `tags[]` · `directory.pathKey` 面包屑 · `source` · `version` · `risk`（真实分级）· `content` 按 `\n\n` 分段 · 关联知识（**仅 465 条有 `relatedIds` 时渲染**） |
| 如实降级 | `summary` 缺 188 条 → 沿用项目现有文案「当前资料暂未记录摘要。」；`applicableVersion` 占位符 → `—`；`level`/`verification`/`category` 大比例缺失 → 不渲染；`evidenceRefs` 不存在 → 该行**不出现**（P0 不显示"证据数"） |
| 核验状态 | 一行「未核验 · UNVERIFIED」如实陈述，**不做绿色已验证态**，也不做恒灰状态点 |
| 交互 | 世界不动 + 邻居降饱和约 30%（一次性 class）；`Esc` / 点外部 / 关闭按钮；焦点陷阱、打开聚焦标题、关闭回焦原格；`FieldPlaneDrawer.vue` 的 `navigate` emit 语义可对接关联跳转，**只换浮层内容 + 高亮目标格，不重排** |
| 动效 | 150ms 淡入 + 8px 位移（`--ds-duration-micro` / `--ds-ease-out`），reduced-motion 无补间 |

---

## 5. 交互状态机（不变）

```
S0 全景 ──滚轮上/捏合张开/滑块/+──> S1 ──> S2 ──> S3 ──「总览」──> S0 + 平移归零
任意可点档 ──点击 tile──> 悬浮详情窗（世界静止 + 邻居降饱和） ──Esc/外部点击──> 回原档原位原焦点
任意档 ──Ctrl+K──> 搜索浮层；命中 → 按 id 高亮 + 自动切 S2 + centerOn 到视口中心（不重排）
任意档 ──点域标签──> 平移到域首格 + 切 S2
详情窗 ──关联知识──> 换内容 + 高亮目标格（位置不变）
```

- 缩放锚点以指针为不动点（复用 `zoomAt`）；拖拽只改 `tx/ty`，**禁旋转**。
- 375：默认 S2（≥44px 命中）；S0 只读、点击自动放大到 S2；双指捏合；隐藏非必要 HUD。
- 键盘：方向键在网格内按行列移动、`Enter` 开详情、`Esc` 关闭、`Ctrl+K` 搜索；S0 档 tile `aria-hidden="true"` + `tabindex="-1"`。

---

## 6. 技术架构（v1.1 收敛）

### 6.1 新增文件（`frontend/src/views/knowledge/space/mosaic/`，选择器统一 `.mw-*`）

| 文件 | 职责 |
|---|---|
| `MosaicWallView.vue` | 容器：stage / `#mw-world` / HUD / 事件；**复用** `useSpaceCamera` 与 `FieldSearch` |
| `MosaicTile.vue` | 单格四层配方，纯 props（`entry / size / hit / selected`），无内部响应式状态 |
| `MosaicDetailPopover.vue` | 悬浮详情窗（焦点陷阱 / Esc / 关联跳转 emit） |
| `MosaicDomainTag.vue` | 域胶囊 + service 小标签（屏幕空间，不随 scale 缩小） |
| `mosaicLayout.js` | **纯函数**：稳定排序 → 三级分段 → 网格坐标 → `k→size` 映射，确定性可单测 |
| `mosaicType.js` | **纯函数**：57 种 type → 7 上位类 + 短码；risk → 6 档短码；占位符识别 |
| `mosaic.css` | 密铺样式；所有选择器限定 `.mw-*`，只用 `--ds-*` 令牌 |

**已删除**：v1.0 计划新建的 `useMosaicZoom.js` —— `useSpaceCamera.js` 已提供 `zoomAt / centerOn / fitOverview / apply`，不重复造轮子。

### 6.2 最小改动点（`KnowledgeSpaceView.vue`，精确到行）

| 行 | 改动 |
|---|---|
| 17 | `const viewMode = ref('field')` → `ref('mosaic')`（D5 确认后） |
| 607–610 | pill 区新增 `<button class="ks-pill" ... @click="onViewModeChange('mosaic')">照片墙</button>`；其余 4 枚不动 |
| 741 附近 | 在 `<SpaceFieldView v-else-if="viewMode === 'field'" />` 前插入 `<MosaicWallView v-else-if="viewMode === 'mosaic'" />` 并 import |
| **780** | `<aside v-if="selectedCard && viewMode !== 'space'">` → 追加 `&& viewMode !== 'mosaic'`。**漏掉这处，mosaic 点格子会同时弹出右侧抽屉，与悬浮窗打架** |

**裁决确认后新增 4 处（共 8 处，完整 diff 见 `EXECUTION-PACK.md` §6.1）**：
- `:10` 追加 `import MosaicWallView`（原计入 741 分支，现单列）。
- `:516` `onKeyDown` 函数体首行加 `if (viewMode.value === 'mosaic') return` —— 否则 Esc 切回 space、`/` 聚焦旧搜索框、`0` 调用旧相机 `fitOverview` + `renderHUD()`。
- `:601` 顶栏 `<label class="ks-search">` 加 `v-if="viewMode !== 'mosaic'"`，避免两个搜索框（照片墙用 Ctrl+K）。
- `:596` `ks-stat` 加 `v-if="viewMode !== 'mosaic'"` + `v-else` 简化条；旧 stat 是 space 视图统计，在 mosaic 下会显示误导数字。

其余逻辑（方向键、Esc、`cam.zoomAt`、迷你地图、grid/list 分支）**完全不动**；`onKeyDown` 的 early return 让照片墙自管键盘，现有 4 视图键盘行为零变化。`onMounted` 的 `if (viewMode === 'space')` 在 mosaic 默认下不执行是正确行为（field 模式同样跳过），不要改。

### 6.3 既有代码 / 测试契约冲突清单（v1.1 新增）

| 对象 | 契约 | 对 mosaic 的约束 |
|---|---|---|
| `knowledge-catalog.test.mjs:22-33` | 断言 `knowledgeDomains` 10 个域的**顺序**、每个 `entry.domain` 已登记 | 不改 catalog、不新增域、排序以登记顺序为准 |
| `space-layout.test.mjs` / `field-layout.test.mjs` / `binding-index.test.mjs` | 只测各自纯函数，不与 `KnowledgeSpaceView.vue` 静态绑定 | 新增分支不会打破它们，但 T27 仍需复跑 |
| 全 `frontend/test` 检索 `viewMode` / `ks-pill` / `knowledge/space` | **无**静态断言绑死 pill 数量或默认视图（不同于侧栏那次踩坑） | 改默认视图不会直接致红，但仍需浏览器实测 |
| `KnowledgeSpaceView.vue:516` 全局 `onKeyDown`（window 监听，583 行挂载） | `:546` Esc 会把 `viewMode !== 'space'` 切回 space；`:536` `/` 聚焦 `#ks-query`；`:540` `0` 调旧相机 | **必须**在 `onKeyDown` 首行 `if (viewMode.value === 'mosaic') return`，照片墙自管键盘 |
| `KnowledgeSpaceView.vue:596-605` 顶栏 stat 与搜索框 | stat 是 space 的 LOD/挂载卡统计；搜索框走 `hitIds`（space 命中集） | mosaic 下条件隐藏 + `v-else` 简化条；照片墙用 `FieldSearch.vue` 的 Ctrl+K |
| `useSpaceCamera.js` | `apply()` 写 `dataset.lod`（3 档） | mosaic 用 `data-size`（4 档），两套属性并存，不互相覆盖 |
| `FieldPlaneDrawer.vue` | `fpd-overlay` 全屏遮罩 + 右侧抽屉 | 只参考字段渲染，容器必须重写 |
| `frontend/src/visual/motionScheduler.js` | 共享 30fps / 慢帧 15fps / reduced-motion 单帧 | 需要 rAF 时订阅它，**不新建循环** |
| 工作区状态 | 当前约 16 个未提交文件（知识空间大改 + 侧栏半成品迁移） | 实现模型**不要覆盖他人改动**，只新增 `mosaic/` 与上述 4 处 |

### 6.4 渲染与性能

- **737 个 tile 全量 DOM 挂载**（与场域 ≤480 截断相反，这是"全量同屏"硬要求）：每格 `contain: layout paint style size` + `content-visibility: auto`（显式尺寸）；文字全部屏幕空间 DOM。
- `will-change: transform` **只给 `#mw-world` 一层**；缩放批量写一次 transform，**禁止逐帧 Vue setState / 逐格计算响应式**。
- 零 Canvas / WebGL / SVG 关系线 / 粒子 / 位图 / `backdrop-filter`；零新增依赖与接口。
- 布局结果按输入数组缓存；缩放、筛选、开详情**都不重算坐标**，只有数据本身变化才重算。

### 6.5 布局纯函数（确定性可单测）

```
输入：searchKnowledgeEntries({}) → 737 条；knowledgeDomains → 10 域
① 排序：domain（登记顺序）→ serviceId → sectionId → id      // 稳定，会话内不变
② 分段：连续同 domain 为一段（段首 domainTag）；段内连续同 serviceId 为子段（≥4 格才出小标签）
③ 网格：cols = floor((stageW + GAP) / (BASE + GAP))；index → (col = i % cols, row = floor(i / cols))
④ 域边界：不插空行，只在段首上方叠浮标签 + 左侧 1px hairline
⑤ 输出：{ tiles:[{id, entry, col, row, x, y, domainTag?, serviceTag?}], cols, rows, worldW, worldH, segments }
⑥ 小域折叠：domain.n ≤ 2 的相邻段共用一枚「其他域 · n 条」标签（数据不合并）
```

---

## 7. 工作包（交实现模型，按序执行）

| 包 | 输入 | 改动 | 禁止 | 验收 |
|---|---|---|---|---|
| **T23 数据与归一化纯函数** | `knowledgeCatalog.js` | `mosaicLayout.js` + `mosaicType.js` + `frontend/test/mosaic-layout.test.mjs` / `mosaic-type.test.mjs` | 不改 catalog、不硬编码 737/10/7、不改写原 type | tile 数 === `searchKnowledgeEntries({}).length`；id 唯一；57 种 type 全覆盖且映射到 7 类；10 段 + 小域折叠；占位符识别；缩放不改坐标 |
| **T24 密铺骨架** | T23 | `MosaicWallView.vue` / `MosaicTile.vue` / `MosaicDomainTag.vue` / `mosaic.css` | 禁 3D、位图、blur、大圆角、区块留白、**禁写死 hex** | 4 档尺寸；间隙 ≤2px；域胶囊 + service 小标签；深浅双主题；1440 首屏 ≥400 格 |
| **T25 缩放平移** | T24 + `useSpaceCamera.js` | 仅 mosaic 侧 `k→size` 映射 + 事件绑定 | 禁新建 camera 文件、禁改 `useSpaceCamera.js`、禁逐帧 setState、禁旋转 | 锚点不跑位；4 档无跳位；`fitOverview` 自定义世界尺寸；pinch；reduced-motion 静态；375 可点格 ≥44px |
| **T26 悬浮详情窗** | T24 + `FieldPlaneDrawer` 字段参考 | `MosaicDetailPopover.vue` | 禁推相机、禁整页跳转、禁右侧抽屉、禁 backdrop-filter、**禁显示不存在的 evidenceRefs** | 字段与 catalog 一致；原始 type 显示；占位符/缺失如实降级；Esc/外部关闭；焦点回位与陷阱；关联跳转不重排 |
| **T27 集成与门禁** | T23–T26 | `KnowledgeSpaceView.vue` **8 处**改动（见执行包 §6.1）+ 浏览器测试 + 基线复跑 + 演示口播同步 | 禁改现有 4 视图逻辑、禁改 `catalogProjection` 白名单、禁覆盖他人未提交改动 | 见 §8 |

**范围**：P0（11-18 前必须）= T23 + T24 + T25 三档 + T26 核心 + T27；P1 = 连续无级缩放 / pinch / 方向键 / 关联跳转 / 搜索命中自动定位 / 证据绑定派生；P2（不进省赛）= 视口虚拟化深度调优。

---

## 8. 验收门禁（v1.1 增补）

**功能与数据真实性**
1. tile 数 === `searchKnowledgeEntries({}).length`（737，运行时取）；域标签数按折叠规则为 8 枚（7 个独立域 + 1 枚「其他域」），控制台无预算截断 warn。
2. 57 种 `type` 全部映射到 7 类且**详情窗显示原始 type**；31 条空 type 走灰条 `REF`；`risk` 6 档角标覆盖率 100%。
3. 无 `evidenceRefs` 假设：详情窗不出现"证据数"字样（P0）；`applicableVersion` 占位符显示为 `—`；`summary` 缺失 188 条显示项目文案，不出现正文冒充摘要。
4. S0 档 1440×900 首屏 ≥400 格、间隙 ≤2px、域内无整格留白；缩放 4 档可用，锚点下 tile id 前后一致，档位切换逻辑坐标误差 ≤1px。
5. 点击可点档 tile → 浮层出现、世界 transform 不变、路由不变、**右侧 `ks-side--alt` 不出现**；Esc 关闭并回焦；关联跳转不重排。

**工程（沿用 T11 基线）**
6. `typecheck` 0 error / `lint` 0 error（warn 不新增）/ 双端构建 / **现有 503 测试 0 失败** / 新增单测与浏览器测试全绿 / Lighthouse 不低于桌面 92、移动 95。
7. 零 `backdrop-filter` / WebGL / Canvas / bitmap / 新增依赖 / 新增后端接口；`catalogProjection` 白名单 diff 为空；现有 4 视图测试全绿。
8. **深色 `:root` 与 `[data-theme='light']` 两套主题**都过对比度 ≥4.5:1 与视觉走查（v1.1 新增）。

**可访问性**
9. 375 / 768 / 1024 / 1440 / 1920 无溢出；375 可点 tile 命中 ≥44px；全键盘可达（Tab / 方向键 / Enter / Esc / Ctrl+K）；focus visible；`aria-label` 含域·类型·标题；S0 档 `aria-hidden="true"` 且不进 Tab 序；reduced-motion 无补间。

**证据纪律**
10. 性能结论必须给 before/after + 测量口径（`perf:baseline` 或等价脚本 + DevTools 帧时间），无实测数字视为未验收。
11. 全文无「准确率 9X%」「AI 识别指令风险」；`reviewStatus` 恒 `UNVERIFIED` 不得渲染成"已验证"；所有色条/角标来自真实字段，无虚构证据、风险或版本。

---

## 9. 风险与对抗

| 风险 | 对抗 |
|---|---|
| 实现模型又做成 3D 场域（本次纠偏对象） | §1.1 黑名单 + T24 逐条查 `perspective/rotate/translateZ/dist`，出现即打回 |
| `import { searchableKnowledgeEntries }` 直接报错 | §2.2 写死唯一取数入口 `searchKnowledgeEntries({})` + T23 单测 |
| 沿用场域 480/180 截断导致墙上有洞 | T23 断言 tile 数 === 运行时 length；T27 控制台零 warn |
| 套用 8 色 `TYPE_COLORS` → 大半墙灰 | `mosaicType.js` 覆盖 57 种 + 单测断言 100% 覆盖 |
| 拿 `content` 补 `summary`、把占位符当版本 | §4.5 降级表 + T26 断言 |
| 写死深色 hex → light 主题不可用 | §2.3 全令牌化 + T24/T27 双主题走查 |
| 漏改 `:780` → 抽屉与悬浮窗同时弹 | 执行包 §6.1 第 8 处 + T27 浏览器断言 `ks-side--alt` 不存在 |
| 默认改 mosaic 后 `:546` Esc 切回 space / `:536` `/` / `:540` `0` 误触旧相机 | 执行包 §6.1 第 3 处 `onKeyDown` 首行 early return；T27 实测四键不切视图、不报错 |
| 顶栏 `ks-stat` 显示 space 的「0 卡 · L0」误导数字 | 执行包 §6.1 第 5 处条件渲染 + `v-else` 简化条 |
| 737 DOM 掉帧 | 单容器 transform + 容器级 `data-size` + `contain`/`content-visibility` + 共享 motionScheduler |
| 44px 命中区与密集小格冲突 | 375 默认 S2；S0 只读、点击自动放大到 S2 |
| 覆盖他人未提交改动 / 省赛时间窗 | 只新增 `mosaic/` + 4 处改动；P0/P1/P2 分级 |

---

## 10. 裁决结果（2026-11-14 22:00 用户「确认」，不再讨论）

| 编号 | 议题 | **结论** |
|---|---|---|
| D5 | 照片墙是否设为 `/knowledge/space` 默认视图 | **是**，`viewMode` 默认 `'mosaic'`，场域保留为 pill |
| D6 | 悬浮窗是否可拖 / 多开 | **否**，单实例、不可拖、锚定格子 |
| D7 | 首页 Bento 是否同步换成照片墙 | **否**，保持 D1 裁决，首页零改动 |
| D8 | 筛选是否提供"紧凑重排"开关 | **P1 才做**；P0 只做降饱和 + 保留原位 |
| D9 | 域排序按登记顺序还是条目数降序 | **登记顺序**（与 `knowledgeTree` 一致、测试写死） |

**D5 生效后牵出的额外改动**：全局 `onKeyDown`、顶栏搜索框、顶栏统计条共 3 处（详见 §6.2 补充与执行包 §6.1），集成改动由 4 处变为 **8 处**。

---

## 11. 交付物索引

- **本文件 v1.1 = 方案唯一口径**（v1.0 已被本版覆盖）；**`EXECUTION-PACK.md` = 执行唯一指令**（T23–T27 逐包、8 处精确 diff、12 条门禁、复跑命令）。
- 实测可复现命令：`node --input-type=module -e "const m = await import('file:///D:/SmartOpsAgent/frontend/src/views/knowledge/knowledgeCatalog.js'); console.log(m.searchKnowledgeEntries({}).length)"` → 737。
- 姊妹文档（保留但**不再是本需求的定义**）：`docs/design/spatial-knowledge-field/DESIGN.md`、`INTERACTION-GUIDE.md`、`docs/design/knowledge-spatial-ia-v1/DESIGN.md`；其中「登记 7 域 / 补齐 3 域」与 `build-data.mjs` 的 `EXTRA_DOMAINS` **已过期**，不要引用。
- 规范基线：`design-system/MASTER.md`、`frontend/src/assets/styles/variables.css`。
- 代码落点：`frontend/src/views/knowledge/space/KnowledgeSpaceView.vue`（4 处）+ 新建 `mosaic/`。
- 执行包：本轮只确立并校准方案，T23–T27 逐包执行指令由下一轮生成。
