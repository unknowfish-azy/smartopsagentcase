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
