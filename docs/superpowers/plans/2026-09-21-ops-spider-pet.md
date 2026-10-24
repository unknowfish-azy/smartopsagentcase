# Ops Spider Pet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, accessible, stateful Ops Spider topology pet that provides safe navigation shortcuts without inventing Kubernetes data.

**Architecture:** A pure state helper converts actual route/Agent activity and inactivity into a presentation state. A small Pinia store persists only a corner position and interaction state. `OpsSpiderPet` renders an SVG orb and an existing `KubernetesSpider` in a fixed layer, while `MainLayout` provides route-derived state and controls stacking with existing organisms.

**Tech Stack:** Vue 3, Pinia, Vue Router, SVG, CSS animations, existing `KubernetesSpider`, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-21-ops-spider-pet-design.md`

## Global Constraints

- Retain the Personal System, Stellar Ocean, whale, jellyfish, and existing typography.
- Do not create a second WebGL canvas or one DOM element per particle.
- Never fabricate cluster, node, Pod, alert, or Agent telemetry.
- The pet navigates only to existing routes and never executes remote operations.
- Persist only the non-sensitive corner placement preference.
- Use transform and opacity for motion; respect `prefers-reduced-motion` and document visibility.
- Provide button and keyboard alternatives to drag-only placement.

## Review Focus

- A route change must never claim a cluster is connected or generate fake counts.
- Compact mode on `/connections` must reserve terminal priority and keep the pet within the viewport.
- A pointer click must not be interpreted as a drag, and a drag must not accidentally activate navigation.
- Sleeping must engage only after the defined inactivity window and wake on a real interaction.
- Reduced-motion users must retain all menus and status semantics without continuous animation.

---

### Task 1: Pet State And Position Helpers

**Files:**
- Create: `frontend/src/components/common/opsSpiderState.js`
- Create: `frontend/test/ops-spider-state.test.mjs`

**Interfaces:**
- Produces `resolveOpsSpiderState({ routeName, agentState, inactiveMs })`.
- Produces `snapOpsSpiderPosition({ x, y, viewportWidth, viewportHeight, size, inset })` for optional corner placement and `clampOpsSpiderPosition(...)` for free dragging.
- Produces `resolveOpsSpiderSize({ width, routeName })`.

- [x] **Step 1: Write failing behavior tests**

```js
test('sleeps after thirty minutes but keeps a real route state before then', () => {
  assert.equal(resolveOpsSpiderState({ routeName: 'AgentCommandCenter', agentState: 'thinking', inactiveMs: 1799999 }), 'thinking')
  assert.equal(resolveOpsSpiderState({ routeName: 'AgentCommandCenter', agentState: 'thinking', inactiveMs: 1800000 }), 'sleeping')
})

test('snaps a released pet to the closest safe corner', () => {
  assert.deepEqual(snapOpsSpiderPosition({ x: 1200, y: 750, viewportWidth: 1280, viewportHeight: 800, size: 68, inset: 20 }), { x: 1192, y: 712 })
})
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- test/ops-spider-state.test.mjs`

Expected: FAIL because the helper module does not exist.

- [x] **Step 3: Implement minimal pure helpers**

```js
export function resolveOpsSpiderState({ routeName = '', agentState = 'idle', inactiveMs = 0 }) {
  if (inactiveMs >= 30 * 60 * 1000) return 'sleeping'
  if (agentState === 'thinking') return 'thinking'
  if (routeName === 'InspectorCenter' || routeName === 'Connections') return 'observing'
  return 'idle'
}
```

- [x] **Step 4: Run the focused test to verify it passes**

Run: `npm test -- test/ops-spider-state.test.mjs`

Expected: PASS.

### Task 2: Pet Store And Topology Articulation

**Files:**
- Create: `frontend/src/stores/opsSpider.js`
- Modify: `frontend/src/components/common/KubernetesSpider.vue`
- Modify: `frontend/test/ops-spider-state.test.mjs`

**Interfaces:**
- `useOpsSpiderStore()` exposes `position`, `hidden`, `menuOpen`, `markActive()`, `sleep()`, `wake()`, `setCorner(corner)`, and `setPosition(position)`.
- `KubernetesSpider` accepts `pet: Boolean` without changing its existing default rendering.

- [x] **Step 1: Add a failing corner-placement test**

```js
test('chooses the requested corner without persisting a free-form coordinate', () => {
  assert.deepEqual(cornerPosition('top-left', { viewportWidth: 1024, viewportHeight: 768, size: 60, inset: 20 }), { x: 20, y: 20 })
})
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- test/ops-spider-state.test.mjs`

Expected: FAIL because `cornerPosition` does not exist.

- [x] **Step 3: Implement corner persistence and pet-only route articulation**

Keep `KubernetesSpider` defaults unchanged. Add `.spider--pet` route animation selectors with nonmatching durations and transform origins for each path. Disable those selectors in reduced motion.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `npm test -- test/ops-spider-state.test.mjs`

Expected: PASS.

### Task 3: Fixed Pet Interaction Surface

**Files:**
- Create: `frontend/src/components/common/OpsSpiderPet.vue`
- Modify: `frontend/test/ops-spider-state.test.mjs`

**Interfaces:**
- Props: `state`, `agentState`, `compact`.
- Emits: `navigate(route)`.
- Uses `useOpsSpiderStore` for location, sleep, menu, and hide state.

- [x] **Step 1: Add a failing compact-size test**

```js
test('keeps terminal priority with a compact Connections pet', () => {
  assert.equal(resolveOpsSpiderSize({ width: 1440, routeName: 'Connections' }), 52)
  assert.equal(resolveOpsSpiderSize({ width: 1440, routeName: 'Dashboard' }), 68)
})
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- test/ops-spider-state.test.mjs`

Expected: FAIL because `resolveOpsSpiderSize` does not exist.

- [x] **Step 3: Implement the orb, hover panel, radial navigation, free dragging, and context menu**

Render one fixed `<aside>` below modal layers. Use a labelled core button with `aria-expanded`; render four text-backed radial buttons and four context actions. Register pointer, keydown, visibility, and inactivity listeners in `onMounted`; remove all listeners and cancel animation frames in `onBeforeUnmount`. The hover panel states exactly `集群 未接入` and the supplied real Agent state.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `npm test -- test/ops-spider-state.test.mjs`

Expected: PASS.

### Task 4: AppShell Integration And Verification

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/test/ops-spider-state.test.mjs`

**Interfaces:**
- `MainLayout` passes route/Agent-derived state and uses `router.push` only in response to an emitted pet action.

- [x] **Step 1: Add a failing route-state test**

```js
test('uses observing state in Connections without changing the Agent route state', () => {
  assert.equal(resolveOpsSpiderState({ routeName: 'Connections', agentState: 'idle', inactiveMs: 0 }), 'observing')
})
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `npm test -- test/ops-spider-state.test.mjs`

Expected: FAIL until the route-state branch is implemented.

- [x] **Step 3: Integrate and preserve the organism hierarchy**

Place `<OpsSpiderPet>` after existing whale/jellyfish elements in `MainLayout`. Compute its state from the current route and current Agent state. Route emitted actions with `router.push`; do not trigger bridge APIs.

- [x] **Step 4: Run complete frontend verification**

Run: `npm run lint; npm run typecheck; npm test; npm run build`

Expected: all commands exit 0. Inspect desktop and mobile routes with reduced motion before reporting completion.
