# Professional Admin Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 落地用户/管理员双入口及真实管理基础，不扩展到未确认外部集成。

**Architecture:** 统一账户与 HttpSession 认证，portal 限制当前会话权限。账户版本、数据库审计和会话撤销形成一致的权限边界；前端使用独立管理布局和真实分页接口。

**Tech Stack:** Spring Boot 3 / Java 17 / JdbcTemplate / MySQL 8、Vue 3 / Vite / Playwright。

**Spec:** `docs/superpowers/specs/2026-10-01-professional-admin-foundation.md`

## Global Constraints

- 保留当前工作区及原有未提交修改；不提交、不建分支、不切换 worktree，避免丢失已部署未提交功能。
- 不明文输出密钥/密码，不调用收费模型，不运行 SSH；真实数据只做已批准迁移，测试账号业务在 H2 / 浏览器 mock 中验证。
- 所有生产变更先有失败测试；不要把权限检查只放在前端。
- 后台服务 Hidden 启动；使用 Java17 和项目 Maven 设置。
- 主线程负责 backend/**、scripts/**、docs/**；前端 worker 仅 frontend/**，写集互斥。

## Review Focus

- 管理员进入 user 模式不能调用管理 API；普通账号即使伪造 portal / role 也不能越权。
- 强制改密不只是 UI 跳转：业务 API 与 WebSocket 都应拒绝。
- 禁用/改密/改角色对已建立会话和正在握手的终端生效。
- 两管理员并发降权/禁用后必须保留至少一个启用管理员。
- 失败不得显示旧数据为成功；审计、列表和会话接口不含认证秘密。

## Task 1: Backend account and session foundation (main)

**Files:** `security/SessionUser.java`, `UserAccountService.java`, new `AccountSessionRegistry.java`, `AccountStateFilter.java`, `SecurityAuditService.java`; `controller/AuthController.java`, new `AdminAccountsController.java`; `config/SecurityConfig.java`; terminal handler; auth schema and new migration.

- [x] Write failing integration tests for portal boundaries, forced password changes, disabled/changed account revocation, safe audit pagination, last-admin protection and concurrent changes.
- [x] Run tests and confirm expected missing behavior.
- [x] Implement schema, transactional lifecycle, live HTTP/WS version checks, registry, audit and endpoints per spec.
- [x] Run focused and full backend tests, package.

## Task 2: Frontend professional workspaces (worker)

**Files:** `frontend/src/security/session.js`, router, LoginView, new AdminLayout and admin pages, user AccountSecurityView, MainLayout controls, related tests.

- [x] Add failing tests for dual login, mode guard, forced password gate and real API contracts.
- [x] Implement separate admin navigation, overview, users, sessions, audit and readiness pages.
- [x] Implement account password flow and explicit workspace switching through login.
- [x] Verify unit/build and isolated browser interactions for light/dark and mobile.

## Task 3: Migration and integration (main)

**Files:** `scripts/windows/migrate-local.ps1`, new migration `V002__admin_foundation.sql`, report/README; shared browser integration test after worker completes.

- [x] Extend migration runner to preserve old checksums and apply new schema after backup.
- [x] Apply local incremental migration, preserve existing users/model data.
- [x] Deploy passing backend, validate real admin/user portals and read-only admin pages; do not mutate real passwords/users for smoke tests.
- [x] Re-run regression suites and inspect screenshots.
- [x] Independent scoped review, resolve significant findings, document outcome and deferred work.

## Execution ledger

- Scope approved by user. Existing dirty workspace retained intentionally; worktree/commit steps superseded by explicit non-destructive workspace constraint.
- Design and API contract fixed before parallel implementation; no external integration prerequisites for this batch.
- 2026-10-02: Backend 116 tests/package passed; deployed on local 8080. Two Important scoped-review findings were reproduced with failing tests, fixed and independently re-reviewed with no remaining Important findings in that scope.
- 2026-10-02: Incremental migration applied after backup, then rerun with matching checksums; existing administrator and two model records preserved. Migration tests 2/2, existing browser regressions 19/19, real session smoke and 20 read-only admin screenshots passed.
- Final visual pass fixed light-login contrast and mobile table readability: 78 computed-style/mobile assertions passed, 36 isolated screenshots captured, 242 unit tests and frontend build passed. Main thread independently reran isolated browser checks and refreshed all 20 real-service screenshots after these fixes. All planned tasks completed.
