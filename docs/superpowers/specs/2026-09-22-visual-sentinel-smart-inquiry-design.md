# Visual Sentinel And Smart Inquiry Design

## Status And Scope

This design supersedes the capture-only direction in
`2026-09-21-vision-ops-design.md`. SmartOpsAgent will become an
evidence-first diagnostic system:

```text
Web page or screen
  -> Ops Spider Visual Sentinel
  -> FaultEvent
  -> Smart Inquiry
  -> InvestigationContext
  -> Senior Operations Knowledge Engine
  -> evidence-ranked hypotheses and recommendations
```

This work is read-only. It must not invoke SSH, Kubernetes, Docker,
databases, browser actions, or any command execution. The one browser-related
exception is an explicit user click on a search result or search command,
which may open the user's local browser to an external search URL. Neither
Spider, Smart Inquiry, Knowledge Search, nor an Agent may silently open a
browser, submit an external query, or navigate a tab. Agent analysis and
Remote Operations remain separate future consumers of an approved
investigation result.

## Delivery Sequence

### Release 1: Chromium Visual Sentinel

A Manifest V3 Chromium extension observes one user-authorized browser tab.
The extension is the only way to inspect arbitrary web pages. The existing
Vue application cannot access another page's DOM, accessibility tree, or
viewport without it.

- Content script: collects visible DOM and accessibility evidence, maintains
  a non-intrusive overlay, and maps page-relative regions to viewport regions.
- Service worker: owns tab permissions, screenshot requests, per-tab state,
  and messaging. It never uploads page content by default.
- Overlay: renders the draggable Ops Spider, alerts, short-lived location
  outlines, selection mode, and the investigation entry point.
- Pure detector modules: normalize evidence, match deterministic operational
  error rules, merge duplicate observations, and apply temporal debounce.

The content script reports a versioned `FaultEvent` through an adapter. A
fixture adapter lets the next release be built and tested before the
extension is available.

### Release 2: Smart Inquiry And Senior Operations Knowledge

The existing local Knowledge architecture is extended instead of duplicated.
Smart Inquiry consumes a `FaultEvent`, establishes the fault boundary, asks
the smallest next high-value question, retrieves cited local knowledge, and
assembles an `InvestigationContext`. It can run in the Vue application with
fixture or extension-backed events. The user may explicitly launch an external
browser search when local evidence and local knowledge are insufficient.

## Visual Sentinel

### Observation Modes

`OFF`, `OBSERVE`, `FOCUS`, `SCAN`, and `STOP` are explicit user-visible
states. `SCAN` performs a single current-viewport check. `FOCUS` analyzes a
user-drawn selection. `OBSERVE` samples incrementally and drops to passive
frequency when the page is stable.

Every observation uses a `PageObservationFrame`:

```text
timestamp, url, title, viewportWidth, viewportHeight, devicePixelRatio,
scrollX, scrollY, domEvidence, accessibilityEvidence, screenshotRegion
```

The detector prioritizes DOM, accessibility, visible text, and page structure;
then augments them with a user-authorized screenshot, OCR, and visual rules.
Network and console errors are included only when extension permissions make
them available. Screenshot regions and OCR are evidence sources, not the
sole source of truth.

### Overlay Contract

The Spider outer host owns `position: fixed` and its translation. Dragging
updates that translation only. The animated core, legs, nodes, and particles
are descendants and must not write the host transform. The overlay defaults to
the lower-right corner, can be dragged, resized, hidden, collapsed, and
expanded, and does not take page focus unless the user activates it.

Alerts are anchored to the detected region. Their outline, badge, and optional
leader line are short-lived, keyboard accessible, and must not block page
controls. Motion is reduced under `prefers-reduced-motion`.

### Evidence, Detection, And Events

Evidence is independently typed as `DOM`, `ACCESSIBILITY`, `OCR`, `VISUAL`,
`NETWORK`, or `CONSOLE`. OCR evidence contains text, confidence, bounding box,
source, and timestamp. Sensitive values are redacted before display,
persistence, or messaging.

`FaultEvent` is immutable evidence plus mutable lifecycle fields:

```text
id, fingerprint, type, severity, confidence, level, page, region,
evidence[], firstSeenAt, lastSeenAt, occurrenceCount, status
```

`level` progresses from `POTENTIAL` to `LIKELY` to `CONFIRMED` only after
consistent observations. The fingerprint combines normalized URL, error type,
region, and normalized text. Repeated events within the debounce window update
the existing event rather than creating an alert stream.

Version 1 recognizes HTTP 4xx/5xx, timeout, connection, authentication,
WebSocket, JavaScript, blank-page, loading-stuck, red-error-region, and
Kubernetes status errors such as `CrashLoopBackOff`, `ImagePullBackOff`,
`OOMKilled`, `Pending`, and `NotReady`.

### Privacy And Performance

The default scope is the current tab. Full-window or full-screen capture
requires a separate user action. Frames are processed locally and in memory;
full screenshots are not retained. Only the minimum redacted evidence region
may be retained after a user-visible save decision.

The extension must use throttled observation, hover debounce, region-first
analysis, workers for heavy processing, stable-content backoff, and automatic
frequency reduction. It must never OCR, capture, perform CV, or update UI on
every animation frame.

## Smart Inquiry

### State Machine

`IDLE -> STARTING -> COLLECTING -> WAITING_USER -> ANALYZING ->
SEARCHING_KNOWLEDGE -> REFINING -> READY`.

`RESOLVED`, `CANCELLED`, and `ERROR` are terminal states. State transitions
are recorded in the investigation timeline and cannot trigger remote actions.

### Question And Answer Models

An `InquiryQuestion` has `id`, `prompt`, `rationale`, `type`, `options`,
`priority`, `required`, `sourceEvidenceIds`, and `knowledgeReferenceIds`.
Supported types are single choice, multiple choice, text, number, boolean,
selection, confirmation, file, screenshot, terminal output, URL, time range,
service selection, and environment selection.

Questions are generated from fault evidence, prior answers, and cited
knowledge. The initial 502 flow asks persistence, recent configuration change,
and upstream availability before lower-value questions. A free-text answer
keeps its original value and may add a normalized value with explicit
confidence; it is never silently rewritten as fact.

The UI is an investigation drawer, not a general-purpose chat transcript.
It shows the finding, evidence, one prioritized question, its rationale,
knowledge references, hypotheses, and recommended diagnostic steps.

### Investigation Context

`InvestigationContext` owns the durable, structured diagnostic record:

```text
id, faultEvent, page, environment, blastRadius, observations, evidence,
questions, answers, knowledgeReferences, hypotheses, recommendations,
timeline, status, createdAt, updatedAt
```

The context has a single assertion vocabulary:
`FACT`, `OBSERVATION`, `EVIDENCE`, `INFERENCE`, `HYPOTHESIS`,
`RECOMMENDATION`, `ACTION`, and `RESULT`. `ACTION` in this release means a
proposed or user-reported step only; it never executes a command. `RESULT`
captures the outcome of an already completed, user-supplied check.

A hypothesis records confidence, supporting and contradicting evidence,
related knowledge, and the next best read-only check. This prevents a
suggested cause from appearing as an observed fact. Confidence ranks the
current evidence; it never represents a confirmed root cause without direct,
recorded proof.

The investigation starts by resolving blast radius and time:

- Scope: affected user cohort, API or page, service, instance, node, region,
  environment, and production versus non-production.
- Timeline: `FIRST_SEEN`, `DETECTED`, `ALERTED`, `CHANGE`, `DEPLOYMENT`,
  `CONFIG_CHANGE`, `FAILURE`, `MITIGATION`, `RECOVERY`, and `VERIFICATION`.
- Change correlation: a nearby deployment or configuration change is recorded
  as correlation, not causation, until supporting evidence confirms it.

The question selector prefers the lowest-risk question or observation that
produces the greatest information gain across competing hypotheses. It asks
one prioritized question at a time and stops at `RESOLVED`,
`ROOT_CAUSE_CONFIRMED`, `MITIGATED`, `INSUFFICIENT_EVIDENCE`,
`NEEDS_HUMAN`, `UNSAFE_TO_CONTINUE`, or `UNAVAILABLE`.

Investigation history is searchable and exportable as JSON or Markdown. An
export includes evidence, questions, answers, knowledge citations, hypotheses,
and recommendations, but never credentials, page secrets, or unredacted
screen content.

## Senior Operations Knowledge Engine

The Knowledge Engine is not a generic document repository. It stores and
relates the operational knowledge needed to identify a boundary, collect
evidence, validate a hypothesis, recommend a safe next step, verify recovery,
and improve future diagnosis. It is local-first, offline-capable, and shared
by the Knowledge Center, Smart Inquiry, Spider, and a future Agent through the
same deterministic search interface. Direct UI and Spider searches never
require an AI service.

### Knowledge Layers

The Engine exposes seven linked knowledge layers rather than a folder tree:

1. **Manuals** explain architecture and version-dependent behavior.
2. **Diagnosis Runbooks** define safe evidence collection, decision branches,
   expected and abnormal results, and the next check.
3. **Repair Runbooks** define mitigation, permanent remediation, verification,
   rollback, prerequisites, and risk. They are reference-only in this release.
4. **Incidents and Postmortems** retain real symptoms, timeline, evidence,
   confirmed root cause, contributing factors, resolution, and lessons.
5. **Evidence and Command Library** define what each signal means and how a
   read-only command can obtain it.
6. **Dependency Graph and Version Matrix** connect services, upstream
   dependencies, platforms, products, and behavior that differs by version.
7. **Anti-patterns and Common Mistakes** prevent unsafe shortcuts and known
   misdiagnoses, such as treating a 502 as proof that Nginx is down or using
   `chmod 777` for every permission failure.

The graph relates symptoms, services, platforms, versions, dependencies,
runbooks, incidents, commands, evidence, and anti-patterns. Categories remain
useful browse facets, not the sole organizational model.

### Data Model

Extend the existing `knowledge_domain`, `knowledge_base`, `knowledge_document`,
and `knowledge_chunk` model rather than introducing a parallel knowledge
database. Documents add `title`, `type`, `category`, `service`, `environment`,
`version`, `author`, `visibility`, `quality`, `sourceType`, `reviewStatus`,
and source provenance. Sections and chunks retain heading, position, tags,
service, platform, version range, and content hash.

Supported document types are `DOCUMENT`, `RUNBOOK`, `FAQ`, `INCIDENT`,
`COMMAND_REFERENCE`, `ARCHITECTURE`, `SOP`, and `POSTMORTEM`. Visibility is
`PUBLIC`, `INTERNAL`, `RESTRICTED`, or `SECRET`; callers without access cannot
receive secret content, excerpts, or metadata.

Runbooks parse into explicit sections: problem, symptoms, causes,
prerequisites, diagnosis, commands, expected result, abnormal result,
resolution, verification, rollback, risk, and notes. Commands are reference
text only, never executable controls.

Diagnosis and repair Runbooks are distinct types. Diagnosis does not recommend
mutation as its first step. Repair has explicit mitigation, permanent fix,
verification, rollback, and risk sections. Incident and Postmortem documents
also retain impact, detection, contributing factors, what went well, what went
wrong, action items, monitoring improvements, and Runbook improvement links.

Each `CommandReference` has `purpose`, `risk`, `readOnly`, `requiresRoot`,
`sideEffect`, `disruption`, `rollback`, `expectedOutput`, `abnormalOutput`,
`timeout`, `platform`, `version`, `service`, and `commandPurpose`. Risk is one
of `READ_ONLY`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, or `DESTRUCTIVE`.
Destructive or disruptive commands must show their risk, impact, prerequisites,
rollback, and verification. They are never executable from this product.

Evidence records `source`, `timestamp`, `confidence`, `rawValue`,
`normalizedValue`, `location`, and `collector`. Metric evidence retains host,
duration, trend, baseline, and relevant dimensions such as CPU user/system/IO
wait, available memory and swap, disk capacity and inode availability, or
connection count and activity. This preserves timeline and baseline context
instead of reducing evidence to claims such as "CPU is high".

Imports initially accept Markdown, TXT, and JSON. Parsing normalizes metadata,
sections, and chunks while preserving source path, content hash, version, and
position. Re-importing a matching source/path/hash updates, replaces, or
archives the existing document instead of duplicating it.

Built-in packs are production diagnosis references, not introductory tutorials.
Version 1 ships curated Docker, MySQL, Nginx, Ubuntu, and CentOS content,
including at least container lifecycle versus application readiness, resource
and network failures, MySQL connection/lock/replication/performance failures,
HTTP and upstream semantics, systemd/filesystem/network diagnostics, and
SELinux-aware CentOS permission diagnosis. Each version-sensitive conclusion
is marked with a product and version range.

Every knowledge source declares whether it is an official reference, internal
Runbook, production incident, expert-maintained reference, community source,
or generated draft. Built-in references must not claim vendor authority.

### Search And Citation

`KnowledgeSearchService` exposes one asynchronous interface for exact match,
keyword, token, tag, category, service, environment, platform, version,
error-code, dependency, document type, and risk search. The first
implementation is local and offline-capable; semantic, vector, and hybrid
search remain replaceable future providers. Searches are asynchronous,
debounced, and cached so they never block the Knowledge Center or
Investigation Drawer.

Each result returns a `KnowledgeEvidence` citation:

```text
documentId, title, source, section, matchedText, score, retrievedAt
```

Smart Inquiry creates queries from the fault plus current context, for example
`502 reverse proxy upstream nginx kubernetes`. Users can open a source, add it
to an investigation, and see why it matched. Search results and hypotheses
must retain citations.

### Knowledge Center And External Search

Knowledge Center is the platform search surface. It provides an internal,
local-first search box with filters for error code, platform, service, version,
environment, document type, category, visibility, and risk. Results explain
the match and show source, section, quality, and access level. Users can open
a document, inspect the cited section, and add it to an investigation.

`BrowserSearchLauncher` is a separate interface for searches that need public
web context. It receives a user-created query and opens a configured external
search URL in the user's local browser only after an explicit click. It may
offer a Baidu-style query target and must URL-encode the query. It has no
background launch path, no Agent API that can bypass user intent, no automatic
submission from a FaultEvent, and no page scraping or imported result claims.
The opened search is external context, not evidence, until the user explicitly
adds a cited result or answer to the investigation.

Search suggestions may be generated locally from a FaultEvent, a question, or
a selected knowledge item. Showing a suggestion is allowed; launching it is a
separate, explicit user action. Query construction must redact credentials,
tokens, private hostnames, internal URLs, and other sensitive values before a
suggestion is displayed or passed to the launcher.

## Boundaries And Tests

- The extension has no Agent, Knowledge database, SSH, or command execution
  dependency; it emits redacted `FaultEvent` values through an adapter.
- Smart Inquiry consumes only the event and Knowledge search interfaces. It
  cannot perform remote operations.
- Knowledge Center and Spider use the same local `KnowledgeSearchService` as
  a future Agent. An AI provider is optional and cannot be a prerequisite for
  deterministic search.
- The only external search operation is `BrowserSearchLauncher.launch(query)`,
  initiated from an explicit user gesture after redaction. No system component
  may call it automatically.
- The system only proposes evidence collection and read-only checks. It does
  not run commands, restart services, modify web pages, submit forms, or make
  remote changes.
- Knowledge import and search run asynchronously and do not block the drawer.
- Tests cover event debounce/deduplication, evidence redaction, current-tab
  permission boundaries, overlay drag isolation, question priority,
  information-gain ordering, answer normalization, assertion labeling,
  timeline/change-correlation distinction, citation retention, visibility
  filtering, command-risk metadata, idempotent import, local/offline search,
  explicit-only browser launch, query redaction, and JSON/Markdown exports.
- Browser checks cover desktop and mobile drawer layouts, reduced motion,
  permission denial, selected-region scan, event location, and no horizontal
  overflow.
