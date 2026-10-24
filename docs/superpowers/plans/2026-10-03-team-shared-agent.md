# Team Shared Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏 Astra6 已有个人空间和团队管理能力的前提下，增加团队共享 Agent、团队工具菜单、协作会话、审批和审计能力。

**Architecture:** 个人资源继续使用 `user` scope，新增资源使用 `team` scope。服务端从 `SessionUser` 推导操作者和团队权限，团队 Agent 通过不可变版本、工具策略和运行记录执行；前端从主菜单进入独立团队协作工作台，使用团队上下文栏、工具菜单和协作会话区。

**Tech Stack:** Spring Boot 3.3, Spring Security, JdbcTemplate, H2/MySQL SQL migrations, Vue 3, Vue Router, Pinia, Node test runner.

**Spec:** `docs/superpowers/specs/2026-10-03-team-shared-agent-design.md`

## Global Constraints

- 保留现有个人 Agent、个人知识、个人连接、团队邀请、成员管理、团队冻结和平台管理员功能。
- 现有团队角色 `owner/admin/member/viewer` 不改名；Agent 场景将 `member` 映射为运行能力。
- 客户端 `X-User-Id`、`teamId`、`agentId` 和 `runtimeId` 不能成为授权依据。
- 团队冻结、成员撤权、Agent 下线或凭据失效时必须阻断新的未授权运行。
- 变更工具必须经过预览、确认和策略要求的审批。

## Review Focus

- 跨团队资源 ID：返回 404/403 且不泄露资源存在性。
- 成员撤权与并发运行：撤权后不能创建新运行，进行中的运行不能获得新的工具授权。
- 团队冻结：工具菜单刷新后隐藏不可用操作，后端也拒绝直接调用。
- 个人/团队会话隔离：切换工作空间不会混入聊天历史、附件、连接或运行记录。
- 版本不可变：运行记录始终引用实际发布版本，运行者不能修改提示词或工具白名单。

### Task 1: Server Scope and Authorization Foundation

**Files:**
- Create: `backend/src/main/java/com/smartops/security/TeamResourceAuthorizer.java`
- Create: `backend/src/main/java/com/smartops/security/TeamResourceScope.java`
- Modify: `backend/src/main/java/com/smartops/controller/OperationToolController.java`
- Modify: `backend/src/main/java/com/smartops/service/OperationToolService.java`
- Modify: `backend/src/main/java/com/smartops/service/OperationRuntime.java`
- Test: `backend/src/test/java/com/smartops/security/TeamResourceAuthorizerTest.java`
- Test: `backend/src/test/java/com/smartops/integration/TeamAgentAuthorizationIntegrationTest.java`

**Interfaces:**
- `TeamResourceAuthorizer.requireMember(SessionUser actor, long teamId, String capability)` returns a team-scoped authorization record.
- `TeamResourceAuthorizer.requireResource(SessionUser actor, String scope, long resourceId, String capability)` validates ownership and capability.
- Operation controllers use `SessionUser` and ignore `X-User-Id` for identity.

- [ ] **Step 1: Write failing authorization tests** for forged user headers, cross-team IDs, viewer execution, frozen teams, and member execution.
- [ ] **Step 2: Run the focused tests** with `mvn -s .mvn/smartops-settings.xml -Dtest=TeamAgentAuthorizationIntegrationTest test`; expect failures because the authorizer and session binding are absent.
- [ ] **Step 3: Implement the authorizer and controller binding** using existing `TeamWorkspaceService` roles and `SessionUser`.
- [ ] **Step 4: Run focused backend tests** and verify all scope and role cases pass.
- [ ] **Step 5: Run existing operations and team integration tests** to ensure personal routes remain compatible.

### Task 2: Team Agent, Version, Policy, and Run Persistence

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261003__team_agents.sql`
- Create: `backend/src/main/java/com/smartops/service/TeamAgentService.java`
- Create: `backend/src/main/java/com/smartops/service/TeamAgentRunService.java`
- Create: `backend/src/main/java/com/smartops/controller/TeamAgentController.java`
- Modify: `backend/src/main/resources/db/local-schema.sql`
- Modify: `backend/src/test/resources/schema.sql`
- Test: `backend/src/test/java/com/smartops/service/TeamAgentServiceTest.java`
- Test: `backend/src/test/java/com/smartops/integration/TeamAgentPersistenceIntegrationTest.java`

**Interfaces:**
- `TeamAgentService.list(SessionUser actor, long teamId)` returns only authorized agents.
- `TeamAgentService.saveDraft(SessionUser actor, long agentId, DraftInput input)` edits only draft versions.
- `TeamAgentService.publish(SessionUser actor, long agentId)` creates an immutable version.
- `TeamAgentRunService.create(SessionUser actor, long agentId, long versionId, RunInput input)` creates a pending or approved run according to policy.

- [ ] **Step 1: Write failing persistence tests** for team ownership, immutable versions, policy defaults, run references, and personal/team isolation.
- [ ] **Step 2: Run the tests** and verify missing migration/service behavior fails.
- [ ] **Step 3: Add the migration and JDBC services** with foreign keys, status checks, immutable version rows, and audit events.
- [ ] **Step 4: Add controller endpoints** under `/api/team-agents` and `/api/team-agent-runs`.
- [ ] **Step 5: Run focused integration tests** with H2 and verify migration order against existing schemas.

### Task 3: Team Tool Menu and Collaboration Workspace

**Files:**
- Create: `frontend/src/api/teamAgents.js`
- Create: `frontend/src/domain/team/teamWorkspace.js`
- Create: `frontend/src/components/team/TeamContextBar.vue`
- Create: `frontend/src/components/team/TeamToolMenu.vue`
- Create: `frontend/src/components/team/TeamCollaborationSession.vue`
- Create: `frontend/src/views/team/TeamCollaborationView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/navigation/routeMetadata.js`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/views/team/TeamSpacesView.vue`
- Test: `frontend/test/team-collaboration-workspace.test.mjs`
- Test: `frontend/test/team-tool-menu.browser.mjs`

**Interfaces:**
- `teamWorkspace` owns active team, active agent, active version, tool groups, session state, and reset-on-team-switch behavior.
- `TeamToolMenu` consumes server-provided capabilities and emits `select-agent`, `select-tool`, `open-run-history`, and `open-approvals`.
- `TeamCollaborationSession` displays messages, tool previews, approval cards, trace output, and sanitized results.

- [ ] **Step 1: Write failing frontend tests** for main-menu entry, team context switching, tool grouping, capability filtering, and personal-history isolation.
- [ ] **Step 2: Run the tests** with `npm test -- --test-name-pattern="team collaboration"`; expect missing route and components.
- [ ] **Step 3: Add the team collaboration route and workspace store** with a clean reset when the team changes.
- [ ] **Step 4: Implement the tool menu** with Agent, diagnostics, operations, connections, runs, and approvals groups.
- [ ] **Step 5: Implement the collaboration session** with pending, approval-required, running, succeeded, failed, and revoked states.
- [ ] **Step 6: Run unit tests and the browser test** at desktop and mobile widths.

### Task 4: Approval, Execution, Audit, and Revocation

**Files:**
- Create: `backend/src/main/java/com/smartops/service/TeamAgentApprovalService.java`
- Create: `backend/src/main/java/com/smartops/controller/TeamAgentRunController.java`
- Modify: `backend/src/main/java/com/smartops/service/OperationToolService.java`
- Modify: `backend/src/main/java/com/smartops/security/SecurityAuditService.java`
- Modify: `frontend/src/components/team/TeamApprovalPanel.vue`
- Modify: `frontend/src/components/team/TeamCollaborationSession.vue`
- Test: `backend/src/test/java/com/smartops/integration/TeamAgentApprovalIntegrationTest.java`
- Test: `frontend/test/team-agent-approval.test.mjs`

**Interfaces:**
- `TeamAgentApprovalService.approve(SessionUser actor, long runId, String decision)` accepts only authorized reviewer decisions.
- `TeamAgentRunController` exposes run detail, approval, cancel, and evidence endpoints.
- `OperationToolService` receives a server-created one-time execution grant instead of trusting client confirmation.

- [ ] **Step 1: Write failing tests** for read-only direct runs, mutation approval, duplicate decisions, expired grants, revoked members, and sanitized viewer results.
- [ ] **Step 2: Run focused tests** and verify approval and grant behavior fails before implementation.
- [ ] **Step 3: Implement transactional approval and one-time grants** with audit records and expiry.
- [ ] **Step 4: Connect operation execution to the grant and team policy** while preserving personal operation behavior.
- [ ] **Step 5: Add frontend approval cards and live run states** and verify reload-safe state restoration.
- [ ] **Step 6: Run backend and frontend security regression tests.**

### Task 5: Quotas, Observability, and Full Acceptance

**Files:**
- Modify: `backend/src/main/java/com/smartops/service/TeamAgentRunService.java`
- Modify: `backend/src/main/java/com/smartops/service/ObservabilityService.java`
- Modify: `frontend/src/views/team/TeamDetailView.vue`
- Modify: `frontend/src/assets/styles/team-workspace.css`
- Test: `backend/src/test/java/com/smartops/integration/TeamAgentGovernanceIntegrationTest.java`
- Test: `frontend/test/team-collaboration-governance.browser.mjs`

- [ ] **Step 1: Write governance tests** for team quotas, concurrent run limits, frozen teams, version rollback, and audit filters.
- [ ] **Step 2: Implement server-side quota and policy enforcement** with observable rejection reasons.
- [ ] **Step 3: Add run history, audit summaries, and sanitized evidence views** to the team workspace.
- [ ] **Step 4: Run all backend tests** with `mvn -s .mvn/smartops-settings.xml -Dmaven.compiler.fork=false test`.
- [ ] **Step 5: Run all frontend tests and production build** with `npm test` and `npm run build`.
- [ ] **Step 6: Run the team collaboration browser checks** across desktop, mobile, light, dark, and reduced-motion modes.

