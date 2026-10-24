# Linux Process Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the Linux process management knowledge module and turn the existing process tool route into a knowledge-driven read-only diagnostic workspace.

**Architecture:** Keep the Markdown source as the complete knowledge reference, extend the existing offline catalog for search/detail access, and add a pure-data diagnostic rules module consumed by `ToolsView.vue`. The tool only presents evidence checklists and safe command previews; it never reads or changes local or remote systems.

**Tech Stack:** Vue 3, Vue Router, Vite, Node test runner, Markdown knowledge source, existing SmartOpsAgent CSS tokens.

**Spec:** `docs/superpowers/specs/2026-09-23-linux-process-diagnostics-design.md`

## Global Constraints

- Do not read or execute real local/SSH process data in this phase.
- Do not add remote execution, database/API changes, or production server integration.
- Use existing knowledge search/detail and tool navigation patterns.
- Keep user changes in `frontend/test/visual-check.mjs` untouched.
- Commands shown in the UI are previews only and must be marked read-only.

## Review Focus

- Query terms with punctuation or mixed case (`D state`, `ps aux`, `LINUX-PROCESS-001`) must find the same knowledge entry; test in Task 1.
- A diagnostic rule with no selected scenario must not imply an action or execute a command; test in Task 2.
- High-risk suggestions such as `kill -9` must be presented as prohibited/escalation guidance, never as executable controls; test in Task 2.
- Opening a diagnostic tool from knowledge must preserve the selected knowledge context and provide a return path; test in Task 3.
- Existing `/tools/*` routes and knowledge previous/next behavior must remain unchanged; test in Task 3.

### Task 1: Linux process knowledge source and catalog index

**Files:**
- Create: `knowledge/linux/process_management.md`
- Modify: `frontend/src/views/knowledge/knowledgeCatalog.js`
- Test: `frontend/test/knowledge-catalog.test.mjs`

**Interfaces:**
- Produces catalog entry `linux-process-management` with `moduleId: 'LINUX-PROCESS-001'`, domain `cloud-operations`, platform `Linux`, service `process`, and tags for `ps`, `top`, `kill`, `D state`, `zombie`, `iostat`, `proc`.

- [ ] **Step 1: Write failing search tests**

Add tests that search `LINUX-PROCESS-001`, `D state`, and `ps aux`, and assert the returned entry id is `linux-process-management`. Add a test that asserts its content includes `SIGTERM`, `SIGKILL`, `iostat`, `zombie`, and `/proc`.

- [ ] **Step 2: Run focused tests to verify failure**

Run from `frontend`: `npm test -- test/knowledge-catalog.test.mjs`.
Expected: the new assertions fail because the process entry does not exist.

- [ ] **Step 3: Add the complete Markdown source**

Create `knowledge/linux/process_management.md` with program/process distinction, PID/PPID, lifecycle, states R/S/D/T/Z/X, `ps`, `top`, signals, TERM-before-KILL, nice/renice, jobs/fg/bg, `/proc`, CPU/IO/memory investigation, CPU 100%, zombie, and D-state cases. Include AI questioning rules and related module IDs `LINUX-MEMORY`, `LINUX-CPU`, `LINUX-DISK`, `LINUX-SYSTEMD`, `LINUX-SHELL`, and `LINUX-PERFORMANCE`.

- [ ] **Step 4: Add the catalog entry**

Add a structured entry to `knowledgeEntries` with `id`, `moduleId`, `title`, `summary`, `content`, `source`, `section`, `version`, `risk`, `tags`, and `relatedTool: 'processes'`. Keep content searchable through the existing `searchKnowledgeEntries` fields.

- [ ] **Step 5: Run focused tests to verify green**

Run `npm test -- test/knowledge-catalog.test.mjs`.
Expected: all catalog tests pass.

### Task 2: Pure process diagnostic rules

**Files:**
- Create: `frontend/src/views/operations/processDiagnostics.js`
- Test: `frontend/test/process-diagnostics.test.mjs`

**Interfaces:**
- Export `processDiagnosticScenarios`, an array of scenario objects with `id`, `label`, `symptoms`, `evidence`, `commands`, `risk`, `verification`, and `escalation`.
- Export `getProcessDiagnosticScenario(id)`, returning the matching object or `null`.
- Every command object has `{ command, purpose, readOnly: true }`.

- [ ] **Step 1: Write failing rule tests**

Assert the four ids `server-slow`, `cpu-high`, `process-d-state`, and `process-zombie` exist; every command has `readOnly === true`; no command string contains `kill`, `renice`, `restart`, `shutdown`, `rm`, or `drop`; unknown ids return `null`.

- [ ] **Step 2: Run focused tests to verify failure**

Run from `frontend`: `npm test -- test/process-diagnostics.test.mjs`.
Expected: module import or assertions fail because the rules module does not exist.

- [ ] **Step 3: Implement the rule data**

Create the four scenario objects using only observation commands such as `uptime`, `top -b -n 1`, `ps aux --sort=-%cpu`, `ps -eo state,pid,ppid,cmd`, `iostat`, `free -h`, `dmesg --level=err,warn`, and `cat /proc/<pid>/status`. Describe `kill -9` as a prohibited escalation in prose only if needed, never as a command object.

- [ ] **Step 4: Run focused tests to verify green**

Run `npm test -- test/process-diagnostics.test.mjs`.
Expected: all rule safety tests pass.

### Task 3: Read-only process tool workspace and knowledge link

**Files:**
- Modify: `frontend/src/views/operations/ToolsView.vue`
- Modify: `frontend/src/views/knowledge/KnowledgeView.vue`
- Modify: `frontend/src/views/knowledge/knowledgeLibrary.js`
- Test: `frontend/test/operations-process-tool.test.mjs`
- Test: `frontend/test/knowledge-library.test.mjs`

**Interfaces:**
- `ToolsView.vue` imports `processDiagnosticScenarios` and renders the workspace only for `selectedTool === 'processes'`.
- Query parameter `?knowledge=linux-process-management` is accepted by the knowledge-to-tool link and displayed as context.
- Existing non-process tools keep their current placeholder behavior.

- [ ] **Step 1: Write failing component/behavior tests**

Add source-level tests that assert the process route imports the diagnostic data, renders scenario labels, displays `READ-ONLY COMMAND PREVIEW`, and has no `runTool` action for process diagnostics. Add a knowledge view test that checks a related-tool link points to `/tools/processes?knowledge=linux-process-management`.

- [ ] **Step 2: Run focused tests to verify failure**

Run `npm test -- test/operations-process-tool.test.mjs test/knowledge-library.test.mjs`.
Expected: new assertions fail because the process workspace and related-tool link do not exist.

- [ ] **Step 3: Implement the process workspace**

Add scenario selection, evidence checklist, command preview rows, risk panel, verification and escalation sections. Keep the existing Bridge status visible, but make process diagnostics available offline and label all commands as read-only previews. Do not call `runTool` when the process scenario is selected.

- [ ] **Step 4: Add the knowledge link**

When the selected knowledge entry has `relatedTool`, render a button/link to `/tools/${relatedTool}?knowledge=${entry.id}`. Preserve close, previous, and next behavior.

- [ ] **Step 5: Run focused tests to verify green**

Run `npm test -- test/operations-process-tool.test.mjs test/knowledge-library.test.mjs`.
Expected: process workspace and link tests pass.

### Task 4: Full verification and handoff

**Files:**
- Modify: none beyond Tasks 1-3

- [ ] **Step 1: Run the complete test suite**

From `frontend`, run `npm test` and confirm zero failures.

- [ ] **Step 2: Run static checks and build**

Run `npm run lint`, `npm run typecheck`, and `npm run build`.

- [ ] **Step 3: Check patch integrity**

From the project root, run `git diff --check` and `git status --short`. Confirm `frontend/test/visual-check.mjs` remains an existing user modification and is not included in the feature change summary.
