# Agent 视觉证据与聊天附件实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在聊天中加入截屏、拍照、文件、粘贴和拖拽的统一视觉证据流，并建立 VisionEvent、OCR 和 Agent 分析边界。

**Architecture:** 复用现有聊天附件会话、权限、配额和审计；前端负责用户主动捕获和预览，后端把已绑定附件转换为作用域内 VisionEvent，OCR/分析以可追踪状态运行。所有视觉分析先输出证据和建议，确认后才可进入个人知识或记忆。

**Tech Stack:** Vue 3, Pinia, browser Media Capture APIs, Spring Boot, JdbcTemplate, Flyway, existing OCR abstraction, Node test runner, Maven tests.

**Spec:** `docs/superpowers/specs/2026-10-04-visual-evidence-chat-design.md`

## Global Constraints

- 只有用户主动点击才能调用屏幕或摄像头权限。
- 视频流只用于生成静态图，完成或取消后立即释放。
- 视觉事件继承聊天会话作用域，服务端校验用户和团队权限。
- OCR/模型结果必须区分事实、识别文本、推断和待验证建议。
- 图片中的命令永远不能自动执行；确认前不能写入知识或记忆。
- 保留现有文件、Ctrl+V、拖拽和附件上传行为。

## Review Focus

- 用户拒绝屏幕或摄像头权限：输入框仍可正常文字聊天。
- 捕获过程中离开页面或取消：媒体轨道被释放且没有悬挂摄像头状态。
- 用户 A 访问用户 B 的 VisionEvent：返回资源不存在或无权限。
- OCR 低置信度命令被误当成可执行命令：结果必须标记待核验。
- 团队会话和个人会话的原图与分析结果不能混用。

### Task 1: Capture Sources

**Files:**
- Create: `frontend/src/domain/chat/visualCapture.js`
- Modify: `frontend/src/components/ai/ChatAttachmentComposer.vue`
- Modify: `frontend/src/components/ai/AiChatPanel.vue`
- Create: `frontend/test/visual-capture.test.mjs`
- Create: `frontend/test/visual-capture.browser.mjs`

- [ ] **Step 1: Write failing tests for source labels, stream cleanup, permission rejection, and paste/drop preservation**
- [ ] **Step 2: Run targeted tests and confirm failure**
- [ ] **Step 3: Implement `captureScreen()`, `captureCamera()`, `stopStream()`, and the visual tool menu**
- [ ] **Step 4: Run unit and browser tests at desktop and 375px viewports**

### Task 2: VisionEvent Persistence

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261004__vision_events.sql`
- Create: `backend/src/main/java/com/smartops/service/VisionEventService.java`
- Create: `backend/src/main/java/com/smartops/controller/VisionEventController.java`
- Create: `backend/src/test/java/com/smartops/service/VisionEventServiceTest.java`

- [ ] **Step 1: Write failing tests for attachment ownership, event creation, status transitions, and cross-scope access**
- [ ] **Step 2: Run targeted Maven tests and confirm failure**
- [ ] **Step 3: Implement table, service, controller, and audit records**
- [ ] **Step 4: Run targeted tests and existing chat attachment tests**

### Task 3: OCR and Privacy State

**Files:**
- Modify: `backend/src/main/java/com/smartops/service/VisionEventService.java`
- Create: `backend/src/main/java/com/smartops/service/VisionAnalysisService.java`
- Create: `backend/src/test/java/com/smartops/service/VisionAnalysisServiceTest.java`
- Modify: `backend/src/main/resources/application.yml`

- [ ] **Step 1: Add failing tests for OCR status, confidence, sensitive token detection, and manual confirmation boundary**
- [ ] **Step 2: Run targeted tests and confirm failure**
- [ ] **Step 3: Implement OCR adapter invocation, redaction hints, confidence thresholds, and failure states**
- [ ] **Step 4: Run targeted tests and verify no command execution path is exposed**

### Task 4: Agent Context and Review UI

**Files:**
- Modify: `backend/src/main/java/com/smartops/service/AssistantService.java`
- Modify: `frontend/src/components/ai/AiChatPanel.vue`
- Create: `frontend/src/components/ai/VisionEventCard.vue`
- Create: `frontend/src/api/visionEvents.js`
- Create: `frontend/test/vision-event-ui.test.mjs`

- [ ] **Step 1: Write failing tests for fact/inference labels, confidence display, and confirmation gating**
- [ ] **Step 2: Run targeted frontend/backend tests and confirm failure**
- [ ] **Step 3: Inject scoped VisionEvent context into the Agent request and render review cards**
- [ ] **Step 4: Run frontend build and targeted tests**

### Task 5: Knowledge and Memory Handoff

**Files:**
- Modify: `backend/src/main/java/com/smartops/service/KnowledgeCandidateService.java`
- Modify: `backend/src/main/java/com/smartops/service/OperatorMemoryService.java`
- Modify: `frontend/src/components/ai/VisionEventCard.vue`
- Create: `backend/src/test/java/com/smartops/service/VisionKnowledgeHandoffTest.java`

- [ ] **Step 1: Write failing tests for explicit confirmation before candidate or memory creation**
- [ ] **Step 2: Run targeted tests and confirm failure**
- [ ] **Step 3: Implement confirmation endpoints and source references**
- [ ] **Step 4: Run all visual, chat attachment, knowledge, and memory tests**

### Task 6: Final Verification

- [ ] **Step 1: Run `npm run build` and `npm run knowledge:check`**
- [ ] **Step 2: Run targeted Maven tests with the project Maven settings**
- [ ] **Step 3: Run browser checks for desktop, mobile, permission denial, paste, and drag/drop**
- [ ] **Step 4: Run `git diff --check` and inspect only task-scoped changes**
