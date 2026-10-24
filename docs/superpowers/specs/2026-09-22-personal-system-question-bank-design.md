# Personal System Navigation And Ops Question Bank Design

## Status And Scope

SmartOpsAgent will extend the existing Personal System with hierarchical
navigation, deterministic sibling-page navigation, and an independent Ops
Question Bank. This design keeps four concerns separate:

```text
Knowledge Center       -> curated, cited operational reference
Operation Library      -> actual local execution history and evidence
Ops Question Bank      -> deliberate practice and learning records
Production Simulation  -> safe, synthetic diagnostic decision training
```

The existing Inspector remains an event and evidence source. It is not renamed,
deleted, or treated as the Question Bank. The future Operation Library consumes
Inspector events through an adapter rather than replacing the Inspector data
model in this release.

This work must not add automatic remote commands, server changes, database
changes, automated remediation, AI publication of questions, or changes to
Spider, Vision, OCR, CV, SSH, Terminal, or browser automation behavior.

## Personal System Navigation

### Hierarchy

The sidebar supports one expandable child level below an existing Personal
System item. It remains a navigation tool, not a tree of arbitrary user files.
Expanded groups and the current section are persisted locally and restored on
reload. A route always opens its parent group.

```text
PERSONAL SYSTEM
  HOME
  KNOWLEDGE
    Knowledge Center
    Runbooks
    Incidents
    Practice This Topic
  OPERATION LIBRARY
    Recent Operations
    Logs
    Evidence
    Exports
    Storage
  OPERATIONS
  AGENT
  TRAINING
    Question Bank
    Wrong Questions
    Review Queue
    Production Simulation
    Skill Profile
```

The existing `/knowledge` route stays the Knowledge Center. Existing
`/inspector` routes continue to resolve while the Operation Library rollout is
incomplete. The `MEMORY` label will be replaced by `OPERATION LIBRARY` only
when its actual pages are implemented; no navigation label may claim an
unimplemented storage system.

On narrow viewports the sidebar remains collapsed by default. Activating the
menu button opens a focus-managed navigation panel whose expandable groups use
real buttons with `aria-expanded`; it must not cover page controls when closed.

### Page Stepper

`PageStepper` is a shared component that resolves ordered sibling routes from a
declarative route-flow registry. It renders an accessible previous-arrow button,
current step label, and next-arrow button.

```text
Previous: <- <label>       Current: <label>       Next: <label> ->
```

It uses direct routes, not `history.back()` or `history.forward()`. The first
or last sibling disables its unavailable button. Arrow-key shortcuts are
available only when focus is not inside an editable control, select, dialog,
or embedded viewer. They never cross navigation groups.

Initial flows are:

```text
Training:
Question Bank -> Question Detail -> Practice -> Result -> Wrong Analysis -> Review

Operation Library:
Library Home -> Operation Detail -> Timeline -> Logs -> Evidence -> Export
```

Only pages that exist participate in a flow. During early stages the Training
flow ends at the implemented page; the Operation Library flow remains absent.

## Knowledge Center Integration

Knowledge Center remains local-first, deterministic, and usable without an AI
provider. Its documents gain relationship references to Knowledge Points,
Runbooks, Incidents, Commands, Platforms, Services, and published Questions.
It is never an execution surface.

Every detail view shows source, section, version applicability, platform,
service, quality, risk metadata, and relation counts. It exposes contextual
navigation actions only:

- Open the cited Runbook or Incident.
- Practice the linked Knowledge Point.
- Open a related Operation Library record when it exists.

The actions navigate within SmartOpsAgent. They do not run a command, launch
an external search, or require an AI call.

## Ops Question Bank

### Product Boundary

Ops Question Bank trains evidence-first operations thinking rather than school
test-taking. It manages the complete practice loop:

```text
Question -> Attempt -> Evaluation -> Explanation -> Wrong-reason analysis
-> Knowledge / Runbook / Incident links -> Review Queue -> Mastery update
-> Skill Profile -> targeted new practice
```

The Question Bank contains all published questions. Wrong Question Bank is a
derived record set containing incorrect, uncertain, repeatedly incorrect, or
explicitly flagged answers. A correct answer with `GUESS` confidence may enter
the review queue, but must be labeled as uncertain rather than incorrect.

### Question Model

`Question` stores:

```text
id, type, title, description, stem, options, answerDefinition, explanation,
difficulty, cognitiveLevel, category, subCategory, knowledgePointIds,
platforms, services, tags, source, sourceType, version, estimatedTimeSeconds,
score, riskLevel, qualityStatus, createdAt, updatedAt, status
```

Supported types are `SINGLE_CHOICE`, `MULTIPLE_CHOICE`, `TRUE_FALSE`,
`FILL_BLANK`, `SHORT_ANSWER`, `COMMAND_OUTPUT`, `COMMAND_SELECTION`,
`TROUBLESHOOTING`, `INCIDENT_ANALYSIS`, `LOG_ANALYSIS`, `CONFIG_ANALYSIS`,
`ARCHITECTURE`, `SCENARIO`, `DRAG_SORT`, `MATCHING`, and `ORDERED_STEPS`.

The first usable release implements `SINGLE_CHOICE`, `MULTIPLE_CHOICE`,
`TRUE_FALSE`, `COMMAND_OUTPUT`, `TROUBLESHOOTING`, `LOG_ANALYSIS`, and
`SCENARIO`. Other types remain modeled but unavailable in the UI until their
evaluation rules are implemented.

Difficulty is `EASY`, `NORMAL`, `MEDIUM`, `HARD`, `EXPERT`, or `PRODUCTION`.
The internal cognitive level is `REMEMBER`, `UNDERSTAND`, `APPLY`, `ANALYZE`,
`EVALUATE`, or `CREATE`.

Answers have explicit correct options or normalized expected answers, accepted
answers, keyword/scoring rules, explanation, why-correct content, and
why-other-options-are-wrong content. Distractors represent documented
operational anti-patterns, not random nonsense. Each distractor carries its own
misconception explanation.

`BUILT_IN`, `USER_CREATED`, `IMPORTED`, `INCIDENT_DERIVED`,
`KNOWLEDGE_DERIVED`, `AI_GENERATED`, and `EXPERT_REVIEWED` are source types.
Quality status is `DRAFT`, `GENERATED`, `REVIEW_REQUIRED`, `REVIEWED`,
`PUBLISHED`, `DEPRECATED`, or `ERROR`. Only `REVIEWED` and `PUBLISHED`
questions appear in normal practice. AI-generated questions always begin as
`GENERATED` or `REVIEW_REQUIRED`; they cannot publish themselves.

### Attempts, Wrong Reasons, And Notes

`QuestionAttempt` preserves question version, original user answer, normalized
answer, evaluation, confidence, elapsed time, and completion time. Confidence
is `CERTAIN`, `LIKELY`, `UNSURE`, or `GUESS`.

`WrongQuestionRecord` preserves the attempted answer and contains:

```text
id, questionId, attemptId, userAnswer, correctAnswer, wrongReason,
knowledgePointIds, difficulty, timeSpentMs, confidence, createdAt,
lastReviewedAt, nextReviewAt, reviewCount, correctAfterWrong, masteryScore
```

Wrong reason is one of `CONCEPT_MISUNDERSTANDING`, `COMMAND_CONFUSION`,
`CONFIGURATION_MISUNDERSTANDING`, `DIAGNOSTIC_PATH_ERROR`,
`RISK_JUDGEMENT_ERROR`, `MEMORY_ERROR`, `CALCULATION_ERROR`, `READING_ERROR`,
`CARELESS`, `GUESS`, or `UNKNOWN`.

Each wrong-answer result distinguishes observation from instruction. For
example, an answer that immediately restarts Nginx for a 502 explains that it
is an early disruptive action, identifies lost evidence and recurrence risk,
and presents an evidence-first next path. It must not present a hypothesis as
a fact or promote an operation button.

Users can create private Question Notes, favorites, `LATER`, `IMPORTANT`,
`DIFFICULT`, `HIGH_VALUE`, `INTERVIEW`, and `PRODUCTION_PRACTICE` labels.
Notes never modify the source question or answer key.

### Knowledge Relations And Privacy

Every published question has at least one Knowledge Point and may relate to
Runbooks, Incidents, Commands, Platforms, Services, and Operation Library
records. Relation pages are links to cited source material.

Questions derived from an Incident or Operation Library record receive a
`Based on Operation` or `Incident-derived` label. Before question creation,
all IP addresses, hostnames, usernames, tokens, passwords, private keys,
cookies, internal URLs, database names, and identifying private values are
redacted. Original raw operation evidence is never copied to a question by
default.

### Review And Mastery

Review uses a local spaced-repetition schedule with `AGAIN`, `HARD`, `GOOD`,
and `EASY`. Incorrect answers schedule a near-term review. Repeated errors
shorten the interval; consistent correct answers extend it. Correct answers
with low confidence may create a review item.

`MasteryRecord` stores a 0-100 score and a status of `NOT_STARTED`, `LEARNING`,
`WEAK`, `IMPROVING`, `MASTERED`, or `REGRESSED`. The calculation considers
recency, repeat errors, confidence, elapsed time, difficulty, cognitive level,
review interval, and consistency. A collection of easy correct answers cannot
mark a Knowledge Point as expert-level mastery.

`SkillProfile` aggregates Linux, Network, Docker, Nginx, MySQL, Kubernetes,
Security, Observability, Troubleshooting, Incident Response, Automation, and
Risk Management. It shows a numeric breakdown plus navigable weak topics,
related questions, knowledge, Runbooks, and Incidents. A visual radar is
supplementary, never the only way to inspect the data.

### Training And Simulation

Training modes are `QUICK_PRACTICE`, `WRONG_QUESTIONS`, `WEAK_TOPICS`,
`DAILY_REVIEW`, `RANDOM`, `KNOWLEDGE_POINT`, `SERVICE`, `PLATFORM`,
`DIFFICULTY`, `INCIDENT`, and `RUNBOOK`.

Production Simulation is a synthetic, decision-tree `SCENARIO` session. It
reveals evidence only after the learner chooses a next diagnostic step. It
scores diagnostic quality, evidence gathering, risk awareness, efficiency,
and recovery verification. A risky simulated step can model its consequence
without touching actual infrastructure. Simulation actions never call SSH,
commands, containers, databases, or browser automation.

The first scenario pack is an Nginx 502 after an `api-order` deployment:

```text
Partial /api/order 502 -> Nginx error log -> upstream refused connection
-> application readiness / listener / deployment evidence -> resolution check
```

Choosing an immediate Nginx restart may temporarily reduce the simulated
symptom but adds a risk penalty and demonstrates that the root cause remains
unconfirmed.

## Data And Local Persistence

Question content, relationships, attempts, wrong records, review records,
mastery records, notes, favorites, training sessions, and simulation events
are durable local data. They are versioned and migration-ready, with export,
backup, and restore support.

The full schema ultimately includes:

```text
questions, question_options, question_answers, question_versions,
knowledge_points, question_knowledge_relations, question_runbook_relations,
question_incident_relations, question_command_relations, question_platforms,
question_services, attempts, wrong_questions, review_records, mastery_records,
skill_profiles, learning_paths, question_notes, favorites, training_sessions,
simulation_sessions, simulation_events
```

The initial pack ships curated Docker, MySQL, Nginx, Ubuntu, CentOS, Network,
Linux, and Kubernetes questions. Its content balance targets 20% foundational,
20% command/output, 20% config/log, 25% troubleshooting, and 15% production
simulation. Each version-specific question carries a version range.

## Delivery Sequence

### Stage A: Personal System Navigation

- Declarative navigation group and route-flow registry.
- Sidebar expand/collapse, persisted group state, accessible mobile drawer.
- Shared `PageStepper` with no history coupling and no shortcut conflicts.
- Existing routes remain compatible; no operation-storage label change yet.

### Stage B: Knowledge Relationships

- Knowledge Point and document relationship models.
- Cited Runbook, Incident, Command, and published-question links.
- Detail actions for "Practice this topic" and related local records.
- No Agent, external browser, command, or remote-operation integration.

### Stage C: Question Bank Learning Loop

- Question/option/version models and reviewed built-in question packs.
- Attempt evaluation, confidence/time capture, explanations, misconception
  analysis, notes, favorites, Wrong Question Bank, and review queue.
- Mastery and Skill Profile with accessible detailed lists.
- JSON/Markdown pack import/export, schema version and migrations.

### Stage D: Synthetic Production Simulation

- Scenario definitions and evidence-reveal decision tree.
- Risk/evidence/diagnosis/efficiency/verification score model.
- Scenario history and linked knowledge/runbooks/incidents.
- No connection to live hosts or operation execution.

## Testing And Safety Boundaries

- Navigation tests cover open-route parent expansion, persistence, mobile
  `aria-expanded`, sibling boundaries, direct route links, and editable-field
  shortcut exclusion.
- Knowledge tests cover cited relationship integrity, published-only question
  visibility, source/version metadata, and no execution action in detail UI.
- Question tests cover structured answer evaluation, distractor explanation,
  question-version preservation, wrong-reason classification, confident and
  uncertain correct answers, review interval changes, mastery regression, and
  duplicate/repeated wrong handling.
- Import/export tests cover schema version migrations, malformed pack rejection,
  source quality status, and sensitive-data redaction for Incident/Operation
  derived questions.
- Simulation tests cover hidden-evidence progression, evidence-first scoring,
  risky action consequence, completion path, and guarantee no operations API,
  SSH, Terminal, or browser-launch call occurs.
- UI checks cover desktop/mobile hierarchy, page stepper layout, keyboard
  access, no horizontal overflow, and clear distinction between raw evidence,
  learner answer, explanation, hypothesis, and recommended study path.
