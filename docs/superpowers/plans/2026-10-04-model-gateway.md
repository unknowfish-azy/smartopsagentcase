# SmartOps Model Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an OpenAI-compatible model gateway with virtual keys, model groups, provider routing, usage audit, and a safe foundation for later LoRA/QLoRA training.

**Architecture:** A server-side gateway authenticates SmartOps virtual keys, resolves an authorized model group, selects a healthy provider connection, forwards only sanitized request data, and records metadata without prompts or secrets. Existing encrypted model connections remain the provider credential store; personal/team/admin scopes are enforced at the gateway boundary.

**Tech Stack:** Spring Boot 3.3, Java 17, MySQL migrations, existing AES-GCM and session security, Vue frontend later.

**Spec:** User-approved unified gateway and vertical-model plan from 2026-10-04 conversation.

## Global Constraints

- Never expose provider API keys to browser clients.
- Never store prompts, completions, credentials, or raw authorization headers in audit records.
- Model group access must be checked against the authenticated user or virtual key scope.
- Execution and approval gates remain separate from model inference.
- Existing personal/team knowledge isolation remains unchanged.

## Review Focus

- Revoked or expired virtual keys must fail before provider calls.
- Unknown model groups and unauthorized scopes must return a safe 403/404.
- Provider failures must not reveal upstream credentials or response bodies.
- Empty or oversized requests must be rejected before routing.
- Usage logging failure must not convert a successful provider response into a retry.

### Task 1: Gateway persistence and key lifecycle

Create `V20261004__model_gateway.sql`, gateway entities and service for hashed virtual keys, model groups, group members, and invocation metadata. Add tests for key hashing, expiry, revocation, and scope checks.

### Task 2: OpenAI-compatible gateway API

Create `/v1/models` and `/v1/chat/completions` controllers, request validation, group routing, provider invocation through the existing encrypted connection client, and metadata-only audit logging. Add controller/service tests.

### Task 3: Admin management surface

Add admin endpoints to create/revoke virtual keys and configure model groups without returning provider secrets. Add frontend management after the backend contract is stable.

### Task 4: Training foundation

Add dataset metadata, approval status, versioning, and evaluation records. Do not start training from unapproved personal or team material; connect approved records to an external QLoRA job runner in a later task.
