# Personal Model Gateway Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the personal model gateway management loop while preserving the existing Astra6 navigation and visual hierarchy.

**Architecture:** Personal users receive personal-scope model-group endpoints. Admin endpoints remain reserved for cross-user administration. Model groups expose CRUD and route controls with ownership checks applied to every mutation; the existing gateway page consumes the personal APIs and keeps audit and route health in the current tabs.

**Tech Stack:** Spring Boot 3.3, Java 17, JdbcTemplate, MySQL-compatible schema, Vue 3, existing request client and gateway styles.

**Spec:** User-approved gateway governance optimization from the 2026-10-04 conversation.

## Global Constraints

- Personal users can only access resources with `scope='PERSONAL'` and their own `owner_user_id`.
- Provider credentials never reach the browser.
- Audit data excludes prompts, completions, raw Authorization headers, and provider secrets.
- Existing Astra6 navigation, tabs, theme tokens, and responsive layout remain intact.

## Review Focus

- A normal user can save and edit their own model group without an admin role.
- A normal user cannot mutate another user's model group or route.
- Disabling a route removes it from invocation selection; deleting a route removes it from health results.
- A model group update preserves explicitly configured routes unless the caller requests replacement.
- Invalid route priority and weight return a client error before database mutation.

### Task 1: Personal model-group API boundary

Add personal POST/PUT/DELETE endpoints and ownership tests. Keep admin endpoints for administrator-wide operations.

### Task 2: Model-group and route management service

Add group listing, update, delete, route update, and route replacement methods with scope and owner predicates. Add service tests for ownership and validation.

### Task 3: Gateway management UI

Replace the single create form with a personal model-group list and route editor inside the existing MODEL GROUPS tab. Reuse current panel and form tokens; keep the audit route controls in AUDIT / HEALTH.

### Task 4: Verification

Run focused backend tests, frontend build, navigation tests, and diff checks. Add browser coverage only after the contract is stable.
