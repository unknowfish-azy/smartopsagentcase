# 平台管理员与团队协作治理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分阶段实现平台管理员分级和团队协作分级，并让权限撤销、资源隔离和审批闭环可验证。

**Architecture:** 使用数据库中的平台管理员等级与能力授权、团队成员职务与能力授权，后端统一授权器负责最终判断，前端只负责展示可用操作。平台身份和团队身份保持独立，通过任命关系和审计记录连接。

**Tech Stack:** Spring Boot 3.3 / Java 17 / JdbcTemplate / Flyway SQL migrations / Spring Security / Vue 3 / Node test / JUnit MockMvc。

**Spec:** `docs/superpowers/specs/2026-10-05-platform-team-governance-design.md`

## Global Constraints

- 保留普通用户登录入口；平台管理员入口仍要求管理员会话、MFA 和现有会话状态校验。
- 所有管理变更写入现有 `SecurityAuditService`，并在事务内完成关键身份变更。
- 不删除历史团队角色和运行记录；迁移只增加字段、映射旧值并提供兼容读取。
- 前端权限判断不能替代后端授权；每个写接口必须在服务层再次校验。

## Review Focus

- 并发任命或负责人转让不能产生两个最高管理员或两个团队负责人：在账户/团队行上加锁并测试并发冲突。
- 降权、禁用或撤职后旧会话、待接受邀请和未消费执行授权必须失效：增加集成测试覆盖三种凭证。
- 平台副管理员访问未授权团队必须拒绝，最高管理员保留审计介入能力：覆盖跨团队查询、冻结和成员管理。
- 自定义或未知角色、能力和团队状态必须返回明确的 400/403：覆盖 API 校验。
- 历史 `admin/owner` 数据迁移后仍能登录、列出团队和查看运行记录：增加迁移回归测试。

### Task 1: 平台管理员等级与能力模型

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261005__platform_admin_governance.sql`
- Modify: `backend/src/main/java/com/smartops/security/UserAccountService.java`
- Modify: `backend/src/main/java/com/smartops/controller/AdminAccountsController.java`
- Modify: `backend/src/main/java/com/smartops/security/SessionUser.java`
- Modify: `frontend/src/security/accessModel.js`
- Test: `backend/src/test/java/com/smartops/integration/AdminGovernanceIntegrationTest.java`

- [ ] 增加平台级别、能力、任命人和任命时间字段/表，迁移第一个启用的旧 `admin` 为 `root`，其余旧管理员映射为 `deputy`。
- [ ] 为账户服务增加 `requirePlatformCapability(actor, capability)`、任命、撤销和最高管理员转让方法；转让使用数据库锁并撤销双方旧会话。
- [ ] 将管理员账号更新、重置密码、注册策略和审计读取改为能力校验，保持最后一个启用最高管理员保护。
- [ ] 扩展会话数据和前端角色模型，兼容旧 `role=admin` 会话并显示级别徽章。
- [ ] 测试越级修改、超额转授、重复转让、撤权后的会话失效和最后一位最高管理员保护。

### Task 2: 团队职务与团队能力授权

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261006__team_governance.sql`
- Modify: `backend/src/main/java/com/smartops/service/TeamWorkspaceService.java`
- Modify: `backend/src/main/java/com/smartops/security/TeamResourceAuthorizer.java`
- Modify: `backend/src/main/java/com/smartops/controller/TeamWorkspaceController.java`
- Modify: `frontend/src/domain/team/permissions.js`
- Test: `backend/src/test/java/com/smartops/integration/TeamGovernanceIntegrationTest.java`

- [ ] 增加团队职务能力、任命关系和团队活动表；将 `owner/admin/member/viewer` 映射到负责人、副负责人、成员、观察者。
- [ ] 新增专项负责人职务和能力集合；实现负责人转让、任命、撤职、退出保护和邀请重新校验。
- [ ] 将 `TeamResourceAuthorizer` 的固定角色判断改为团队能力判断，保留 `view/run/approve/manage` 兼容映射。
- [ ] 测试副负责人不能管理负责人或同级、负责人转让并发保护、观察者只读和未知能力拒绝。

### Task 3: 平台管理员的团队治理范围

**Files:**
- Modify: `backend/src/main/java/com/smartops/security/TeamResourceAuthorizer.java`
- Modify: `backend/src/main/java/com/smartops/service/TeamWorkspaceService.java`
- Modify: `backend/src/main/java/com/smartops/controller/AdminTeamsController.java`
- Test: `backend/src/test/java/com/smartops/integration/AdminTeamGovernanceIntegrationTest.java`

- [ ] 用平台 `teams.view/manage/freeze/audit` 授权替代所有 `admin` 自动成为 `root` 的行为。
- [ ] 限制副管理员只能访问被授权团队；最高管理员可全局介入，但每次介入写入原因和审计事件。
- [ ] 团队冻结时拒绝邀请、成员修改、资源修改、发布和运行，并使未消费执行授权失效。
- [ ] 覆盖平台管理员访问未授权团队、冻结/恢复、全局审计和权限撤销后的拒绝测试。

### Task 4: 资源范围与 Agent 协作授权

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261007__team_resource_grants.sql`
- Modify: `backend/src/main/java/com/smartops/service/TeamAgentService.java`
- Modify: `backend/src/main/java/com/smartops/service/TeamAgentRunService.java`
- Modify: `backend/src/main/java/com/smartops/service/TeamWorkspaceService.java`
- Test: `backend/src/test/java/com/smartops/integration/TeamResourceGovernanceIntegrationTest.java`

- [ ] 为 Agent、知识库和连接增加团队归属与成员授权范围；密钥字段只返回给具备明确能力的服务调用。
- [ ] 分离 Agent 查看、编辑草稿、发布、运行和审批能力；版本发布要求 `publish`，执行要求 `run`。
- [ ] 权限撤销、团队冻结或版本变化时，使待执行 grant token 失效。
- [ ] 测试跨团队资源访问、降权后执行、密钥脱敏和版本变更后的审批失效。

### Task 5: 审批中心、活动记录与通知

**Files:**
- Modify: `backend/src/main/resources/db/migration/V20261003__team_agent_runs.sql`
- Create: `backend/src/main/resources/db/migration/V20261008__team_activity_and_notifications.sql`
- Modify: `backend/src/main/java/com/smartops/service/TeamAgentRunService.java`
- Create: `backend/src/main/java/com/smartops/service/TeamActivityService.java`
- Modify: `backend/src/main/java/com/smartops/controller/TeamAgentRunController.java`
- Test: `backend/src/test/java/com/smartops/integration/TeamApprovalGovernanceIntegrationTest.java`

- [ ] 增加风险等级、审批人资格、审批快照和活动记录；发起人不能审批自己的高风险任务。
- [ ] 任务参数、Agent 版本或授权范围变化时清除旧预览和审批结果。
- [ ] 提供团队活动分页和待审批列表接口，记录邀请、任命、发布、审批、冻结和执行事件。
- [ ] 测试自批、重复审批、审批后内容变化、通知已读和降权后待审批任务。

### Task 6: 控制台整合与迁移回归

**Files:**
- Modify: `frontend/src/views/admin/AdminUsersView.vue`
- Create: `frontend/src/views/admin/AdminGovernanceView.vue`
- Modify: `frontend/src/views/admin/AdminTeamsView.vue`
- Modify: `frontend/src/views/team/TeamDetailView.vue`
- Modify: `frontend/src/views/team/TeamCollaborationView.vue`
- Modify: `frontend/src/api/admin.js`
- Modify: `frontend/src/api/teams.js`
- Test: `frontend/test/admin-governance.test.mjs`
- Test: `frontend/test/team-governance.test.mjs`

- [ ] 增加管理员级别、能力矩阵、任命和转让操作；危险操作显示影响范围和二次确认。
- [ ] 在团队详情中加入成员职务、能力、共享资源、待审批和活动记录视图。
- [ ] 根据服务端返回的能力显示入口；处理 401/403、冻结、撤权和过期邀请状态。
- [ ] 运行前端单测、后端集成测试、构建和既有团队/管理员浏览器测试，确认旧数据可用。
