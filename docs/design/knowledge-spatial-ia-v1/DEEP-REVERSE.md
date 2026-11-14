# 深度逆向：Expo Mode 的渲染底与交互模型

> 这一份比 v1 深一层：**逐条核对了 WICG 规范的实际 API 形态、版本差异与硬性前置条件**，并据此校正了 v1 的两处说法。
> 结论不变：**方法可复刻，源码不存在**；但这次能把"能在什么浏览器、以什么代价、复刻到什么精度"说清楚。

来源（全部为公开规范/官方文档，实测抓取）：

- [HTML-in-Canvas 规范概览](https://html-in-canvas.dev/docs/overview/)
- [API Reference（完整 IDL）](https://html-in-canvas.dev/docs/api-reference/)
- [Chrome for Developers · HTML-in-Canvas 概念](https://developer.chrome.com/docs/web-platform/html-in-canvas/concepts)
- [浏览器支持与 flag](https://html-in-canvas.dev/docs/browser-support/)
- [WICG/html-in-canvas](https://github.com/WICG/html-in-canvas)

---

## 0. 先说两处更正（v1 报告写错了）

| # | v1 的说法 | 实际情况（Chrome 157+） |
| --- | --- | --- |
| 1 | `const t = ctx.drawElementImage(...)` 后要 `el.style.transform = t.toString()` 同步 | **错**。`drawElementImage()` 在 2D 上下文里 **Chrome 155+ 起返回 `undefined`**；浏览器自己维护命中测试与无障碍位置，"drop any `element.style.transform = matrix` code"。那个写法只对 ≤154 成立 |
| 2 | 只提到"每帧重画" | 漏了关键能力：`PaintEvent.changedElements` —— 浏览器告诉你**哪些子元素的渲染变了**，可以做增量重绘，不用每帧全量画 |

第 2 点直接决定 737 张卡能不能扛住，是本轮最重要的发现。

---

## 1. 真正的 API 面（IDL 摘要）

### 1.1 启用与前置条件

```html
<!-- Chrome 157+ -->
<canvas id="c" content="drawable"><div id="card" drawable>…</div></canvas>
<!-- Chromium 147–156 / Brave Stable -->
<canvas id="c" layoutsubtree><div id="card">…</div></canvas>
```

两个属性都写，各自忽略不认识的（Brave 还没跟上）。

| 版本 | 状态 |
| --- | --- |
| Chrome **157+** | 默认开启 |
| Chromium **147–156**、Brave Stable ≥1.89.132 | 需 `chrome://flags/#canvas-draw-element` |
| Firefox / Safari | **不支持**（无时间表） |

**硬性前置条件（不满足就不画，且不报错）**：

1. canvas 上要有 `layoutsubtree` / `content="drawable"`；
2. 被画的元素必须是 **canvas 的直接子元素**（157+ 还要带 `drawable`）；
3. 元素必须**生成了盒**（`display:none` 不行）；
4. **元素自身的 CSS transform 对绘制无效**（位置由 `drawElementImage` 的 dx/dy 决定，画布 CTM 生效）；
5. 内容按元素的 **border box 裁剪**。

第 4 条很关键：**卡片不能"用 CSS 摆位、再整体截图"**。在 canvas 模式里，位置来自画布坐标，DOM 的 transform 只服务于命中测试/无障碍。

### 1.2 方法表

| 成员 | 签名 | 作用 |
| --- | --- | --- |
| `HTMLCanvasElement.layoutSubtree` / `content` | — | 让子元素参与布局与命中测试 |
| `onpaint` / `paint` 事件 | `PaintEvent{changedElements}` | 子元素渲染变化时触发；`changedElements` 是**这次变了的子元素** |
| `requestPaint()` | — | 强制下一帧触发 paint（类似 `requestAnimationFrame`，不依赖子元素变化） |
| `drawElementImage` | 4 个重载，镜像 `drawImage` | `(el,dx,dy)` / `(el,dx,dy,dw,dh)` / `(el,sx,sy,sw,sh,dx,dy)` / `(el,sx,sy,sw,sh,dx,dy,dw,dh)`；**2D 下返回 `undefined`** |
| `captureElementImage(element)` | → `ElementImage` | 抓一份快照，可 `postMessage` 传给 Worker |
| `getElementTransform(el, drawTransform)` | → `DOMMatrix` | **WebGL/WebGPU 用**：反算 DOM 该有的 CSS transform |
| `ElementImage` | `{width,height,close()}`，Transferable | Worker 里直接画，用完 `close()` 释放 |
| WebGL | `texElementSubImage2D(target, level, xoffset, yoffset, el)` | 先自建纹理再上传（旧名 `texElementImage2D` 在 157 移除） |
| WebGPU | `drawElementImageToTexture(el, dest)` | 旧名 `copyElementImageToTexture` 在 157 移除 |
| 新 | `canvas.updateElementGeometry()` | 给 WebGL/WebGPU 画布手动设置命中/无障碍边界 |

### 1.3 快照语义（容易踩的坑）

| 时机 | 画到的是 |
| --- | --- |
| 在 `paint` 事件回调里 | **当前帧**的快照 |
| 在 `paint` 之外 | **上一帧**的快照 |
| 首帧之前调用 | **抛异常** |

所以标准写法是：`onpaint` 里 `ctx.reset()` → 按 `changedElements` 决定重画范围 → 收工。

### 1.4 DPR（文字不糊的关键）

```js
new ResizeObserver(([e]) => {
  c.width  = e.devicePixelContentBoxSize[0].inlineSize
  c.height = e.devicePixelContentBoxSize[0].blockSize
}).observe(c, { box: 'device-pixel-content-box' })
```

用 `device-pixel-content-box` 而不是 `clientWidth`，否则 2x 屏上文字发虚——**这是"真 HTML 进 canvas"和"截图凑数"的视觉分界线**。

---

## 2. 对我们这个应用意味着什么

我们有 **737 条**真实条目（见 [APPLIED.md](APPLIED.md) 的实测）。把规范逐条对到场景：

| 规范事实 | 对 737 张卡的影响 | 结论 |
| --- | --- | --- |
| 子元素必须参与布局 | 737 个 DOM 节点**仍然存在**，只是不需要各自合成 | DOM 成本没省，省的是**合成层数** |
| CSS transform 对绘制无效 | 不能用 CSS 3D 摆位再交给 canvas | 两套坐标系必须分开设计（见下） |
| `changedElements` | 只有变了的卡重画 | 增量重绘可行，这是 737 规模的关键 |
| 首帧前抛异常 | 需要一个"骨架帧" | 先画占位，再等 paint |
| FF/Safari 不支持 | 内部用户里只要有 Safari 就不能只做这一条路 | 必须双路线 |

### 2.1 结论：双渲染器，按"要不要读字"分工

| 缩放档 | 渲染器 | 理由 |
| --- | --- | --- |
| L0 总览（k<0.30） | **SVG 批量块**：一域一个 `<svg>`，域内 737 个 `<rect>` | 一次绘制，零 DOM 卡片；块只是几何 |
| L1 域内（0.30–0.95） | SVG 块 + 视口内少量 DOM 卡（文字仍小） | 过渡档 |
| L2 阅读（≥0.95） | **DOM 卡片**（真实文字、可选中、可读屏） | 这一档才需要"真 HTML" |
| Phase-2（可选） | 同一套几何交给 **HTML-in-Canvas**：一个 canvas + 视口内的 `drawable` 卡片，`changedElements` 增量重画 | 只给 Chrome 157+ 的"演示模式"，Safari/FF 仍走 L2 |

**为什么 Phase-2 不是主路线**：它省的是合成，不省布局；而我们的痛点（737 条的 DOM 数量）靠**虚拟化**解决更直接。HTML-in-Canvas 的真正价值在"一镜到底缩放到卡片内部"这类演示场景——那正是 Expo Mode 的用法。

### 2.2 Phase-2 的实现骨架（给后面的人）

```js
// 只在 Chrome 157+ 且用户显式开启「演示模式」时启用
const supported = 'layoutSubtree' in HTMLCanvasElement.prototype || 'drawable' in HTMLElement.prototype
if (!supported) return renderCss3d()

canvas.addEventListener('paint', () => {
  const dirty = new Set(paintEvent.changedElements)      // 增量
  ctx.reset()
  for (const c of visibleCards) {
    if (!dirty.size || dirty.has(c.el)) draw(c)          // 只画变了的那批
  }
})
function draw (c) {
  const x = c.wx * cam.k + cam.tx, y = c.wy * cam.k + cam.ty
  ctx.save(); ctx.scale(cam.k, cam.k)
  ctx.drawElementImage(c.el, x / cam.k, y / cam.k, c.w, c.h)   // 注意 CTM 与 dx/dy 的关系
  ctx.restore()
}
```

要点：
- 卡片元素必须是 canvas 的**直接子元素**，且 `display:none` 的卡不能画（虚拟化用 `visibility:hidden` 而不是 `display:none`）；
- 用 `requestPaint()` 在相机变化时触发，不要每帧无条件画；
- WebGL 路线要 `getElementTransform()` 回写 CSS transform，否则命中测试和肉眼会错位。

---

## 3. 交互模型的复原（与 v1 一致，补充量化）

| 要素 | 复原值 | 依据 |
| --- | --- | --- |
| 相机档位 | 3 档：全域 / 分区 / 卡片 | 笔记描述"镜头先俯瞰全貌，再钻进某个分区" |
| 缩放即导航 | 无面包屑、无侧栏树 | 同上；本设计改为"检索永远可用"（737 条必须有兜底） |
| 分区表达权重 | 面积 ∝ √n | 实测：linux 225 条若按 n 分配会吃掉 30.5%，√ 压缩后 21.4% |
| 连线表达关系 | 同 platform / 同 service / 互补类型 | 条目无显式关系字段（缺口 B），只能推断且必须标注 |
| 卡片 = 真界面 | 我们改为"卡片 = 真条目摘要（可点开正文）" | 我们没有"一个功能一个界面"，但有 737 条真数据 |

---

## 4. 深度逆向后仍不确定的部分（诚实边界）

1. **Expo Mode 的具体相机参数**（FOV、速度曲线、分区间距）无法获取——它没有公开页面或仓库。我们用的是自己的值，不是"抄来的"。
2. **它对卡片的 LOD 策略**未知。我们的"SVG 批量块 → DOM 卡片"是按 737 条实测出来的，属本项目自研。
3. **性能数字**：规范没给 737 级别的基准，我们的数字全部来自本机实测，见 [APPLIED.md](APPLIED.md)。
