# SmartOps 分层访问与管理层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为智维 Agent 增加用户层/管理层访问边界、架构总览和管控中心。

**Architecture:** 前端以 `accessModel.js` 作为角色、能力、层级和训练波次的契约。路由守卫和侧栏消费同一契约，管理员页面聚合权限、配置、审计和安全入口；既有运维页面保持原路由和实现。

**Tech Stack:** Vue 3、Vue Router、Pinia、Node test runner。

**Spec:** `docs/superpowers/specs/2026-09-28-smartops-layered-access-design.md`

## Global Constraints

- 遵循用户层 → 管理层 → 应用层 → Agent 智能编排层 → 模型推理层 → 数据资源层 → 基础设施层。
- 高风险动作必须经过人工审批、最小权限和全程留痕。
- 历史无角色预览会话按 `operator` 兼容处理。

## Review Focus

- 缺失或损坏的本地会话不能绕过路由守卫；测试角色解析回退。
- 管理员页面不能误显示给普通用户；测试角色能力矩阵。
- 侧栏切换角色后必须更新入口；测试导航分组。
- 七层架构数据必须包含技术栈和训练波次；测试条目完整性。

### Task 1: Access model and session contract

**Files:**
- Create: `frontend/src/security/accessModel.js`
- Test: `frontend/test/access-model.test.mjs`

- [ ] Define roles, capabilities, architecture layers, training waves, session parsing and `canAccess`.
- [ ] Test fallback role, capability checks and layer catalog completeness.

### Task 2: Role-aware routing and login

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/auth/LoginView.vue`
- Test: `frontend/test/access-routing.test.mjs`

- [ ] Add `/admin` and `/architecture` routes with role metadata.
- [ ] Persist selected role and redirect unauthorized users.
- [ ] Test route metadata and access decisions.

### Task 3: Management and architecture views

**Files:**
- Create: `frontend/src/views/admin/AdminControlCenterView.vue`
- Create: `frontend/src/views/architecture/ArchitectureMapView.vue`

- [ ] Render four management domains and eight training waves.
- [ ] Render seven architecture layers with ownership and technology.

### Task 4: Role-aware navigation

**Files:**
- Modify: `frontend/src/navigation/personalSystemNavigation.js`
- Modify: `frontend/src/components/navigation/PersonalSystemNavigation.vue`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Test: `frontend/test/access-navigation.test.mjs`

- [ ] Add admin groups and switch navigation from the current session role.
- [ ] Preserve existing user navigation and responsive behavior.
- [ ] Test group visibility and route mapping.

### Task 5: Verification

- [ ] Run focused Node tests.
- [ ] Run frontend build and diff checks.
