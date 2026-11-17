# 侧栏导航动效与无障碍说明

> 适用范围：个人系统侧栏（`PersonalSystemNavigation`）的展开组动效。
> 关联文件：[PersonalSystemNavigation.vue](../frontend/src/components/navigation/PersonalSystemNavigation.vue)、[MainLayout.vue](../frontend/src/layouts/MainLayout.vue)、[visualMode.js](../frontend/src/visual/visualMode.js)。

## 1. 动效清单

| 编号 | 动效 | 时长 | 触发时机 |
| --- | --- | --- | --- |
| M1 | 展开组高度过渡 | 180ms（淡入 150ms） | 点击展开/收起按钮 |
| M2 | 折叠箭头旋转 | 150ms | 同上，`rotate(-90deg) ↔ 0` |
| M3 | 子项级联入场 | 每项 200ms，步进 30ms | 展开组首次渲染子项 |
| M4 | 收起态浮出层滑入 | 140ms | 图标轨 hover / 键盘聚焦唤出 |

（截图占位：M1 展开过渡中间帧）

（截图占位：M3 子项级联入场序列）

（截图占位：M4 浮出层滑入）

## 2. 无障碍设计原则

### 2.1 三层降级门禁

动效从"完整 → 精简 → 关闭"逐层降级，任何一层命中即保证信息可达：

1. **系统级** `prefers-reduced-motion: reduce`
   - CSS：所有动画/过渡置 `none`（含 `@media` 内的 M1–M4 全量规则）；
   - JS：`onChildrenEnter / onChildrenLeave` 直接 return，高度即时呈现，不产生中间帧。
2. **应用级** 顶栏 VISUAL 选择「减少动效」
   - MainLayout 的全局规则 `[data-visual-mode='reduced-motion']` 关闭侧栏内一切 CSS 动效；
   - 浮出层因 Teleport 到 `body`（选择器作用域外），改为直接读取 `visualMode` 状态交空过渡名。
3. **应用级** VISUAL 选择「轻量视觉」
   - 仅关闭装饰层（M3 级联、M4 滑入的位移分量），保留 M1 高度过渡作为必要的状态反馈。

### 2.2 不依赖动效传递信息

- 展开状态的真实数据源是 `aria-expanded`，动效只是视觉映射；动画被禁用时语义无损。
- 箭头方向（M2）始终与 `aria-expanded` 同步，色弱用户也可通过旋转方向判断状态。

### 2.3 键盘交互不受影响

- 浮出层唤出保留键盘路径：Tab 聚焦行 → 浮层出现 → 焦点自动进入首项 → Escape 关闭并归还焦点；
- 过渡期间不拦截任何按键事件，`Tab` 顺序与无动效版本完全一致；
- M3 级联延迟不阻塞交互：子项在延迟期间已可点击/聚焦（`animation-fill-mode: backwards` 仅影响视觉）。

### 2.4 焦点可见性

- 展开/收起按钮与浮出层链接保留 `:focus-visible` 轮廓，动效不覆盖焦点样式；
- 高度过渡（M1）期间 `overflow: hidden` 仅存在于过渡类挂载期间，结束后即移除，不会裁剪焦点环。

## 3. 实现要点速查

| 关注点 | 位置 |
| --- | --- |
| 高度过渡 JS 钩子 | `onChildrenEnter / onChildrenAfterEnter / onChildrenLeave` |
| 浮出层过渡名按视觉档切换 | `flyoutTransition` computed（balanced 才有动效） |
| reduced-motion 媒体查询 | 组件 `<style scoped>` 末尾集中声明 |
| 全局视觉档规则 | MainLayout `[data-visual-mode='reduced-motion']` |

（截图占位：VISUAL 档位切换下拉）

## 4. 验证清单

- [ ] 系统开启"减弱动态效果"后展开 KNOWLEDGE 组：子项即时出现，无高度动画
- [ ] VISUAL 切到「减少动效」后重复上述操作：效果一致
- [ ] VISUAL 切到「轻量视觉」：仍有平滑展开，但子项无级联延迟
- [ ] 键盘 Tab 进入侧栏 → 聚焦 OPERATIONS → 浮层出现且焦点在首项 → Escape 归还焦点
- [ ] 展开动画播放中连续快速点击展开/收起：无残影、无高度错位
- [ ] 侧栏收起为图标轨后 hover 任意组：浮层滑入，`prefers-reduced-motion` 下即时呈现

## 5. 边界与不做的事

- 不为侧栏添加粒子、扫光、backdrop-filter（G8 红线）；
- 不在动效中传递"新增/告警"等语义（G7：语义由健康徽章承担）；
- 不用动效时长超过 250ms（避免拖慢高频导航操作）；
- 浮出层的定位/夹取逻辑（clampFlyout）与动效解耦，动画不参与坐标计算。
