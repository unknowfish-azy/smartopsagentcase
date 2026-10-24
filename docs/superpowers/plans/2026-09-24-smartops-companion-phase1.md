# SmartOps Companion Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 Companion foundation that unifies events, operational context, role states, attention policy, and the existing Smart Inquiry flow without enabling remote execution.

**Architecture:** Add a small framework-agnostic Companion domain layer and Pinia adapter. Existing Ops Spider and Smart Inquiry consume the adapter through events and context snapshots; future VisualOps and Remote Operations will use the same contracts.

**Tech Stack:** Vue 3, Pinia, Vite, ES modules, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-23-smartops-companion-architecture-design.md`

## Global Constraints

- Phase 1 only observes, builds context, asks questions, retrieves knowledge, and recommends; it does not execute remote or destructive operations.
- `executionAllowed` remains `false` on every path.
- Spider submits observations and Fault Events; it does not infer repairs or call tools.
- Jellyfish separates Observed, Inferred, Hypothesis, and Recommendation.
- Knowledge results include source, section, matched evidence, and risk.
- Event payloads are immutable snapshots and carry `id`, `type`, `timestamp`, `source`, and `contextId`.
- Existing `FaultEvent`, `InvestigationContext`, `SmartInquiryDrawer`, and `searchKnowledgeEntries` remain compatible.

## Review Focus

- Duplicate event listeners must not receive events after unsubscribe; test in Task 1.
- A malformed event or evidence-free fault must be rejected without corrupting the active context; test in Task 2.
- Repeated answers and knowledge references must update existing records rather than duplicate them; test in Task 2.
- Attention policy must suppress ordinary notifications in Focus/Quiet while allowing critical visual hints; test in Task 3.
- AI/knowledge degradation must remain visible and preserve read-only investigation; test in Task 3.

### Task 1: Companion Event Bus

**Files:**
- Create: `frontend/src/domain/companion/eventBus.js`
- Test: `frontend/test/companion-event-bus.test.mjs`

**Interfaces:**
- Produces `createCompanionEvent({ type, source, contextId, payload })`, `createCompanionEventBus()`, `bus.subscribe(type, handler)`, `bus.publish(event)`, and `bus.clear()`.
- `publish` delivers a frozen event snapshot; `subscribe` returns an unsubscribe function.

- [ ] **Step 1: Write failing tests** for event metadata, frozen payloads, filtering by type, unsubscribe, and malformed event rejection.
- [ ] **Step 2: Run `node --test test/companion-event-bus.test.mjs`** and confirm failures for missing exports.
- [ ] **Step 3: Implement the bus** with a `Map<string, Set<Function>>`, cloned/frozen payloads, ISO timestamps, and explicit validation of type/source/contextId.
- [ ] **Step 4: Re-run the focused test** and confirm all cases pass.
- [ ] **Step 5: Commit** `feat: add companion event bus`.

### Task 2: Companion Context and Pinia Adapter

**Files:**
- Create: `frontend/src/domain/companion/context.js`
- Create: `frontend/src/domain/companion/state.js`
- Create: `frontend/src/stores/companion.js`
- Modify: `frontend/src/stores/investigation.js`
- Test: `frontend/test/companion-context.test.mjs`

**Interfaces:**
- `createCompanionContext(input)`, `mergeCompanionContext(context, patch)`, and `snapshotCompanionContext(context)`.
- `useCompanionStore()` exposes `context`, `states`, `attentionPolicy`, `publish`, `ingestFault`, `recordAnswer`, `addKnowledgeReference`, and `setCapabilityStatus`.
- The store delegates investigation records to existing models and keeps `executionAllowed: false`.

- [ ] **Step 1: Write failing tests** for default context shape, Fault Event ingestion, immutable snapshots, answer/reference deduplication, and execution denial.
- [ ] **Step 2: Run the focused test** and confirm failures.
- [ ] **Step 3: Implement context constructors and merge helpers** with arrays for observations, evidence, questions, answers, hypotheses, recommendations, knowledge references, and capability statuses.
- [ ] **Step 4: Implement role state constants** for Spider, Jellyfish, Whale, and interaction modes.
- [ ] **Step 5: Implement the Pinia adapter** and bridge `smartops:fault-detected` into `ingestFault` without replacing the existing investigation store.
- [ ] **Step 6: Re-run focused tests** and then existing investigation tests.
- [ ] **Step 7: Commit** `feat: add companion context and state store`.

### Task 3: Attention Policy and Graceful Degradation

**Files:**
- Create: `frontend/src/domain/companion/attention.js`
- Modify: `frontend/src/stores/companion.js`
- Test: `frontend/test/companion-attention.test.mjs`

**Interfaces:**
- `resolveAttention({ severity, confidence, duration, businessImpact, userMode, incidentState })` returns `silent`, `visual_hint`, `badge`, `panel`, or `urgent_notice`.
- `setCapabilityStatus(name, status, detail)` records `available`, `degraded`, or `offline` without changing execution permission.

- [ ] **Step 1: Write failing tests** for Normal, Focus, Quiet, critical severity, and degraded AI/knowledge/visual capabilities.
- [ ] **Step 2: Run the focused test** and confirm failures.
- [ ] **Step 3: Implement deterministic attention rules**: low impact is suppressed in Focus/Quiet, critical events retain a visual hint, and no rule opens a remote operation.
- [ ] **Step 4: Add capability status to CompanionContext** and expose a read-only status getter for UI.
- [ ] **Step 5: Re-run focused tests** and confirm degradation never fabricates a recommendation or recovery.
- [ ] **Step 6: Commit** `feat: add companion attention and degradation policy`.

### Task 4: Integrate Spider and Smart Inquiry

**Files:**
- Modify: `frontend/src/components/common/OpsSpiderPet.vue`
- Modify: `frontend/src/components/investigation/SmartInquiryDrawer.vue`
- Create: `frontend/src/components/companion/CompanionStatus.vue`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Test: `frontend/test/companion-integration.test.mjs`

**Interfaces:**
- Spider publishes `FAULT_DETECTED` and `USER_CLICKED_SPIDER` through the Companion store/event bus.
- Smart Inquiry reads the context snapshot, records answers/references through the store, and never calls Remote Operations.
- `CompanionStatus` renders role state and capability degradation without creating a dashboard.

- [ ] **Step 1: Write failing integration tests** for a fault event opening Smart Inquiry, preserving evidence, recording a user answer, and showing a read-only safety state.
- [ ] **Step 2: Run the focused integration test** and confirm failures.
- [ ] **Step 3: Replace direct cross-component fault handling** with Companion store/event publishing while keeping existing investigation behavior compatible.
- [ ] **Step 4: Add minimal status rendering** for Spider/Jellyfish/Whale state and capability degradation.
- [ ] **Step 5: Verify close/reopen behavior** preserves investigation history and does not create a second context.
- [ ] **Step 6: Run all frontend tests, build, lint, typecheck, and diff check.**
- [ ] **Step 7: Commit** `feat: connect companion foundation to inquiry UI`.

### Task 5: Phase 1 Verification and Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-23-smartops-companion-architecture-design.md` only if implementation decisions materially change the spec.
- Test: all existing `frontend/test/**/*.test.mjs`.

- [ ] **Step 1: Run `npm test`** and record the final test count and failures.
- [ ] **Step 2: Run `npm run build`** and confirm exit code 0; record any non-blocking chunk warnings.
- [ ] **Step 3: Run `npm run lint`, `npm run typecheck`, and `git diff --check`.**
- [ ] **Step 4: Review the diff** for accidental execution paths, invented infrastructure data, duplicate state ownership, and listener leaks.
- [ ] **Step 5: Commit final Phase 1 changes** with `feat: establish SmartOps Companion phase one foundation`.

## Self-review

- Spec coverage: all Phase 1 requirements map to Tasks 1–4; Task 5 verifies the complete boundary.
- No placeholders: every task names files, interfaces, focused tests, commands, and commit scope.
- Type consistency: event bus contracts feed the context store; the context store feeds the existing inquiry UI; no task depends on a later undefined interface.
- Execution safety: no task adds SSH, Shell, kubectl, Docker, database writes, or automatic approval.
