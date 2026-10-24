# Personal Operations System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recast the Vue operations console as a personal operations knowledge space without breaking existing routes, API calls, or preview authentication.

**Architecture:** A shared editorial app shell supplies navigation, status context, and one WebGL particle whale for protected routes. Existing views retain their stores and API modules while their visual structure moves to section index, technical list, timeline, and empty-state patterns.

**Tech Stack:** Vue 3, Vite, Vue Router, Pinia, Element Plus, Three.js, Node test runner, native CSS.

**Spec:** User request dated 2026-09-20: Personal Operations Knowledge Space visual and information architecture refactor.

## Global Constraints

- Preserve existing routes, data fetching, login guard, and API module contracts.
- Use dark editorial tokens, a single Docker cyan accent, thin rules, and no generic dashboard card grid.
- Keep exactly one app-level WebGL Whale for protected routes; use a separate full-screen instance only on login.
- Respect `prefers-reduced-motion`; avoid Vue reactive writes inside animation frames.
- Do not represent unavailable API data as real operational data.

## Review Focus

- Reduced motion must render a static, low-density whale.
- Narrow screens must use the low particle tier and keep content unobscured.
- Route changes must update whale state without recreating its canvas.
- Existing preview login redirect behavior must remain unchanged.
- Empty API results must display an explicit empty state instead of invented metrics.

---

### Task 1: Design System And Test Harness

**Files:**
- Create: `design-system/MASTER.md`
- Create: `frontend/test/whale-quality.test.mjs`
- Create: `frontend/src/components/common/whaleQuality.js`
- Modify: `frontend/package.json`

- [ ] Write a failing Node test that expects low/static reduced motion and high desktop density.
- [ ] Run `node --test test/whale-quality.test.mjs`; expect module-not-found failure.
- [ ] Add `resolveWhaleQuality({ width, dpr, reducedMotion })` and Node test scripts.
- [ ] Re-run the test; expect two passing tests.

### Task 2: Shared WebGL Whale And App Shell

**Files:**
- Create: `frontend/src/components/common/ParticleWhale.vue`
- Create: `frontend/src/components/common/whaleShape.js`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/assets/styles/variables.css`
- Modify: `frontend/src/assets/styles/global.css`

- [ ] Use a Three.js `BufferGeometry` with typed arrays for whale body, tail, head, and container blocks.
- [ ] Map route metadata to position, scale, opacity, flow, and semantic state.
- [ ] Replace icon-led sidebar with indexed text navigation and a compact header status line.
- [ ] Verify route changes preserve one canvas element and reduced motion disables frame updates.

### Task 3: Editorial Home, Knowledge, And Agent

**Files:**
- Modify: `frontend/src/views/dashboard/DashboardView.vue`
- Modify: `frontend/src/views/knowledge/KnowledgeView.vue`
- Modify: `frontend/src/views/agent/AgentCommandCenterView.vue`

- [ ] Replace preview metrics with store-backed lists and explicit empty states.
- [ ] Compose home as Personal System, Knowledge, Operations, Agent, and Memory sections.
- [ ] Turn Knowledge into indexed taxonomy and availability-aware content.
- [ ] Turn Agent into a vertical action stream that retains Inspector API calls.

### Task 4: Login And Existing Operational Views

**Files:**
- Modify: `frontend/src/views/auth/LoginView.vue`
- Modify: `frontend/src/views/server/ServerListView.vue`
- Modify: `frontend/src/views/inspector/InspectorCenterView.vue`
- Modify: `frontend/src/router/index.js`

- [ ] Replace the login-specific particle sphere with the shared whale renderer in login mode.
- [ ] Apply the editorial page primitives to server and Inspector views without changing their data operations.
- [ ] Add semantic route metadata and maintain all legacy deep links.

### Task 5: Verification

**Files:**
- Modify as needed only for test/build failures.

- [ ] Run `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build`.
- [ ] Verify protected routes and `/login` in a browser at 375, 768, 1024, 1440, and 1920 pixel viewports.
- [ ] Verify reduced motion and no horizontal overflow on all target pages.
