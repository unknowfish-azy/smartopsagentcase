# Vision Ops Design

## Scope

Vision Ops is a browser-safe visual operations sentinel for SmartOpsAgent. It observes a user-authorized display stream, samples frames locally, detects operational fault patterns, emits evidence-first fault events, and exposes those events to the Ops Spider and Agent UI. It does not silently capture screens, read cross-origin DOM, or execute remote operations.

## Runtime Audit

- Current runtime: Vue 3 + Vite in the browser, with Spring Boot services.
- Existing visual organisms: Ops Spider, Jellyfish, Whale, Stellar Ocean.
- Existing Agent/Knowledge: Agent command center, inspector/evidence pipeline, Python Knowledge service.
- Existing CV/OCR: no frontend capture or detector; backend OCR is optional ingestion support and is not a screen observer.
- Native bridge: none detected. Continuous window/display capture therefore remains unavailable until Electron/Tauri/Wails is added.

## First Real Slice

1. User clicks Start Vision.
2. Browser `getDisplayMedia()` requests explicit display/window/tab permission.
3. A local `video` + `canvas` sampler runs at 1 FPS by default and stops on permission denial, track end, or user stop.
4. The detector combines optional OCR text with deterministic patterns for HTTP errors, terminal/Kubernetes/Docker failures, loading-stuck hints, blank-screen hints, and red-alert pixel ratio.
5. Consecutive matching frames are debounced and deduplicated into a `VisionFaultEvent` with `DETECTED | LIKELY | CONFIRMED` evidence level, severity, confidence, bounding region, and redacted evidence text.
6. The UI shows the latest evidence, a timeline, privacy state, and an explicit Agent handoff. No operation is executed automatically.

## Domain Interfaces

`VisionCaptureAdapter` owns browser capture and exposes `start`, `stop`, `onFrame`, `onEnded`.

`VisionDetector` is pure and receives `{ frameStats, ocrText, now }`; it returns zero or more detector findings.

`VisionEventAggregator` owns temporal debounce and fingerprint dedupe.

`VisionPrivacyPolicy` owns capture mode, local-only processing, retention, and redaction rules.

## State Model

`OFF → REQUESTING → OBSERVING → SCANNING → ANOMALY → ANALYZING → STOPPED`.

`PERMISSION_DENIED`, `CAPTURE_ENDED`, and `ERROR` are terminal states for a run and are visible to the user. `CONFIRMED` is an evidence level, not an automatic action state.

## Privacy

- No capture starts without a user gesture.
- Default processing is local-only.
- No frame is persisted by default; the UI keeps only the latest in-memory evidence preview.
- OCR text is redacted for password/token/private-key patterns before event creation.
- Native continuous capture, remote vision models, and persistent evidence storage are explicit future capabilities.

## Testing

Pure detector and aggregator tests cover 404/500/502/503/504, timeout/refused, terminal/Kubernetes/Docker signals, loading/blank heuristics, redaction, confidence levels, debounce, and fingerprint dedupe. Browser capture tests cover permission denial and ended tracks through adapter injection; UI build/lint and route smoke checks cover integration.

## Non-goals For This Slice

- OCR engine installation or pretending OCR is available.
- Cross-origin DOM, cookies, localStorage, or console access.
- Automatic Agent commands or remote remediation.
- Electron/Tauri native capture.
