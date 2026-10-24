# Vision Ops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a browser-safe, evidence-first Vision Ops sentinel that captures only after explicit user permission, detects deterministic operational anomalies locally, and routes evidence to the Ops Spider and Agent UI.

**Architecture:** Pure JavaScript detector and event aggregator modules sit below a Vue `VisionOpsView`. A capture adapter wraps `getDisplayMedia()` and is injectable for tests. The existing layout reads the vision state from the view/store boundary; no SSH, Agent execution, or cross-origin browser APIs are coupled to the detector.

**Tech Stack:** Vue 3, Vite, Pinia, browser Media Capture API, Canvas, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-21-vision-ops-design.md`

## Global Constraints

- Browser capture requires an explicit user gesture and secure context.
- Default processing is local-only and in-memory.
- No passwords, private keys, tokens, or passphrases may enter evidence text.
- `DETECTED`, `LIKELY`, and `CONFIRMED` must remain distinct.
- Existing SmartOps visual language and organisms must remain intact.
- No protocol or AI capability may be represented as real before its adapter exists.

## Review Focus

- Permission denied or capture track ended must leave no active timer or stream.
- Repeated 502 frames must update one event instead of creating a new event every second.
- OCR-like evidence containing secrets must be redacted before display or storage.
- A single red frame must not become a fault without temporal confirmation.
- Reduced motion must disable scan animation while preserving readable state.

### Task 1: Vision Domain Detector

**Files:**
- Create: `frontend/src/vision/visionTypes.js`
- Create: `frontend/src/vision/visionDetector.js`
- Create: `frontend/src/vision/visionAggregator.js`
- Test: `frontend/test/vision-detector.test.mjs`

**Interfaces:**
- `detectVisionFindings(input) -> VisionFinding[]`
- `VisionEventAggregator.observe(findings, now) -> VisionFaultEvent[]`
- `redactEvidence(text) -> string`

- [ ] Write failing tests for HTTP, terminal, Kubernetes, Docker, loading, redaction, confidence, debounce, and dedupe.
- [ ] Run `npm test -- --test-name-pattern vision` from `frontend`; confirm the new tests fail because the modules do not exist.
- [ ] Implement deterministic pattern matching, pixel heuristics, stable fingerprints, and a three-frame confirmation window.
- [ ] Run the focused tests and then the full frontend test suite.
- [ ] Commit with `feat: add vision ops detector and event aggregation`.

### Task 2: Browser Capture Adapter

**Files:**
- Create: `frontend/src/vision/browserCapture.js`
- Test: `frontend/test/vision-capture.test.mjs`

**Interfaces:**
- `createBrowserCaptureAdapter(mediaDevices = navigator.mediaDevices) -> VisionCaptureAdapter`
- `start({ video, canvas, fps, onFrame, onEnded }) -> Promise<void>`
- `stop() -> void`

- [ ] Write tests using injected `mediaDevices` and fake tracks for permission denial, stop, and ended events.
- [ ] Run focused tests and observe the expected failure.
- [ ] Implement explicit `getDisplayMedia({ video: true, audio: false })`, one sampling timer, canvas extraction, and full cleanup.
- [ ] Run focused tests and full frontend tests.
- [ ] Commit with `feat: add explicit browser vision capture adapter`.

### Task 3: Vision Ops View And Route

**Files:**
- Create: `frontend/src/views/vision/VisionOpsView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/components/common/opsSpiderState.js`
- Modify: `frontend/src/components/common/OpsSpiderPet.vue`

**Interfaces:**
- View owns capture lifecycle and exposes `visionState`, `latestEvent`, and in-memory timeline.
- `/vision` is the user-facing route and `VISION OPS` is a primary navigation entry.

- [ ] Add route/navigation/state tests for the new route and spider states.
- [ ] Implement Start/Pause/Stop, privacy disclosure, capability labels, evidence preview, timeline, and explicit Agent handoff.
- [ ] Wire route metadata to `SCANNING`, `ANOMALY`, and `ANALYZING` without changing existing route behavior.
- [ ] Add accessible labels, keyboard focus, reduced-motion CSS, and no persistent screenshot storage.
- [ ] Run frontend tests, lint, and build.
- [ ] Commit with `feat: add vision ops sentinel workspace`.

### Task 4: Verification And Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-21-vision-ops-design.md`
- Create: `docs/vision-ops.md`

- [ ] Run `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build` in `frontend`.
- [ ] Run the app and verify `/vision` at desktop and mobile widths, permission denied, stop, capture-ended, and reduced-motion states.
- [ ] Document REAL, PARTIAL, REQUIRES BRIDGE, and NOT IMPLEMENTED capabilities.
- [ ] Commit with `docs: document vision ops runtime boundaries`.
