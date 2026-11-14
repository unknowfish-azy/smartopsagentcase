# SmartOpsAgent Personal Operations System

## Intent

Quiet, technical, editorial. The interface presents a personal SRE knowledge space, not an administration template.

## Color

- Background: `#05090D`
- Surface: `#071018`
- Raised surface: `#0A1118`
- Primary text: `#E8F2F7`
- Secondary text: `#92A6B5`
- Rule: `rgba(159, 190, 207, 0.18)`
- Accent: `#2496ED`
- Accent soft: `#7AD7F5`
- Status colors are reserved for explicit state only.
- Celebration gold (`#F5C942` family) is a controlled exception scoped to the MilestoneRain canvas and its immediate celebration markers (unlocked achievement border and status chip). It never enters status colors, data colors, or general chrome. Milestone celebrations are driven by real ledger data only; no unevidenced states are ever presented.

## Typography

- Display: Geist or system sans fallback, 400-600 weight.
- Technical metadata: Geist Mono or ui-monospace fallback.
- Editorial headings use natural wrapping, normal letter spacing, and a maximum readable measure.
- Labels are uppercase mono with 0.12em tracking.
- Bilingual editorial tokens live in `variables.css`: `--display-cn` (56-84px desktop, 34-48px mobile), `--display-en` (20-30px), `--section-cn` (36-52px), `--section-en`, `--body-cn`, `--body-en`, and `--label-size`.
- Chinese carries personal identity and uses a humanist system fallback at 400 weight; English carries system/operations meaning in Geist Mono with wider tracking. English is an offset second track, not a literal translation line.
- Home and Knowledge headings follow `index -> Chinese identity -> English system label -> description`; title rules use thin dividers and signatures use restrained `OPERATE / LEARN / REMEMBER` metadata.

## Layout

- Desktop rail: 252px. Content uses a 12-column grid with asymmetric 4/8, 3/9, and 5/7 compositions.
- Sections use 72-144px vertical rhythm on desktop and 48-80px on mobile.
- Separate content with thin rules and whitespace before considering cards.
- Use 0-4px radius. Cards are reserved for forms, modals, and bounded technical tools.

## Navigation

- Navigation is indexed text: Personal System, Knowledge, Operations, Agent, Memory, then infrastructure destinations.
- Header contains route context, environment, agent state, and local time.

## Particle Whale

- Single canvas instance for protected SPA routes; login can render an isolated full-viewport instance.
- State modes: idle, thinking, executing, observing, warning, error, recovering.
- Quality tiers: high 18k, medium 10k, low 4.2k particles; reduced motion is low/static.
- Use WebGL buffer geometry, typed arrays, visibility pause, and no per-frame framework state.
- The whale is a living infrastructure organism: staged 9.3s inhale/hold/exhale/rest breathing, point-level body deformation, delayed tail follow-through, internal flow, and a restrained cyan breath stream. Continuous rotation is prohibited.
- Runtime frame pressure may reduce the visible point draw range to 55% and restore it once frame time stabilizes; structural regions are interleaved so the silhouette remains recognizable.

## Living Organisms

- Semantic hierarchy: Docker Whale = infrastructure body; Kubernetes Spider = cluster topology; Living Jellyfish = Agent awareness.
- All visual organisms read the same low-frequency fluid field but use different durations and phase offsets: whale 6.4-9.3s, jellyfish 4.9-6.1s drift and 5.2-6.8s breathing, spider 3.2-4.8s topology flow.
- The login Jellyfish is a procedural SVG organism, not an image: translucent deep-pink body, blue-violet Bezier tentacles, 360 soft particles, internal energy streams, light pointer response, and `prefers-reduced-motion` static rendering.
- On the login ecosystem, whale exhale is coupled into a small Jellyfish glow and tentacle-flow response. The components never share a synchronized loop or global Vue animation state.

## Stellar Ocean

- `StellarOceanProvider` defines the shared environmental state. Its render data is supplied by `stellarOcean.js` and is drawn inside the existing Particle Whale WebGL renderer, never as an additional page canvas.
- Three point layers provide depth: muted background stars, mid-depth active stars, and brighter local energy stars. Density is intentionally uneven, with open water between clusters.
- Star chains use only nearby mid-layer nodes, low opacity, and gently curved two-segment paths. Chain particles travel slowly; the field must never resemble a dependency graph or a galaxy wallpaper.
- Whale inhale bends nearby stellar paths inward; exhale produces a soft local ripple and a slight chain-intensity lift. The login Jellyfish creates a lighter local disturbance; Spider reads the same flow and receives a subtle exhale pulse.
- Stellar quality tiers: high 900 stars / 40 chains / 52 flows, medium 520 / 26 / 32, low 260 / 14 / 16. Reduced motion keeps the low field static and disables movement, tide, ripple, and flows.

## Motion And Accessibility

- Motion is slow and state-driven. Route transitions only fade/translate small distances.
- Reduced motion disables particle animation and nonessential transitions.
- All controls retain visible focus, semantic labels, and at least 44px hit areas on touch layouts.

## Responsive

- Verify 375, 768, 1024, 1440, and 1920 pixel widths.
- On small screens, navigation becomes a compact indexed strip and the whale moves behind or below content.
- Long technical identifiers wrap instead of forcing horizontal scroll.

## Open Source Intake

- Route (confirmed 2026-10-18): intelligent operations (AIOps) is the primary visualization route. Quant dashboard vocabulary is visual reference only, not product direction.
- Tier A, direct dependency allowed (MIT / Apache-2.0; retain copyright and NOTICE): tremorlabs/tremor, tradingview/lightweight-charts, satnaing/shadcn-admin, Kiranism/next-shadcn-dashboard-starter, dromara/go-view, setWan/goView, DataV-Team/DataV, L-noodle/vue-big-screen-plugin, laogong5i0-2/vue-big-screen-plugin, ccfos/nightingale, apache/hertzbeat, apache/skywalking, hummingbot/hummingbot, vnpy/vnpy.
- Tier B, isolated use only: freqtrade/freqtrade (GPL-3.0; no code copying into this repository), stophobia/OpenProphet (NOASSERTION custom license; read LICENSE before any use).
- Tier C, prohibited: grafana/grafana (AGPL-3.0 network copyleft); jakobildstad/QuantDash, tangzhimang/vue-big-screen, nyrf/vue-big-screen, thekingofall/quant-trading-bot (no license = all rights reserved); you200109/quanttrading (repository 404).
- Naming caution: L-noodle/vue-big-screen and its forks carry no license, while the separate vue-big-screen-plugin repository from the same lineage is MIT. Similar names, opposite outcomes. Always verify the exact repository, never a family name.
- Default method: replicate design language and write own components. A new npm dependency requires a fresh GitHub API license check before introduction; licenses change as projects migrate (tremorjs/tremor is gone, tremorlabs/tremor is Apache-2.0).
- Star count and apparent completeness never imply commercial usability. Every intake decision records its SPDX id and verification date in `reports/open-source-license-verification-2026-10-18.md`.
- Any performance or effect metric (savings, accuracy, usage deltas) states its measurement basis, sample window, and comparison baseline. The project is evidence-first: unevidenced states are never presented as fact, and external visual vocabulary never overrides this.

## Revision 2026-11-12 — Dual-surface contract (supersedes conflicting legacy values)

The 0-4px radius rule above described the original editorial prototype. The product now has two explicit surfaces; where this section conflicts with earlier lines, **this section wins**.

- **Expressive surface** (`/login`, brand/intro pages): cosmic starfield + a single simplified jelly-glass card. Radius 12-14px, blur <= 12px, one static inner highlight, spring deformation on focus. No per-frame pointer-driven gradient repaint, no WebGL, no 1MB bitmap, no vertical ink scroll, no OPS glyph.
- **Tool surface** (user console on :5173, admin console on :5174): enterprise-grade, quiet, high-density flat. Radius 4-8px, 1px rules, flat backgrounds, **zero `backdrop-filter`**, no particles, no WebGL. Cards are a legitimate tool primitive here (tables, filters, metrics), unlike the editorial prototype.
- Radius tokens: `--ds-radius-sm 4` / `--ds-radius-md 8` / `--ds-radius-lg 12` / `--ds-radius-pill 999`. New code must use `--ds-*`; `--smart-*` remains a compatibility alias and `--el-*` is a hard contract that must not be rewritten.
- Breakpoints are exactly 375 / 768 / 1024 / 1440 / 1920 (`src/design/breakpoints.js`). Do not introduce new ad-hoc breakpoint values.
- Typography is a local system stack (`--ds-font-cn`, `--ds-font-mono`); external Google Fonts `@import` is removed to unblock first paint and offline use.
- Motion budget: one shared rAF scheduler (`src/visual/motionScheduler.js`), 30fps default, 15fps on sustained slow frames, off-screen pause, static single frame under reduced motion. `src/design/surfacePolicy.js` exposes the adaptive recommendation and its human-readable reason.
- Evidence rule still applies: every visual/performance claim (FCP, LCP, frame time, rAF count, blur radius) must state its measurement basis and before/after baseline. See `docs/development/前端整改-企业级控制台与果冻登录方案-20261112.md`.

## Revision 2026-11-19 — Agent module plate (scoped exception inside the tool surface)

`/agent/module`（`views/agent/AgentModuleView.vue`）是工具层里的一张"版面"，不是新的 surface 类型；其余路由不受影响。

- **Allowed:** a scoped warm-paper palette (`--fab-*` in `assets/styles/fable-agent.css`), constructivist geometry, one SVG "gaze" organ, and soft fat-volume blobs. Selectors stay inside `.fable-*`; the global `.panel` / light-theme card rules must not reach them (verified in `test/agent-module.browser.mjs`).
- **Still forbidden here:** `backdrop-filter`, WebGL, canvas particles, bitmap imagery, and per-frame framework state. The page draws with SVG, CSS gradients, and CSS transitions only.
- **Radius and rules:** `--ds-radius-sm` for plates and panels, 1px hairlines, no gradient card borders. Breakpoints remain 375 / 768 / 1024 / 1440 / 1920.
- **Motion:** composition transforms 900-1200ms, aperture 900ms, gaze 620-700ms, fat-blob breathing 7.4s at ≤1.6% scale. Pointer tracking uses the shared `motionScheduler` at 30fps and unsubscribes on pointer leave; reduced motion keeps a static frame.
- **Ambient organisms:** `MainLayout` skips the whale and jellyfish on this route (`isCompositionPlate`) because their particles cross the plate copy; the desktop pet stays and remains user-dismissible.
- **Evidence rule:** the page renders only live runtime signals or explicitly tagged `SAMPLE` / `REHEARSAL` content; missing data renders `—`, never an estimate. Structural parameters (aperture / tilt / volume) are drawing parameters, labelled as such, and never presented as model or operational metrics.
- Spec and acceptance: `docs/design/agent-module-v1/DESIGN.md`, `frontend/test/agent-module.browser.mjs`.

## Revision 2026-11-14 — Spatial Field plate (scoped exception inside the tool surface)

`/knowledge/space` 的 **场域**视图模式（`views/knowledge/space/SpaceFieldView.vue` + FieldStage/FieldPlane/EvidenceBed/ThreadLayer/InsightCanopy）是工具层里的"三层空间场"，不是新的 surface 类型；`/knowledge/space` 的 **空间 / 网格 / 列表** 三个原有视图完全不受影响，其余路由也不受影响。

此节的所有约束仅作用于上述组件树；其他路由继续遵守 tool surface 基线（零 WebGL / 零粒子 / 零 backdrop-filter）。

### 允许项
- **CSS 3D 变换层**：`FieldStage` 作为 `perspective` 容器，子元素使用 `transform-style: preserve-3d` + `translate3d(x, y, z)` 在世界坐标系中定位。yaw / pitch 受限轨道（yaw ±35°, pitch 8–52°），三机位预设，Esc 三级回退。
- **单 Canvas2D 证据层**（`EvidenceBed.vue`）：只画真实 `evidenceRefs`，空数组不装饰。15fps（motionScheduler 订阅），reduced-motion 静态单帧。新事件到达时 400ms 一次性局部脉冲，不循环。
- **SVG 线程层**（`ThreadLayer.vue`）：屏幕空间叠加，与世界坐标换算后绘制。纵向渐变（`--ds-accent-soft → --ds-accent → --ds-text-secondary`），hover 2px + relation 标签。`contradicts` 用虚线 + 菱形端点；`operational` 用短横线 + 空心端点。

### 仍然禁止（与 tool surface 一致）
- **WebGL**（three.js / raw WebGL）— 暂未达准入条件（见 DESIGN.md §7 四条：FPS 不足、世界平面 ≥1500、MASTER 新增 scoped exception、有 before/after 实测）。
- **粒子装饰**（背景网格 / 星空 / 永续动画）。`EvidenceBed` 空数组时 canvas 必须完全透明。
- **`backdrop-filter` / `backdrop-blur`**（FieldPlane / InsightCanopy 使用 `rgba()` 半透明背景）。
- **逐帧框架状态写入**（不允许在 `requestAnimationFrame` 里逐平面 `setState` / `v-model`；所有变换批量一次性写 `transform`）。
- **新增独立 `requestAnimationFrame` 循环**（全部走 `motionScheduler.subscribe()`，共享 rAF 调度器）。

### 预算（硬约束，DESIGN §6.2）
- 同帧挂载世界平面 ≤ **480**；超出按距相机 target 的距离升序截断并 `console.warn('[field] plane budget exceeded …')`。
- 同帧可见平面 ≤ **180**（视锥 + 距离裁剪）。
- 帧率：30fps 默认，慢帧自动降 15fps（motionScheduler 的全局降级机制），`prefers-reduced-motion` 下单帧静态无补间。
- `will-change: transform` 生效元素 ≤ 40；其余靠合成层提升（`translate3d` 天然促成）。
- 世界平面数据结构（JS 对象）≤ 2 MB。

### 文字与可访问性
- **所有文本为屏幕空间 DOM**（FieldPlane / InsightCanopy 直接输出 `<span>` / `<h3>`，不画 canvas-text / SDF-text）。必须可选中、可搜索、可被读屏。
- `aria-label` 复述位置与身份（DESIGN §8）：知识层 / 洞察层 · domain · 条目身份。
- `far` / `mid` LOD 平面 `aria-hidden="true"`、`tabindex="-1"`，不参与 Tab 序；`near` / `focus` 平面可聚焦。
- 触控命中区 ≥ 44px；对比度 ≥ 4.5:1。
- 断点 375 下禁用自由轨道（SpaceFieldView.vue media query 禁用 pointermove 拖拽，隐藏 ThreadLayer）。

### 其他
- **不引入新 npm 依赖**（Phase A 0 新增依赖；WebGL 需先过 Open Source Intake）。
- **不新建后端接口**（Phase A 纯前端数据契约；Phase B 才加只读 `GET /api/knowledge/{id}/evidence-refs`）。
- **不改 `catalogProjection` 白名单**（`knowledgeModel.js` 的字段白名单保持不动；新增的 `evidenceRefs` / `insightRefs` / `freshness` 被自动丢弃，这是正确行为，它们是前端派生/待接入字段）。
- **不编造数据**：`evidenceRefs` 缺失 → EvidenceBed 对应域无带；绑定 0 命中 → `operational` 模式（InsightCanopy 显式「未绑定知识」）。

### Evidence rule
- 平面预算的 before/after：`npm run perf:baseline`（覆盖 `/knowledge/space` field 视图场景）或独立 node 脚本验证 `computeField.stats`（见 `frontend/test/field-layout.test.mjs`）。
- 帧率 / 内存：motionScheduler 输出的帧时间日志 + Chrome DevTools Performance 面板截图。
- 无 before/after 数字的性能结论视为未验收。

- Spec: `docs/design/spatial-knowledge-field/DESIGN.md`, `docs/design/spatial-knowledge-field/KNOWLEDGE-INSIGHT-BINDING.md`
- Source: `frontend/src/views/knowledge/space/useFieldLayout.js`, `bindingIndex.js`, `SpaceFieldView.vue`, `FieldStage.vue`, `FieldPlane.vue`, `EvidenceBed.vue`, `ThreadLayer.vue`, `InsightCanopy.vue`
- Tests: `frontend/test/field-layout.test.mjs`, `frontend/test/binding-index.test.mjs`
