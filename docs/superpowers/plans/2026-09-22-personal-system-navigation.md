# Personal System Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent, accessible multi-level Personal System navigation and direct-route previous/next page stepping for existing SmartOpsAgent routes without inventing unavailable Operation Library or Question Bank pages.

**Architecture:** A pure navigation registry declares groups, route names, labels, icons, and optional page flows. Pinia owns only sidebar/mobile visibility and persisted expanded-group ids; route-derived state always forces the active group open. `PersonalSystemNavigation` renders the tree and `PageStepper` consumes the same registry to route directly between actual sibling pages without coupling to browser history.

**Tech Stack:** Vue 3, Vue Router 4, Pinia 3, Element Plus icons, Node test runner, Playwright, Vite.

**Spec:** `docs/superpowers/specs/2026-09-22-personal-system-question-bank-design.md`

## Global Constraints

- This plan implements Stage A only: personal navigation and page stepping.
- Use only routes that exist in `frontend/src/router/index.js`; do not add a visible Operation Library, Training, Question Bank, Runbook, Incident, Storage, or Simulation route in this stage.
- The current `MEMORY` navigation label and `/inspector` routes remain unchanged until an actual Operation Library exists.
- Parent groups are one level deep, use real buttons with `aria-expanded`, persist only local group state, and automatically open for the active route.
- `PageStepper` uses named/direct routes and never calls `history.back()` or `history.forward()`.
- Page-step arrows never cross groups; they are disabled at the first/last route and unavailable for pages without an implemented flow sibling.
- Arrow-key navigation is disabled while focus is in an editable element, a select, a dialog, or embedded viewer.
- No change to Spider, Vision, OCR, CV, Knowledge search behavior, Agent behavior, SSH, Terminal, command execution, browser-launch behavior, or backend APIs.
- Preserve current desktop/sidebar behavior outside the navigation surface, and keep mobile navigation closed by default without covering page controls.

## Review Focus

- A deep-linked Inspector or Agent route must open its parent group even when persisted storage says it is collapsed; Task 2 tests the route-overrides-storage behavior.
- Corrupt or stale local storage must not prevent navigation rendering or expose a group that no longer exists; Task 2 tests sanitization.
- A next/previous action must never use browser history or navigate outside its declared flow; Task 3 tests route name results and both boundaries.
- Left/right keys in a search field, textarea, select, modal/dialog, or embedded viewer must retain their normal behavior; Task 4 tests the eligibility guard.
- On mobile, the menu panel must be closed initially, expose `aria-expanded`, close after selecting a link, and not cause horizontal overflow; Tasks 5 and 6 verify the interaction and browser layout.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `frontend/src/navigation/personalSystemNavigation.js` | Pure, immutable route/group/flow registry and route lookup helpers. |
| `frontend/src/navigation/navigationState.js` | Pure persisted-group state sanitizer and active-route expansion resolver. |
| `frontend/src/navigation/pageFlow.js` | Pure previous/next lookup and keyboard-eligibility logic. |
| `frontend/src/stores/app.js` | Holds sidebar/mobile visibility and expanded Personal System groups; delegates persistence/sanitization to navigation helpers. |
| `frontend/src/components/navigation/PersonalSystemNavigation.vue` | Accessible desktop/mobile tree navigation driven by the registry. |
| `frontend/src/components/navigation/PageStepper.vue` | Accessible direct-route previous/next controls driven by the flow registry. |
| `frontend/src/layouts/MainLayout.vue` | Composes navigation and stepper around existing shell; retains organism components and existing tool menu. |
| `frontend/src/assets/styles/global.css` | Defines mobile panel behavior and prevents closed navigation from occupying space. |
| `frontend/src/router/index.js` | Adds stable group/flow metadata to existing named routes only. |

### Task 1: Pure Personal System Route Registry

**Files:**
- Create: `frontend/src/navigation/personalSystemNavigation.js`
- Test: `frontend/test/personal-system-navigation.test.mjs`

**Interfaces:**
- Produces immutable `personalSystemGroups` with group ids, bilingual labels, Element Plus icon names, direct routes, and at most one child level.
- Produces `findPersonalSystemGroup(routeName)`, `isRouteInPersonalSystem(routeName)`, and `visiblePersonalSystemGroups()` for components and state logic.
- Does not import Vue, Pinia, Router, browser APIs, or components.

- [ ] **Step 1: Write the failing route registry test.**

```js
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  findPersonalSystemGroup,
  personalSystemGroups,
  visiblePersonalSystemGroups
} from '../src/navigation/personalSystemNavigation.js'

test('maps Inspector statistics to the existing Memory parent group', () => {
  const group = findPersonalSystemGroup('InspectorStatistics')

  assert.equal(group.id, 'memory')
  assert.equal(group.label, 'MEMORY')
  assert.deepEqual(group.children.map(item => item.routeName), [
    'InspectorCenter',
    'InspectorStatistics'
  ])
})

test('contains only groups with existing direct routes', () => {
  assert.deepEqual(visiblePersonalSystemGroups(personalSystemGroups).map(group => group.id), [
    'home', 'knowledge', 'connections', 'operations', 'agent', 'memory'
  ])
})
```

The production break this protects is a navigation entry pointing at an unimplemented route or a deep Inspector page no longer revealing its parent group.

- [ ] **Step 2: Run the test and verify it fails because the registry is absent.**

Run: `npm test -- test/personal-system-navigation.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND` for `personalSystemNavigation.js`.

- [ ] **Step 3: Add the registry and lookup helpers.**

```js
export const personalSystemGroups = Object.freeze([
  Object.freeze({
    id: 'home', label: 'HOME', cn: '首页', icon: 'HomeFilled',
    routeName: 'Dashboard', to: '/', children: Object.freeze([])
  }),
  Object.freeze({
    id: 'agent', label: 'AGENT', cn: '智能体', icon: 'Cpu',
    routeName: 'AgentCommandCenter', to: '/agent',
    children: Object.freeze([
      Object.freeze({ label: 'COMMAND CENTER', cn: '控制中心', routeName: 'AgentCommandCenter', to: '/agent' }),
      Object.freeze({ label: 'EXECUTION TRACE', cn: '执行轨迹', routeName: 'ExecutionTrace', to: '/agent/trace' })
    ])
  })
])

export function findPersonalSystemGroup(routeName) {
  return personalSystemGroups.find(group =>
    group.routeName === routeName || group.children.some(child => child.routeName === routeName)
  ) || null
}
```

Use the existing route names exactly: `Dashboard`, `Knowledge`, `Connections`, `ServerList`, `AgentCommandCenter`, `ExecutionTrace`, `InspectorCenter`, and `InspectorStatistics`. Make only `agent` and `memory` expandable in Stage A; direct groups have an empty `children` array. Keep `InspectorDetail` routed and reachable but exclude it from the top-level list and PageStepper until an operation-detail flow exists.

- [ ] **Step 4: Run the focused test and full frontend unit suite.**

Run: `npm test -- test/personal-system-navigation.test.mjs`

Expected: PASS.

Run: `npm test`

Expected: PASS.

- [ ] **Step 5: Commit the pure registry.**

```powershell
git add frontend/src/navigation/personalSystemNavigation.js frontend/test/personal-system-navigation.test.mjs
git commit -m "feat: define personal system navigation"
```

### Task 2: Persisted Expansion And Route-Derived State

**Files:**
- Create: `frontend/src/navigation/navigationState.js`
- Modify: `frontend/src/stores/app.js`
- Test: `frontend/test/navigation-state.test.mjs`

**Interfaces:**
- Produces `sanitizeExpandedGroupIds(value, groups)`, `resolveExpandedGroupIds(routeName, persistedIds, groups)`, and `toggleExpandedGroupId(groupId, expandedIds, groups)`.
- Extends `useAppStore()` with `mobileNavigationOpen`, `expandedPersonalSystemGroups`, `setRouteNavigation(routeName)`, `togglePersonalSystemGroup(groupId)`, `openMobileNavigation()`, and `closeMobileNavigation()`.
- Uses existing `getStorage`/`setStorage` with key `personal_system_navigation`; it does not save route history or unrelated sidebar state.

- [ ] **Step 1: Write the failing state tests.**

```js
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  resolveExpandedGroupIds,
  sanitizeExpandedGroupIds,
  toggleExpandedGroupId
} from '../src/navigation/navigationState.js'
import { personalSystemGroups } from '../src/navigation/personalSystemNavigation.js'

test('forces the active Agent parent open when persisted state is empty', () => {
  assert.deepEqual(
    resolveExpandedGroupIds('ExecutionTrace', [], personalSystemGroups),
    ['agent']
  )
})

test('drops malformed and stale persisted navigation groups', () => {
  assert.deepEqual(
    sanitizeExpandedGroupIds(['agent', 'question-bank', 42, 'agent'], personalSystemGroups),
    ['agent']
  )
})

test('does not collapse the group that owns the current route', () => {
  assert.deepEqual(
    toggleExpandedGroupId('memory', ['memory'], personalSystemGroups, 'InspectorCenter'),
    ['memory']
  )
})
```

The production breaks are a stale `localStorage` value crashing navigation, a direct deep link hiding its parent, or a user collapsing the only visible route context.

- [ ] **Step 2: Run tests to verify the new state module is absent.**

Run: `npm test -- test/navigation-state.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND` for `navigationState.js`.

- [ ] **Step 3: Implement state sanitization and Pinia integration.**

```js
export function sanitizeExpandedGroupIds(value, groups) {
  const expandable = new Set(groups.filter(group => group.children.length > 0).map(group => group.id))
  return [...new Set(Array.isArray(value) ? value.filter(id => typeof id === 'string' && expandable.has(id)) : [])]
}

export function resolveExpandedGroupIds(routeName, persistedIds, groups) {
  const parent = findPersonalSystemGroup(routeName)
  const expanded = sanitizeExpandedGroupIds(persistedIds, groups)
  return parent?.children.length && !expanded.includes(parent.id) ? [...expanded, parent.id] : expanded
}
```

Initialize `expandedPersonalSystemGroups` from `getStorage('personal_system_navigation')` and sanitize it. `setRouteNavigation(routeName)` resolves the parent state and persists only if the list changes. `togglePersonalSystemGroup` receives the current route name from the layout so it cannot hide that route's group. Mobile state is in-memory only and always starts `false` after a refresh.

- [ ] **Step 4: Run focused and full frontend tests.**

Run: `npm test -- test/navigation-state.test.mjs`

Expected: PASS.

Run: `npm test`

Expected: PASS.

- [ ] **Step 5: Commit the state boundary.**

```powershell
git add frontend/src/navigation/navigationState.js frontend/src/stores/app.js frontend/test/navigation-state.test.mjs
git commit -m "feat: persist personal navigation state"
```

### Task 3: Page Flow Registry And Direct-Route Step Resolution

**Files:**
- Create: `frontend/src/navigation/pageFlow.js`
- Test: `frontend/test/page-flow.test.mjs`

**Interfaces:**
- Produces immutable `pageFlows`, `resolvePageStep(routeName)`, `previousPageStep(routeName)`, `nextPageStep(routeName)`, and `isPageStepperKeyEligible(target)`.
- Initial flows contain only existing, parameter-free siblings: `agent` (`AgentCommandCenter`, `ExecutionTrace`) and `memory` (`InspectorCenter`, `InspectorStatistics`).
- Returns `null` for `Knowledge`, `InspectorDetail`, server details, login, and unknown routes.

- [ ] **Step 1: Write failing page-flow tests.**

```js
import assert from 'node:assert/strict'
import test from 'node:test'
import { nextPageStep, previousPageStep, resolvePageStep } from '../src/navigation/pageFlow.js'

test('returns direct sibling routes instead of a browser-history target', () => {
  assert.deepEqual(nextPageStep('AgentCommandCenter'), {
    routeName: 'ExecutionTrace', to: '/agent/trace', label: 'EXECUTION TRACE'
  })
  assert.equal(previousPageStep('AgentCommandCenter'), null)
})

test('keeps inspector detail out of an incomplete operation flow', () => {
  assert.equal(resolvePageStep('InspectorDetail'), null)
})
```

The production break is an arrow accidentally navigating through a previous browser location, across a group, or into a parameterized detail page without a valid id.

- [ ] **Step 2: Run tests to verify the flow module is absent.**

Run: `npm test -- test/page-flow.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND` for `pageFlow.js`.

- [ ] **Step 3: Implement explicit route flows and keyboard eligibility.**

```js
export const pageFlows = Object.freeze([
  Object.freeze({
    id: 'agent',
    steps: Object.freeze([
      Object.freeze({ routeName: 'AgentCommandCenter', to: '/agent', label: 'COMMAND CENTER' }),
      Object.freeze({ routeName: 'ExecutionTrace', to: '/agent/trace', label: 'EXECUTION TRACE' })
    ])
  }),
  Object.freeze({
    id: 'memory',
    steps: Object.freeze([
      Object.freeze({ routeName: 'InspectorCenter', to: '/inspector', label: 'INSPECTOR CENTER' }),
      Object.freeze({ routeName: 'InspectorStatistics', to: '/inspector/statistics', label: 'STATISTICS' })
    ])
  })
])

export function isPageStepperKeyEligible(target) {
  const tag = target?.tagName?.toLowerCase()
  return !target?.isContentEditable && !['input', 'textarea', 'select', 'dialog', 'iframe'].includes(tag)
}
```

`resolvePageStep` returns `{ flow, index, current, previous, next }` or `null`. `previousPageStep` and `nextPageStep` return only exact step objects or `null`; they never construct paths from text or route parameters.

- [ ] **Step 4: Add and run keyboard eligibility cases.**

```js
test('does not capture arrow keys from editable or embedded controls', () => {
  assert.equal(isPageStepperKeyEligible({ tagName: 'INPUT', isContentEditable: false }), false)
  assert.equal(isPageStepperKeyEligible({ tagName: 'TEXTAREA', isContentEditable: false }), false)
  assert.equal(isPageStepperKeyEligible({ tagName: 'IFRAME', isContentEditable: false }), false)
  assert.equal(isPageStepperKeyEligible({ tagName: 'BUTTON', isContentEditable: false }), true)
})
```

Run: `npm test -- test/page-flow.test.mjs`

Expected: PASS.

- [ ] **Step 5: Commit the route-flow contract.**

```powershell
git add frontend/src/navigation/pageFlow.js frontend/test/page-flow.test.mjs
git commit -m "feat: define direct page flows"
```

### Task 4: Accessible Navigation And Stepper Components

**Files:**
- Create: `frontend/src/components/navigation/PersonalSystemNavigation.vue`
- Create: `frontend/src/components/navigation/PageStepper.vue`
- Create: `frontend/src/components/navigation/pageStepper.js`
- Test: `frontend/test/page-stepper.test.mjs`
- Test: `frontend/test/personal-system-component.test.mjs`

**Interfaces:**
- `PersonalSystemNavigation` receives `groups`, `expandedGroupIds`, `currentRouteName`, and `mobileOpen`; emits `toggle-group`, `navigate`, and `close-mobile`.
- `PageStepper` receives `routeName`; it calls `router.push({ name: step.routeName })` only in response to its own button or eligible `Alt+ArrowLeft` / `Alt+ArrowRight` user event.
- `pageStepper.js` produces `stepperView(routeName)` for component display and tests, with `{ current, previous, next }` values from Task 3.

- [ ] **Step 1: Write failing pure component-view tests.**

```js
import assert from 'node:assert/strict'
import test from 'node:test'
import { stepperView } from '../src/components/navigation/pageStepper.js'

test('disables the previous button at the first direct Agent step', () => {
  const view = stepperView('AgentCommandCenter')
  assert.equal(view.previous.disabled, true)
  assert.equal(view.next.label, 'EXECUTION TRACE')
})

test('hides a stepper view for routes without an implemented sibling flow', () => {
  assert.equal(stepperView('Knowledge'), null)
})
```

`personal-system-component.test.mjs` uses the pure registry and state helpers to assert a group with children exposes an `expanded` boolean and direct groups never expose a toggle state. Do not snapshot Vue markup or assert framework internals.

- [ ] **Step 2: Run tests to verify the view helper is absent.**

Run: `npm test -- test/page-stepper.test.mjs test/personal-system-component.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND` for `pageStepper.js`.

- [ ] **Step 3: Implement `PersonalSystemNavigation.vue`.**

Render direct groups as `RouterLink`. Render expandable groups with a parent `RouterLink` and a separate icon-only `button` with `aria-label="Expand AGENT navigation"` or `aria-label="Collapse AGENT navigation"`, `aria-controls`, and boolean `aria-expanded`. Child links render only while expanded. Add a visible focused state and a 44px minimum mobile hit target.

When a child or direct link is selected, emit `navigate` and `close-mobile`; do not mutate Pinia inside the component. For desktop, child items appear indented below their parent without a card/container inside a card. For mobile, provide an `aside` panel with `aria-hidden` when closed and trap no focus while closed; MainLayout owns focus movement to the first navigation link after explicit opening.

- [ ] **Step 4: Implement `PageStepper.vue` and its helper.**

Render no markup when `stepperView(routeName)` returns `null`. Otherwise render previous/next icon buttons using Element Plus `ArrowLeft` and `ArrowRight`, with `disabled` attributes at flow boundaries and descriptive `title`/`aria-label` text. The center label includes the current group and step label. Register the keydown listener on mount and remove it on unmount; react only to `Alt+ArrowLeft` and `Alt+ArrowRight`, no modifiers beyond Alt, eligible targets from Task 3, and available steps.

```js
function move(step) {
  if (step && !step.disabled) router.push({ name: step.routeName })
}
```

The component must not import `window.history`, `opsSpiderState`, operation APIs, Agent APIs, or browser-search code.

- [ ] **Step 5: Run focused and full frontend tests.**

Run: `npm test -- test/page-stepper.test.mjs test/personal-system-component.test.mjs`

Expected: PASS.

Run: `npm test`

Expected: PASS.

- [ ] **Step 6: Commit the components.**

```powershell
git add frontend/src/components/navigation frontend/test/page-stepper.test.mjs frontend/test/personal-system-component.test.mjs
git commit -m "feat: add personal navigation controls"
```

### Task 5: Compose Navigation In Existing Layout And Routes

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/assets/styles/global.css`
- Test: `frontend/test/main-layout-navigation.test.mjs`

**Interfaces:**
- MainLayout imports registry/components and calls `appStore.setRouteNavigation(route.name)` in a route watcher with `{ immediate: true }`.
- Existing route records gain only stable `meta.personalGroup` and `meta.pageFlow` values that match Task 1/Task 3 identifiers.
- MainLayout closes mobile navigation after each `PersonalSystemNavigation` navigation event.

- [ ] **Step 1: Write a failing layout integration test against route metadata and pure state.**

```js
import assert from 'node:assert/strict'
import test from 'node:test'
import { routeMetaFor } from '../src/navigation/personalSystemNavigation.js'

test('assigns the execution trace to the Agent group and direct page flow', () => {
  assert.deepEqual(routeMetaFor('ExecutionTrace'), {
    personalGroup: 'agent',
    pageFlow: 'agent'
  })
})

test('keeps inspector detail outside the incomplete memory page flow', () => {
  assert.deepEqual(routeMetaFor('InspectorDetail'), {
    personalGroup: 'memory',
    pageFlow: null
  })
})
```

The production breaks are inconsistent string identifiers between routes, sidebar grouping, and stepper logic, or moving a parameterized detail route into a flow that lacks its id.

- [ ] **Step 2: Run the test to verify route metadata helper behavior is missing.**

Run: `npm test -- test/main-layout-navigation.test.mjs`

Expected: failure because `routeMetaFor` is not exported until the registry is extended.

- [ ] **Step 3: Extend the registry and router route meta.**

Add `routeMetaFor(routeName)` to Task 1's registry, using a hand-maintained route-name map derived from the group/flow registry. In `router/index.js`, add `meta: { personalGroup: 'agent', pageFlow: 'agent' }` to `AgentCommandCenter` and `ExecutionTrace`; add `personalGroup: 'memory'` to Inspector pages, with `pageFlow: 'memory'` only for `InspectorCenter` and `InspectorStatistics`. Add group metadata for all other existing top-level Personal System routes, with `pageFlow: null`.

Refactor `MainLayout.vue` to remove the local `primaryNav` array, import `personalSystemGroups`, render `<PersonalSystemNavigation>`, and keep `systemNav`/tools menu unchanged. Replace the mobile menu `toggleSidebar()` action with an explicit `appStore.toggleMobileNavigation()` at mobile breakpoint; desktop collapse behavior continues to use `toggleSidebar()`. Add `<PageStepper :route-name="route.name?.toString()" />` above `<RouterView />` inside `main`.

- [ ] **Step 4: Add scoped/global CSS for the desktop tree and mobile panel.**

Keep mobile panel positioning within the document below the top bar rather than `position: fixed`, so it cannot overlay active page controls when closed. Use a constrained height with `overflow-y: auto` when open. Preserve the existing 767px breakpoint, existing content padding, and default no-horizontal-overflow behavior. Do not alter organism z-index ownership.

- [ ] **Step 5: Run targeted tests, lint/typecheck, and build.**

Run: `npm test -- test/main-layout-navigation.test.mjs`

Expected: PASS.

Run: `npm test`

Expected: PASS.

Run: `npm run lint`

Expected: PASS.

Run: `npm run typecheck`

Expected: PASS.

Run: `npm run build`

Expected: PASS.

- [ ] **Step 6: Commit layout integration.**

```powershell
git add frontend/src/layouts/MainLayout.vue frontend/src/router/index.js frontend/src/assets/styles/global.css frontend/src/navigation/personalSystemNavigation.js frontend/test/main-layout-navigation.test.mjs
git commit -m "feat: add hierarchical personal navigation"
```

### Task 6: Browser Verification And Regression Documentation

**Files:**
- Create: `frontend/test/personal-navigation-visual-check.mjs`
- Modify: `frontend/package.json`
- Modify: `README.md`

**Interfaces:**
- Produces `npm run personal-navigation-check` that runs standalone Playwright assertions against the already-running Vite server.
- Does not modify `frontend/test/visual-check.mjs`, which currently contains unrelated uncommitted login assertions.

- [ ] **Step 1: Write the browser check script with controlled user-visible assertions.**

```js
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: process.env.SMARTOPS_BROWSER_PATH, headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'visual-test' })))
  await page.goto('http://127.0.0.1:5173/agent', { waitUntil: 'networkidle' })
  assert.equal(await page.getByRole('button', { name: /collapse agent navigation/i }).getAttribute('aria-expanded'), 'true')
  await page.getByRole('button', { name: /next page: execution trace/i }).click()
  assert.match(page.url(), /\/agent\/trace$/)
  assert.equal(await page.getByRole('button', { name: /next page/i }).isDisabled(), true)
} finally {
  await browser.close()
}
```

Extend the script with a 375px viewport: verify the mobile navigation is initially closed, open it through the menu button, verify `aria-expanded="true"`, choose Execution Trace, confirm panel closure, and assert `document.documentElement.scrollWidth <= window.innerWidth`. Screenshot only test artifacts under ignored `frontend/test-artifacts/`.

- [ ] **Step 2: Run the browser check and correct interaction/layout failures.**

Run: `npm run personal-navigation-check`

Expected: PASS on desktop and 375px mobile viewports, with direct stepper navigation and no horizontal overflow.

If this fails, invoke `systematic-debugging` before changing implementation code. Preserve the unrelated `visual-check.mjs` modification rather than folding it into this work.

- [ ] **Step 3: Document Stage A behavior and deferred module boundaries.**

Document current expandable groups, direct page flows, keyboard shortcut (`Alt+Left`/`Alt+Right`), editable-control exclusion, local expansion storage, and the fact that Question Bank and Operation Library links are intentionally absent until their dedicated stages. Do not document storage management, question answering, or simulation as available.

- [ ] **Step 4: Run final full verification.**

Run: `npm test`

Expected: PASS.

Run: `npm run lint`

Expected: PASS.

Run: `npm run typecheck`

Expected: PASS.

Run: `npm run build`

Expected: PASS.

Run: `npm run personal-navigation-check`

Expected: PASS.

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 5: Commit verification and documentation.**

```powershell
git add frontend/test/personal-navigation-visual-check.mjs frontend/package.json README.md
git commit -m "docs: verify personal navigation"
```

## Plan Self-Review

- Spec coverage: Task 1 defines current one-level hierarchy; Task 2 persists/derives expansion; Task 3 defines direct sibling flow and editable-key exclusion; Task 4 creates accessible controls; Task 5 integrates current routes and mobile behavior; Task 6 verifies desktop/mobile behavior and documents the intentional Stage A scope. Knowledge relations, Question Bank learning, and Production Simulation are excluded as separate Stage B-D plans, matching the delivery sequence.
- Placeholder scan: no unresolved `TBD`, `TODO`, or deferred implementation instruction appears in task steps. Stage boundaries are explicit product scope, not missing task details.
- Type consistency: `personalSystemGroups`, `findPersonalSystemGroup`, `routeMetaFor`, `resolveExpandedGroupIds`, `toggleExpandedGroupId`, `pageFlows`, `resolvePageStep`, `stepperView`, `PersonalSystemNavigation`, and `PageStepper` use one name/signature across all tasks.
- Review focus coverage: Task 2 tests deep links and malformed storage; Task 3 tests flow boundaries and editable-key exclusion; Task 5 tests consistent metadata; Task 6 tests mobile closed/open state, selection closure, desktop direct navigation, and overflow.
