# 健康诊断与前端体积优化第二阶段实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不引入任意网络探测、Shell、自动修复或定时告警的前提下，增加 C2 轻量视觉模式、健康诊断过期/重试语义和管理员安全策略摘要。

**Architecture:** 复用现有 `theme.js`、Pinia app store、Canvas/Three.js 异步组件和诊断接口。显示模式只影响前端视觉组件加载；健康诊断继续由后端承担权限隔离，前端只维护本地时间戳与过期展示状态；管理员策略摘要只返回限制值和配置布尔值，不返回凭据或固定地址。

**Tech Stack:** Vue 3、Pinia、Vite、Canvas 2D、Three.js 异步组件、Spring Boot 3.3.5、Java 17、JUnit、Node test、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-02-health-diagnostic-phase2-design.md`

## Global Constraints

- 不删除 Three.js 依赖，不提高 `chunkSizeWarningLimit`。
- 不开放任意 URL、扫描网段、自定义请求头、认证凭据传递或任意命令执行。
- 不增加定时任务、告警通知、自动修复、诊断结果持久化或外部模型调用。
- 不修改真实账号、密码、数据库数据或生产环境凭据。
- 显示偏好可以写入现有前端偏好存储，但不得写入诊断原文或响应正文。
- 诊断权限继续由服务端判断，前端筛选不能作为授权依据。
- 浅色/深色主题继续使用现有 CSS 变量和 `data-theme`，不新增无关全局覆盖。

## Review Focus

- 非法视觉模式值必须回退到 `balanced`，不能触发未知组件路径；由显示模式单元测试覆盖。
- 首页轻量模式不能动态导入 Three.js，非首页任何模式也不能提前加载 Three.js；由构建契约和浏览器请求测试覆盖。
- 健康请求失败后旧结果必须标记过期，不能继续显示为当前健康；由组件状态测试和浏览器失败重试覆盖。
- 管理员策略摘要不能包含 token、password、Authorization、Cookie、hostname 或 pinned address；由后端服务测试覆盖。
- 移动端切换模式、重试诊断和主题后不能横向溢出；由 Playwright 在 375px 和 1440px 覆盖。

### Task 1: 显示模式状态与异步视觉边界

**Files:**
- Create: `frontend/src/visual/visualMode.js`
- Modify: `frontend/src/theme.js`
- Modify: `frontend/src/stores/app.js`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/views/dashboard/DashboardView.vue` 或首页视觉组件的实际入口
- Test: `frontend/test/visual-mode.test.mjs`
- Test: `frontend/test/build-optimization.test.mjs`

**Interfaces:**
- `visualMode.js` exports `VISUAL_MODES`, `normalizeVisualMode(value)`, `visualMode`, `setVisualMode(value)` and `isLightweightVisualMode`.
- `normalizeVisualMode` accepts only `balanced`, `lightweight`, `reduced-motion`; unknown values return `balanced`.
- `MainLayout.vue` consumes the reactive mode and chooses Canvas fallback before Three.js enhancement.
- Existing `theme.js` remains the owner of light/dark/system resolution; visual mode must not alter `data-theme`.

- [x] **Step 1: Write failing visual mode tests**

  Add tests for default `balanced`, invalid-value fallback, explicit mode persistence, and independent theme resolution:

  ```js
  test('visual mode normalizes independently from color theme', () => {
    assert.equal(normalizeVisualMode('lightweight'), 'lightweight')
    assert.equal(normalizeVisualMode('unknown'), 'balanced')
    assert.equal(resolveTheme('light', true), 'light')
  })
  ```

- [x] **Step 2: Run the focused test and confirm failure**

  Run from `frontend`: `node --test test/visual-mode.test.mjs`.

  Expected: module/export failure before implementation.

- [x] **Step 3: Implement the minimal visual mode module**

  Use a dedicated storage key such as `smartops_visual_mode`; guard storage access the same way as `theme.js`; do not reuse `smartops_theme`.

- [x] **Step 4: Add the display control without changing theme semantics**

  Add a visible, keyboard-accessible select or equivalent control near the existing theme selector. Its labels must distinguish “平衡视觉”, “轻量视觉”, and “减少动效”. The control must use existing semantic variables in both themes.

- [x] **Step 5: Gate Three.js imports by mode and route**

  Keep Canvas components as the fallback path. Ensure the homepage enhancement component is not dynamically imported when mode is `lightweight` or when the current route is not the dashboard. Preserve the existing non-home Canvas behavior.

- [x] **Step 6: Run focused tests and build contracts**

  Run `node --test test/visual-mode.test.mjs test/build-optimization.test.mjs` and confirm Three.js remains asynchronous and `chunkSizeWarningLimit` is absent.

### Task 2: Health result freshness, retry, and error semantics

**Files:**
- Modify: `frontend/src/components/diagnostics/HealthCheckList.vue`
- Modify: `frontend/src/components/diagnostics/NetworkDiagnosticTool.vue`
- Modify: `frontend/src/api/diagnostics.js` only if stable error metadata needs normalization
- Test: `frontend/test/diagnostic-health-state.test.mjs`
- Modify: `frontend/test/diagnostic-tools.browser.mjs`

**Interfaces:**
- Add pure helpers in a colocated module or named exports: `isFreshCheck(checkedAt, now)`, `healthStateLabel(status, stale)`, and `normalizeDiagnosticFailure(error)`.
- Freshness threshold is exactly five minutes (`300000` ms).
- A failed refresh keeps the previous result only as stale reference; it must expose an error alert and never render stale `HEALTHY` as current.

- [x] **Step 1: Write failing state tests**

  Cover fresh/expired timestamps, unknown timestamps, preserving form target after failure, and mapping timeout/network/assertion failures to stable labels.

- [x] **Step 2: Run focused tests and confirm failure**

  Run `node --test test/diagnostic-health-state.test.mjs` from `frontend`.

- [x] **Step 3: Implement freshness and stale-result state**

  Track `lastCheckedAt`, `stale`, `loading`, and `error` separately. Do not overwrite the previous result with a synthetic healthy result. On failed refresh, mark the previous result stale and keep the retry button enabled.

- [x] **Step 4: Add accessible retry and status copy**

  Render a visible “结果可能已过期” state, `role="status"` while checking, and `role="alert"` for failures. Keep the existing selected diagnostic target and assertion form values when retrying.

- [x] **Step 5: Add browser failure/retry coverage**

  Extend `diagnostic-tools.browser.mjs` with one successful health response followed by a failed response. Assert stale labeling, alert visibility, preserved target, no raw response rendering, and no horizontal overflow in light and dark themes.

### Task 3: Backend diagnostic categories and administrator policy summary

**Files:**
- Modify: `backend/src/main/java/com/smartops/diagnostics/HttpProbeService.java`
- Modify: `backend/src/main/java/com/smartops/diagnostics/CertificateProbeService.java`
- Modify: `backend/src/main/java/com/smartops/diagnostics/HealthDiagnosticService.java`
- Modify: `backend/src/main/java/com/smartops/controller/HealthDiagnosticController.java` only if a new admin summary field is required
- Test: `backend/src/test/java/com/smartops/diagnostics/HealthDiagnosticServiceTest.java`
- Test: `backend/src/test/java/com/smartops/diagnostics/HttpProbeServiceTest.java`
- Test: `backend/src/test/java/com/smartops/diagnostics/CertificateProbeServiceTest.java`

**Interfaces:**
- Preserve existing endpoint paths and existing JSON fields.
- Add nullable/optional `errorCategory` to active probe result records only if serialization remains backward-compatible.
- Add an admin-only `policy` summary containing `targetCount`, `perUserConcurrency`, `globalConcurrency`, `connectTimeoutMs`, `readTimeoutMs`, `maxResponseBytes`, and boolean configuration flags.
- Never include target hostname, pinned address, token, password, Authorization, Cookie, raw response, or exception stack.

- [x] **Step 1: Write failing backend tests**

  Assert timeout maps to `TIMEOUT`, connection/TLS failures map to `NETWORK`, assertion mismatch maps to `ASSERTION`, and admin policy JSON contains only approved keys.

- [x] **Step 2: Run focused Maven tests and confirm failure**

  From `backend`, compile tests with `mvn.cmd -s .mvn/smartops-settings.xml -Dmaven.compiler.fork=false -DskipTests test-compile`, then run the focused Surefire tests.

- [x] **Step 3: Implement stable category mapping**

  Keep user-facing summaries concise and preserve current status values. Ensure invalid assertion input is rejected before network I/O and all limiter leases remain closed in `finally`/try-with-resources paths.

- [x] **Step 4: Implement admin policy summary**

  Return fixed limits from server-side constants/configuration. Use the existing administrator and portal checks before constructing the summary. Keep ordinary user responses unchanged.

- [x] **Step 5: Run focused and affected backend tests**

  Run the diagnostics tests plus existing `OperationToolControllerTest` and `ObservabilityServiceTest`.

### Task 4: Administrator safety presentation and documentation

**Files:**
- Modify: `frontend/src/components/diagnostics/HealthCheckList.vue`
- Modify: `frontend/src/views/admin/AdminReadinessView.vue`
- Modify: `frontend/src/assets/styles/admin.css` only if existing admin variables cannot express the summary
- Modify: `docs/operations/health-and-diagnostic-tools.md`
- Test: `frontend/test/diagnostic-tools.test.mjs`
- Test: `frontend/test/admin-foundation.test.mjs` only if the existing contract needs an additive assertion

**Interfaces:**
- Admin-only copy must state “手动、只读、受白名单控制”.
- Policy summary uses booleans and numeric limits only.
- Normal user pages must not render admin policy data or global dependency details.

- [x] **Step 1: Add contract tests for safe policy rendering**

  Assert admin-only rendering references the policy summary but contains no `token`, `password`, `Authorization`, `Cookie`, `hostname`, or `pinnedAddresses` display paths.

- [x] **Step 2: Implement the admin safety summary**

  Add a compact section below the admin health checks with configuration state, concurrency limits, timeouts, and a link to the operations document. Keep it usable in light and dark themes.

- [x] **Step 3: Update the operations document**

  Document visual mode behavior, freshness threshold, error categories, and the fact that no scheduled alert, auto-remediation, arbitrary URL, or Shell capability exists in this phase.

- [x] **Step 4: Run focused frontend tests**

  Run `node --test test/diagnostic-tools.test.mjs test/admin-foundation.test.mjs`.

### Task 5: Full acceptance and build-size report

**Files:**
- Modify: `frontend/test/diagnostic-tools.browser.mjs`
- Modify: `frontend/test/build-optimization.test.mjs` if new mode contracts need static assertions
- Modify: `frontend/test/visual-check.mjs` only if the new display control changes selectors
- Create: `frontend/test/visual-mode.browser.mjs` if the existing browser scripts become too broad

- [x] **Step 1: Run focused browser checks**

  Start the frontend dev server with the existing local command and run diagnostic, visual, and visual-mode browser scripts at 375px and 1440px.

- [x] **Step 2: Run frontend full suite and build**

  Run `npm.cmd test` and `npm.cmd run build`; record the actual `vendor-three` size and do not suppress warnings.

- [x] **Step 3: Run backend full suite**

  Run test compilation separately when needed, then `mvn.cmd -s .mvn/smartops-settings.xml -Dmaven.compiler.fork=false test`. Record unrelated pre-existing failures separately rather than modifying unrelated modules.

- [x] **Step 4: Run diff and scope checks**

  Run `git diff --check` on all files touched by this phase, inspect for secrets or real addresses, and verify no diagnostic raw text is persisted.

- [x] **Step 5: Report acceptance status**

  Report completed features, test counts, browser widths, actual chunk warning state, and any remaining unrelated failures. Do not commit or create a branch.

## Execution Recommendation

推荐使用 Native 执行：任务之间有明确顺序，且显示模式、诊断组件和后端摘要都依赖当前工作区已有脏改动；由当前助手连续实施可以减少合并冲突。计划审阅通过后，使用 `superpowers:executing-plans` 按任务顺序执行。
