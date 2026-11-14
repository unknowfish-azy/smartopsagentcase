# 逆向报告：Expo Mode 的「立体信息架构」

> 结论先行：**它不是 Three.js 场景，而是一张"能缩放的地图"——卡片是真正的 HTML，由浏览器自己画进 `<canvas>`。**
> 我们复刻的是这套方法（分区布局 + 三段相机 + 缩放即导航 + 真 DOM 卡片），不是 Shopify 的视觉资产。

| 项 | 内容 |
| --- | --- |
| 原始出处 | Shopify CEO Tobi（Tobias Lütke）在 X 上发布 · 经小红书笔记转述（note `6ae499880000000025013203`） |
| 作品名 | **Expo Mode** |
| 做了什么 | 把整个 Shopify 平台铺成一张三维地图：商品 / 营销 / 履约 / Agentic / 开发者按功能分区，卡片之间用连线表达关系；镜头先俯瞰全貌，再钻进某个分区看细节，**缩放就是导航** |
| 技术底 | **HTML-in-Canvas API**（Google / WICG 提案）：画布上的卡片不是截图，是真实 HTML 界面由浏览器引擎直接渲染进 Canvas |
| 公开代码 | **没有**。这不是开源仓库，也没有可抓的 bundle 说明它是产品内 / 演示页。所以本报告是"按公开规范还原技术路线"，不是"复制它的源码" |

---

## 1. 为什么不能"爬源码"，以及我们爬到了什么

小红书笔记是**二手转述**，原始演示在 Tobi 的推文里，没有公开仓库、没有可引用的源文件。硬去扒一个没见过地址的站点，只能是猜。

但技术底是**公开规范**，可以精确还原——这正是复刻的关键：Expo Mode 的"酷"不来自私有魔法，而来自一条当时刚可用的浏览器新能力。

所以我们把逆向拆成两层：

| 层 | 能不能拿到 | 我们怎么做 |
| --- | --- | --- |
| **交互与视觉模型** | 能从笔记描述 + 公开讨论复原 | 分区布局、三段镜头、缩放即导航、连线表达关系——见 §3 |
| **渲染技术路线** | 公开规范可查 | HTML-in-Canvas 的三个原语——见 §2 |

---

## 2. 技术底：HTML-in-Canvas 到底是什么

来源：[html-in-canvas.dev 规范概览](https://html-in-canvas.dev/docs/overview/)、[Chrome for Developers · HTML-in-Canvas 概念](https://developer.chrome.com/docs/web-platform/html-in-canvas/concepts)、[WICG/html-in-canvas](https://github.com/WICG/html-in-canvas)

### 2.1 支持现状（决定我们能不能用）

| 环境 | 状态 |
| --- | --- |
| Chrome **157+** | 默认开启 |
| Chromium 147–156 / Brave Stable（≥1.89.132） | 需开 flag `chrome://flags/#canvas-draw-element` |
| Firefox / Safari | **不支持** |

命名差异：Chrome 157+ 用 `<canvas content="drawable">` + 子元素加 `drawable` 属性；Chromium ≤156 用 `layoutsubtree`。两个构建各自忽略不认识的属性，所以同一份代码可以两个都写上。

### 2.2 三个原语（整个 API 就这些）

```html
<canvas id="c" layoutsubtree content="drawable">
  <div id="card" drawable>卡片是真的 DOM</div>
</canvas>
<script>
const ctx = c.getContext('2d')
c.onpaint = () => {
  ctx.reset()
  const t = ctx.drawElementImage(card, 0, 0)   // 把子元素画进画布，返回变换
  card.style.transform = t.toString()          // 让 DOM 与像素保持同步
}
</script>
```

1. **`layoutsubtree` / `content="drawable"`**：让 canvas 的子元素参与布局（否则它们不参与排版，也就没有"真实布局"可画）。
2. **`ctx.drawElementImage(el, x, y)`**：由浏览器引擎把元素画进画布，返回一个 `transform`。
3. **`paint` 事件**：浏览器告诉你什么时候该重画；每帧可重画。

配套还有 `drawElement` 之类的重载与 `canvas` 上的 `requestPaint()`；IDL 见规范 [API Reference](https://html-in-canvas.dev/docs/api/)。

### 2.3 它解决了什么（这也是它"看起来很贵"的原因）

| 老问题 | html2canvas 类方案 | HTML-in-Canvas |
| --- | --- | --- |
| 无障碍 | 画布内容对读屏是黑盒 | 由浏览器渲染，**语义仍在** |
| 国际化 | `fillText` 搞不定 RTL / 竖排 / 复杂脚本 | 用引擎自己的排版 |
| 性能 | 每次截图都昂贵且不完整 | 原生绘制，可每帧重画 |
| 质量 | 字体、连字、次像素渲染对不齐 | 与页面上的文字完全一致 |

**这就是 Expo Mode 敢于"把真界面当贴图"的底气**：卡片上的文字仍然可以被选中、被读屏、被 Ctrl+F 找到。

---

## 3. 交互与视觉模型（从描述复原）

| 要素 | 做法 | 为什么重要 |
| --- | --- | --- |
| **主视图** | 一张平面地图，不是列表、不是 3D 场景 | 信息架构变成了**空间关系**，一眼看出谁和谁近 |
| **分区** | 按功能聚成若干展区，展区之间留白 | 用面积和距离表达"这块有多重" |
| **卡片** | 每个功能区一张卡，卡内是真实界面 | 缩进去就能看到真东西，不用跳页 |
| **连线** | 卡片之间画线表达依赖/关系 | 关系是 IA 里最贵的信息，列表表达不了 |
| **相机** | 三段：俯瞰全貌 → 钻进分区 → 读卡片 | **缩放就是导航**，没有面包屑、没有侧边栏 |
| **视野控制** | 顶部检索/筛选 | 737 张卡不可能靠眼睛找 |

---

## 4. 复刻边界

| 可复刻（方法） | 不复刻（资产） |
| --- | --- |
| 分区 + 留白 + 面积表达权重 | Shopify 的品牌色、字体、图标 |
| 三段相机与锚点缩放 | Expo Mode 的具体文案与版式 |
| 连线表达关系 | 他们的产品截图 |
| HTML 卡片进画布的渲染路线 | 他们的源码（本来也拿不到） |

---

## 5. 对本项目的结论（关键决策）

我们要落的是**知识库**（737 条、10 个 domain 取值），不是营销演示页。技术路线要按项目约束重选：

| 方案 | 可行性 | 结论 |
| --- | --- | --- |
| **A. HTML-in-Canvas**（原版路线） | Chrome 157+ 才有，Firefox/Safari 不支持，需要 flag | **只作演示页增强**，必须特性检测 + 降级 |
| **B. CSS 3D 平面分层**（`perspective` + `translate3d`） | 全浏览器可用，卡片是真 DOM，零新依赖 | ✅ **控制台主路线** |
| **C. three.js + 卡片纹理** | 已有 `three@^0.186` | ❌ **不选**：卡片变成纹理就等于截图，丢掉可选中文本、读屏、Ctrl+F——恰好丢掉了 A 方案存在的理由 |

为什么 B 就够：

1. 我们要的是"俯视地图 + 钻进分区"的**镜头语言**，不是真 3D 光照与遮挡。CSS 3D 的 `perspective` + `scale` 完全够表达。
2. 卡片必须保持真实 DOM（文字可选中、可读屏、可搜索、可被测试断言）。
3. `MASTER.md` 写明工具层**零 WebGL**；B 不违反，A 也只是可选增强。
4. 组合层只有 `transform` / `opacity`，走合成器，不触发布局与重绘。

详细设计见 [DESIGN.md](DESIGN.md)，实现提示词见 [PROMPT.md](PROMPT.md)。
