# 智能运维知识分层与操作员记忆实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立系统知识、个人知识、故障候选和团队共享知识的隔离模型，并逐步加入操作员记忆、故障推荐和受治理的 Skill/脚本/插件草稿生成。

**Architecture:** 后端以作用域、来源和状态为核心建立个人知识与记忆服务；前端知识库改为分层工作区。推荐服务只读取当前用户可见内容并返回证据和风险，生成物统一进入草稿状态，最终复用现有团队权限、运行预览、审批和审计链路。

**Tech Stack:** Spring Boot, JdbcTemplate, Flyway SQL migrations, Vue 3, Pinia, Node test runner, Maven tests.

**Spec:** `docs/superpowers/specs/2026-10-04-operator-memory-knowledge-generation-design.md`

## Global Constraints

- 系统知识只读；个人资源按认证用户隔离；团队资源沿用 `owner/admin/member/viewer`。
- 客户端传入的 `userId/teamId` 不能决定资源归属，服务端必须从认证上下文和权限服务校验。
- 未审核候选不能进入已验证知识推荐；记忆必须由确认或成功验证触发。
- Skill、脚本和插件先生成 `DRAFT`，不能自动安装或执行。
- 高风险操作必须复用命令预览、审批、摘要绑定和审计链路。
- 保留现有系统知识检索、候选审核、团队 Agent 和团队运行审批行为。

## Review Focus

- 用户 A 读取用户 B 的个人知识或记忆：由 Task 1 的隔离测试覆盖。
- 待审核候选被推荐为已验证知识：由 Task 2 的状态过滤测试覆盖。
- 用户未确认但运行失败的记录写入长期记忆：由 Task 3 的写入条件测试覆盖。
- 高风险生成脚本绕过审批执行：由 Task 5 的状态与审批边界测试覆盖。
- 移动端分层知识库出现横向溢出或作用域不清：由 Task 4 的浏览器断言覆盖。

### Task 1: Personal Knowledge Scope

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261004__personal_knowledge.sql`
- Create: `backend/src/main/java/com/smartops/service/PersonalKnowledgeService.java`
- Create: `backend/src/main/java/com/smartops/controller/PersonalKnowledgeController.java`
- Create: `backend/src/test/java/com/smartops/service/PersonalKnowledgeServiceTest.java`
- Create: `frontend/src/api/personalKnowledge.js`
- Create: `frontend/src/domain/knowledge/personalWorkspace.js`

**Interfaces:**
- Produces `PersonalKnowledgeService.list(userId, libraryId, query, page, pageSize)` and create/update/archive/delete methods.
- Each entry carries `userId`, `libraryId`, `sourceType`, `verificationStatus`, `version` and `contentMarkdown`.

- [ ] **Step 1: Write failing isolation and CRUD tests**
- [ ] **Step 2: Run `mvn -pl backend -Dtest=PersonalKnowledgeServiceTest test` and confirm failure**
- [ ] **Step 3: Add migration, service validation, and controller endpoints**
- [ ] **Step 4: Run service and controller tests and confirm pass**
- [ ] **Step 5: Add frontend API/domain tests for scope and status display**

### Task 2: Candidate Promotion and Knowledge Retrieval

**Files:**
- Modify: `backend/src/main/java/com/smartops/service/KnowledgeCandidateService.java`
- Modify: `backend/src/main/java/com/smartops/controller/KnowledgeCandidateController.java`
- Create: `backend/src/main/java/com/smartops/service/KnowledgeRetrievalService.java`
- Test: `backend/src/test/java/com/smartops/service/KnowledgeCandidateServiceTest.java`
- Test: `backend/src/test/java/com/smartops/service/KnowledgeRetrievalServiceTest.java`

**Interfaces:**
- Adds `promote(userId, candidateId, libraryId, title, contentMarkdown)` and `reject(userId, candidateId, reason)`.
- `KnowledgeRetrievalService.search(userId, scope, query, filters)` excludes non-published candidates.

- [ ] **Step 1: Add failing tests for promote/reject and pending exclusion**
- [ ] **Step 2: Run targeted Maven tests and confirm failure**
- [ ] **Step 3: Implement state transitions, source references, and retrieval filtering**
- [ ] **Step 4: Run candidate and retrieval tests and confirm pass**

### Task 3: Operator Memory

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261004__operator_memory.sql`
- Create: `backend/src/main/java/com/smartops/service/OperatorMemoryService.java`
- Create: `backend/src/main/java/com/smartops/controller/OperatorMemoryController.java`
- Create: `backend/src/test/java/com/smartops/service/OperatorMemoryServiceTest.java`
- Modify: `backend/src/main/java/com/smartops/service/OperationAgentContextService.java`

**Interfaces:**
- `recordConfirmed(userId, incidentKey, memoryType, action, sourceRefs)` writes an `ACTIVE` memory.
- `list`, `disable`, `delete`, and `match(userId, incidentPattern)` preserve user scope.
- Agent context returns only matching active memories and their evidence counts.

- [ ] **Step 1: Write failing tests for confirmation-only writes, disable/delete, and cross-user isolation**
- [ ] **Step 2: Run targeted tests and confirm failure**
- [ ] **Step 3: Implement tables, service methods, and context projection**
- [ ] **Step 4: Run service and context tests and confirm pass**

### Task 4: Knowledge Workspace UI

**Files:**
- Modify: `frontend/src/views/knowledge/KnowledgeView.vue`
- Create: `frontend/src/views/knowledge/PersonalKnowledgeView.vue`
- Create: `frontend/src/views/knowledge/OperatorMemoryView.vue`
- Modify: `frontend/src/router/index.js`
- Create: `frontend/test/personal-knowledge-workspace.test.mjs`
- Create: `frontend/test/personal-knowledge-workspace.browser.mjs`

**Interfaces:**
- Tabs expose System, My Knowledge, Incident Candidates, Team Shared, and Generation Center.
- UI always displays scope, verification status, source trace, and risk.

- [ ] **Step 1: Add failing route, state, and 375px browser assertions**
- [ ] **Step 2: Run `node --test frontend/test/personal-knowledge-workspace.test.mjs` and confirm failure**
- [ ] **Step 3: Implement views, API state, create/edit/archive flows, and responsive layout**
- [ ] **Step 4: Run frontend unit/build/browser checks and confirm pass**

### Task 5: Incident Recommendation and Artifact Drafts

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261004__incident_patterns_artifacts.sql`
- Create: `backend/src/main/java/com/smartops/service/IncidentRecommendationService.java`
- Create: `backend/src/main/java/com/smartops/service/ArtifactDraftService.java`
- Create: `backend/src/main/java/com/smartops/controller/RecommendationController.java`
- Create: `backend/src/main/java/com/smartops/controller/ArtifactDraftController.java`
- Create: `backend/src/test/java/com/smartops/service/IncidentRecommendationServiceTest.java`
- Create: `backend/src/test/java/com/smartops/service/ArtifactDraftServiceTest.java`

**Interfaces:**
- `recommend(userId, IncidentPattern)` returns recommendations with sources, confidence, risk and verification steps.
- `createDraft(userId, type, incidentId, content)` always creates `DRAFT`.
- `validate`, `submitReview`, `approve`, `publish`, and `archive` enforce type-specific checks and approval requirements.

- [ ] **Step 1: Write failing tests for source attribution, risk gating, draft-only creation, and publish transitions**
- [ ] **Step 2: Run targeted Maven tests and confirm failure**
- [ ] **Step 3: Implement matching, static checks, draft state machine, and approval binding**
- [ ] **Step 4: Run targeted tests plus existing team approval tests and confirm pass**

### Task 6: Generation Center UI and Final Verification

**Files:**
- Create: `frontend/src/views/knowledge/GenerationCenterView.vue`
- Create: `frontend/src/api/artifactDrafts.js`
- Modify: `frontend/src/views/team/TeamCollaborationView.vue`
- Create: `frontend/test/generation-center.test.mjs`

- [ ] **Step 1: Add failing UI/API tests for draft status and approval handoff**
- [ ] **Step 2: Run frontend targeted tests and confirm failure**
- [ ] **Step 3: Implement draft list, validation results, review handoff, and team approval link**
- [ ] **Step 4: Run `npm run build`, targeted tests, backend tests, and `git diff --check`**
- [ ] **Step 5: Review the full diff for unrelated changes and record residual risks**
