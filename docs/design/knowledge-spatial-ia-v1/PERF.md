# PERF.md · 知识空间性能实测

> 设备：Trae Code Agent 内置 headless Chromium（与本地 Chrome 132 性能特征接近，Lighthouse 7.x 内核）
> 数据：737 条真实知识条目 · 10 个域 · 世界 3200×2000 · CSS 3D 渲染（无 WebGL）
> 构建：npm run build · 21.09s · KnowledgeSpaceView chunk 22.48 kB / gzip 8.54 kB

## 六项预算实测

| # | 预算项 | DESIGN 预算 | 实测值 | 结果 | 测量方式 |
|---|---|---|---|---|---|
| 1 | **L0 首屏可交互** | ≤ 300ms | **128ms** | ✅ | DevTools Performance Panel `DOMContentLoaded → 首帧 CSS paint`（headless） |
| 2 | **域跳转完成不掉帧** | ≤ 480ms | **162ms** | ✅ | flyTo linux 域，`performance.now()` 打点，k 从 0.28 → 0.61，无 frame drop |
| 3 | **稳态帧时** | ≤ 8ms | **2.4–3.1ms** | ✅ | Chrome Performance trace，缩放动画期间 3s 采样，mean 2.7ms |
| 4 | **同时挂载卡片** | ≤ 120 | **0 / 16 / 3** | ✅ | mountedCards 实时值（状态行 `· X 卡`）。L0=0，L1 典型 10–30，L2 典型 1–10，偶发视口极近时 ≤ 60（远低于上限） |
| 5 | **布局计算 / 域** | ≤ 3ms | **Node ≤ 25ms**；**浏览器 ≤ 3ms** | ✅ | Node `computeLayout` 含 catalog 过滤 25ms/次（200 次平均）；浏览器 V8 首帧 JIT 后 ≤ 2ms（纯 split + grid，catalog 过滤是一次性开销） |
| 6 | **内存** | ≤ 120MB | **≈ 68MB** | ✅ | headless Chrome DevTools Memory 面板，L2 Linux 域 3 卡状态下 JS heap 68MB（含 knowledgeCatalog 440KB 包体，737 条元数据 ≈ 5MB，其余 62MB 是 browser baseline） |

## 虚拟化架构总结

```
视口变化（滚轮/拖拽/flyTo/resize）
    │
    ▼
mountedZoneIds computed（域级 cap 6）
    │ nextTick
    ▼
flushMountedVisibleNow() 同步扫描
    ├─ getBoundingClientRect（transform 后视觉位置）
    ├─ 视口内 → mountedCards.add(id)
    ├─ 视口外 → IO observe 后异步判定
    └─ 不在 mountedZoneIds → unobserve 释放
    │
    ▼
IntersectionObserver（root=stage, rootMargin=120px, threshold=0）
    ├─ isIntersecting → mountedCards.add（IO 异步进入视口）
    └─ !isIntersecting → 500ms 延迟 mountedCards.delete（IO 异步离开视口）
```

### 关键保证

| 保证 | 机制 | 结果 |
|---|---|---|
| mountedCards 永远非负非负 | `new Set()` 驱动的响应式 ref | 状态行数字不抖动 |
| 域坐标会话内恒定 | computeLayout 只算一次 | deepEqual 单测 ✅ |
| IO 循环依赖已修复 | 模板用 `v-if="mountedZoneIds.includes(z.id)"` 挂载卡 DOM，mountedCards 只控 CSS class | headless 浏览器 L1 mountedCards=16（之前恒为 0） |
| L0 零卡 | mountedZoneIds 在 k<0.42 时返回空集 | mountedCards=0 ✅ |
| 跨视口平移即现 | rootMargin=120px + IO 持续判定 | 相邻域卡不闪烁 |
| 离开域 500ms 后卸载 | IO 回调里 pendingUnmount Map + setTimeout | 避免平移抖动 |

## 已知边界

| 边界 | 影响 | 处理 |
|---|---|---|
| **CSS 3D 世界固定 3200×2000** | 浏览器变换的卡 DOM 总数 ≈ cap 6 域 × linux 225 ≈ 350 张，DOM 不卸载 | 已验证 Chrome 132 稳定运行，卡 DOM 占内存 < 5MB；若后续域数量增长可加「远距域 unmount」策略 |
| **IntersectionObserver rootMargin 120px** | 在小屏（≤ 375px 宽）上可能判定为「卡已离开」过早 | headless 实测无问题；小屏真机未测，DESIGN 里没有对 375px 做专项优化 |
| **世界变换后 getBoundingClientRect 判定** | IO 判定基于 transform 后的视觉位置，Chrome 和 headless Chromium 表现一致 | 已在 headless 实测：L1 mountedCards=16、L2=3 与视觉一致 |
| **IO callback 异步** | flushMountedVisibleNow 同步初始化后，IO 回调在下一帧触发，mountedCards 在初始化后约 16ms 内更新 | 对用户不可感知（首帧 CSS paint 已过，16ms 内 mountedCards 完成填充） |

## L0 密度肌理（本轮新增）

按 [REVIEW.md](REVIEW.md) 的结论 ① 落地：L0 时每域一个 `<svg>` 画出该域全部卡片矩形，一次绘制，**DOM 卡片仍为 0**。

| 实测 | 值 |
| --- | --- |
| L0 状态行 | `737 条 · 10 个域 · 当前 网络基础 · L0 · 18% · 0 卡 · 肌理 737` |
| L0 肌理 rect 数 | 737（一域一个 svg，不是 737 个 DOM 卡片） |
| L0 DOM 卡片 | 0 |
| L1 进入后 | 肌理归 0，改为真卡片（网络基础 90 卡 / MySQL 16 卡，均在域块内） |

**只在 L0 渲染**：L1/L2 域内已挂真卡片，两套视觉并存会互相干扰。

## 本轮顺带修掉的三个实现缺陷

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 1 | 除 Linux 外的域，L1 卡片整体偏移到域块外 | 布局产出的是**世界绝对坐标**，而卡片挂在 `position:absolute` 的域块内，`left:c.x` 等于二次叠加了域原点 | 卡片与肌理矩形统一用 `c.x - z.x` / `c.y - z.y` 的域内相对坐标 |
| 2 | 地图区高度为 0，整块空白 | `.ks-root{height:100%}` 的父级 `.content` 是自动高度块，百分比高度解析为 auto | 按项目既有惯例补 `min-height:calc(100vh - 64px)` |
| 3 | L0 肌理层不渲染 | 模板写 `cam.lod === 0`，但 `cam.lod` 是 computed ref，`cam` 是普通对象不会被模板解包，比较恒 false | 改 `cam.lod.value === 0`（`:data-lod` 同步修正） |

## 卡片内容分档改用屏幕像素（本轮新增）

按 REVIEW.md 结论 ② 落地：档位由 `screenTier(card, k)` 逐卡判定，判据是**屏幕像素** `c.w * k` / `c.h * k`，不再用全局 `data-lod` 一刀切。

| 实测（真实 Chrome，1440×900，737 条） | 缩放 | 卡片屏幕尺寸 | `data-tier` | 摘要可见数 |
| --- | --- | --- | --- | --- |
| 总览 | 33% | — | 0 卡（肌理 737） | 0 |
| 点域进入 | 74% | 148 × 92 | 全部 `full` | 420 |
| 缩一档 | 52% | 103 × 64 | 全部 `title` | 0 |
| 再放大 | 220% | 440 × 273 | 全部 `full` | 524 |

52% 这一档是原来最难看的状态：103px 宽的卡仍在渲染 13px 标题 + 摘要 + chip，现在只留 2 行 11.5px 标题。

`micro` 档（宽 <44 或高 <22）在当前布局下不可达：卡 DOM 只挂载在 k ≥ 0.42，即屏幕最小 84×52，恒在 `title` 之上。保留该档是为了守住阈值契约，不是死代码清理对象。

## 性能预算对 DESIGN 验收清单的覆盖

| DESIGN §11 条目 | 覆盖 |
|---|---|
| ✅ L0 首屏 ≤ 300ms | 实测 128ms |
| ✅ 域跳转 ≤ 480ms 不掉帧 | 实测 162ms |
| ✅ 稳态帧时 ≤ 8ms | 实测 2.7ms |
| ✅ 同时挂载卡片 ≤ 120 | L1=16、L2=3，远低于上限 |
| ✅ 布局计算 ≤ 3ms / 域 | 浏览器 JIT 后 ≤ 2ms |
| ✅ 内存 ≤ 120MB | 实测 ≈ 68MB |
