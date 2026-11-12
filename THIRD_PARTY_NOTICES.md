# 第三方技术与设计参考声明

> 依 AIC 算法创新赛「引用他人技术、算法或数据需在参赛材料中明确标注」与「拥有自主知识产权或合法授权」要求建立。
> 核实日期：2026-11-12（GitHub REST API）。star 为当日快照。

本项目为自主开发的智维Agent / SmartOpsAgent。以下开源项目仅用于**设计思路、参数与架构模式参考**，未整站复制、未替代本项目 UI 框架、未引入为生产依赖（除已在 `package.json` 中声明的既有依赖）。

## 一、企业级 B 端控制台（信息架构与密度参考）

| 仓库 | 许可证 | 参考内容 | 是否引入代码 |
|---|---|---|---|
| `vbenjs/vue-vben-admin` | MIT | Monorepo 分层、动态路由、虚拟列表性能实践 | 否 |
| `soybeanjs/soybean-admin` | MIT | 轻盈视觉语言、令牌化样式、克制动效 | 否 |
| `pure-admin/vue-pure-admin` | MIT | Element Plus 按需、打包体积控制 | 否 |
| `HalseySpicy/Geeker-Admin` | MIT | ProTable 高级表格与密度控制 | 否 |
| `arco-design/arco-design-pro-vue` | MIT | 企业级栅格与表单规范 | 否 |
| `Tencent/tdesign-vue-next` | MIT | 企业级设计令牌体系与深浅主题 | 否 |
| `tusen-ai/naive-ui` | MIT | 主题覆盖机制 | 否 |
| `TanStack/virtual` | MIT | 虚拟滚动内核思路；核对后本项目列表均为服务端分页（20–100 行/页），无需虚拟滚动，未安装该依赖 | 否 |

## 二、果冻 / 液态玻璃（光学参数与性能门控参考）

| 仓库 | 许可证 | 参考内容 | 是否引入代码 |
|---|---|---|---|
| `archisvaze/liquid-glass` | MIT | SVG `feDisplacementMap` 折射、IOR/厚度参数、形状预设 | 否 |
| `sohumsuthar/liquid-glass` | MIT | **性能门控表**：blur 上限、粒子 canvas 30fps、`hover:none` 关追光、低帧率自动降级 | 否（参数借鉴） |
| `nikdelvin/liquid-glass` | MIT | LiquidGlass / LiquidButton 组件抽象、Safari blur-only 降级 | 否 |
| `@daviduo/liquid-glass-web` | MIT（npm 包声明，GitHub 归属未核实） | Vue 3 composable / 指令思路、ResizeObserver 重建 | 否 |

浏览器兼容约定：`backdrop-filter: url(#filter)` 仅 Chromium 完整支持，项目保留 `@supports not (backdrop-filter)` 的 blur-only / 实底回退。

## 三、宇宙星空（零依赖与单一 rAF 参考）

| 仓库 | 许可证 | 参考内容 | 是否引入代码 |
|---|---|---|---|
| `AmiARMiess/nebulabs` | MIT | 纯 CSS 星云 + Canvas 2D 星野、400ms rAF watchdog、reduced-motion 静态一帧 | 否 |
| `Edwson/GalaxyJS` | MIT | 全页共享单一 rAF、离屏暂停、DPR 钳制、设计令牌化 | 否（架构借鉴，见 `src/visual/motionScheduler.js`） |
| `TheodorStorm/starfield` | MIT | 无依赖星野与设备自适应密度 | 否 |

## 四、项目自研部分（核心贡献）

- `--ds-*` 统一设计令牌与表现层/工具层分级契约（`src/assets/styles/variables.css`、`src/design/surfacePolicy.js`）
- 自适应视觉预算与可解释降级理由（`src/design/surfacePolicy.js`）
- 全页共享 rAF 调度器（`src/visual/motionScheduler.js`）
- 简约果冻登录窗口的光学参数与 spring 形变（`src/views/auth/LoginView.vue`）
- AI 证据链 UI 语法、四级核查、版本感知混合检索等既有能力

## 五、抖音参考说明

用户提供的两条抖音图文短链（`CWNdoWZNifU`、`JguFIutypO8`）在公开 Web 侧均返回「请尝试在抖音内观看」，**未取得任何画面或素材**，未做扒站、未绕过访问限制、未提取受保护资源。整改方案的视觉规格来自用户口述归纳（B 端简约控制台 / 宇宙星空 / 果冻体视感）与上述公开开源资料，不构成对原作品的复刻。
