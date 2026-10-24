# 远程只读诊断实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. If the user chooses subagent-driven execution, use `superpowers:subagent-driven-development` instead. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有连接中心加入固定任务白名单的 SSH 只读诊断闭环，并为返回结果提供有界、脱敏和可审计的呈现。

**Architecture:** 不复用交互式 `OperationRuntime.write()` 或 `MultiExecService`。新增只读诊断能力契约，服务层将稳定 taskId 映射为静态任务，SSH runtime 通过 exec channel 执行；连接中心复用当前已连接 runtimeId 展示任务和结果。

**Tech Stack:** Java 17、Spring Boot 3.3.5、Apache SSHD 2.12.1、JUnit 5、Vue 3、Axios、Node.js 内置 `node:test`。

**Spec:** `docs/superpowers/specs/2026-09-23-linux-shell-knowledge-remote-diagnostics-design.md`

## Global Constraints

- Runtime 所有权通过 `OperationRuntimeRegistry.requireOwned(runtimeId, userId)` 在服务端验证。
- 连接中心仅当 runtime 对应当前选中的 SSH session 时允许运行诊断。
- 诊断只允许服务端静态任务，不接受或拼接用户命令、参数、路径或服务名。
- 任务执行必须具备超时、输出字节上限、截断标记和 `OperationRedactor` 脱敏。
- 诊断失败关闭，不回退到 SSH 交互终端；首期无写操作，不修改审批流程。
- 不新增远程凭据存储、数据库 schema、任意命令执行能力或生产连接测试。
- 保留实施开始时工作区内已有用户改动；提交时只包含当前任务文件。

## Review Focus

- 未知 taskId 或额外 `command` 字段：不能改变实际静态命令；控制器/服务测试验证。
- 切换到另一个 session 后旧 runtimeId 仍在页面状态：诊断必须禁用，直到当前 session 成功连接；前端状态测试验证。
- 其他用户的 runtimeId：服务端返回既有未找到语义且执行器未被调用；服务单测验证。
- SSH runtime 离线或不实现只读诊断能力：请求失败关闭，不向终端写入；服务单测验证。
- 大量/持续输出或执行超时：返回受限输出、截断/超时状态并释放 channel；执行器测试验证。
- 输出包含密码/token 模式：响应与日志元数据不泄漏原值；脱敏测试验证。

---

### Task 1: 定义固定诊断任务和结果契约

**Files:**
- Create: `backend/src/main/java/com/smartops/operations/ReadOnlyDiagnosticAccess.java`
- Create: `backend/src/main/java/com/smartops/operations/DiagnosticTask.java`
- Create: `backend/src/main/java/com/smartops/operations/DiagnosticResult.java`
- Create: `backend/src/main/java/com/smartops/operations/ReadOnlyDiagnosticChannel.java`
- Test: `backend/src/test/java/com/smartops/operations/DiagnosticTaskTest.java`

**Interfaces:**
- Produces: `ReadOnlyDiagnosticAccess.execute(DiagnosticTask task)`；`DiagnosticTask` 仅有 `PROCESS_SUMMARY`、`FAILED_SERVICES`、`RECENT_SERVICE_ERRORS` 等首期固定任务；`DiagnosticResult` 字段为 `taskId`、`status`（`SUCCEEDED`、`NON_ZERO_EXIT`、`TIMED_OUT`、`FAILED`）、`exitCode`、`startedAt`、`finishedAt`、`durationMillis`、`output`、`truncated`。

- [ ] **Step 1: 写固定任务测试**

```java
@Test
void task_catalog_exposes_only_known_static_tasks() {
    assertThat(DiagnosticTask.fromId("process-summary")).isEqualTo(DiagnosticTask.PROCESS_SUMMARY);
    assertThat(DiagnosticTask.fromId("arbitrary-command")).isEmpty();
    assertThat(DiagnosticTask.PROCESS_SUMMARY.command()).doesNotContain("${", "runtimeId");
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f backend/pom.xml -Dtest=DiagnosticTaskTest test`  
Expected: FAIL，诊断任务类型不存在。

- [ ] **Step 3: 实现任务表和结果类型**

在 `DiagnosticTask` 内定义稳定外部 ID、静态 Linux 命令、固定超时和最大输出字节数；`fromId` 返回 `Optional<DiagnosticTask>`。接口不得接受原始字符串或可变参数。

- [ ] **Step 4: 运行测试确认通过**

Run: `mvn -f backend/pom.xml -Dtest=DiagnosticTaskTest test`  
Expected: PASS，只有枚举定义的 ID 可解析。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/src/main/java/com/smartops/operations/ReadOnlyDiagnosticAccess.java backend/src/main/java/com/smartops/operations/DiagnosticTask.java backend/src/main/java/com/smartops/operations/DiagnosticResult.java backend/src/test/java/com/smartops/operations/DiagnosticTaskTest.java
git commit -m "feat: define read-only diagnostic tasks"
```

### Task 2: 实现有界 SSH exec channel 执行器

**Files:**
- Create: `backend/src/main/java/com/smartops/operations/SshReadOnlyDiagnosticExecutor.java`
- Create: `backend/src/test/java/com/smartops/operations/SshReadOnlyDiagnosticExecutorTest.java`
- Modify: `backend/src/main/java/com/smartops/operations/SshConnectionAdapter.java`

**Interfaces:**
- Consumes: `DiagnosticTask` 静态命令与执行限额。
- Produces: SSH runtime 实现 `ReadOnlyDiagnosticAccess`；命令只从任务枚举读取。
- Produces: 包级 `ReadOnlyDiagnosticChannel` 提供 `void open(Duration timeout) throws IOException`、`InputStream stdout()`、`InputStream stderr()`、`Integer awaitExit(Duration timeout) throws IOException`、`void close()`；执行器接收此接口的 factory 以隔离 Apache SSHD channel 细节。

- [ ] **Step 1: 写输出收集测试**

通过包级 `ReadOnlyDiagnosticChannel` seam 注入 fake channel。接口固定为 `open(Duration timeout)`、`stdout()`、`stderr()`、`awaitExit(Duration timeout)` 和 `close()`；测试正常 stdout/stderr 合并、退出码、输出超过上限时 `truncated=true`、任务超时、非零退出码和关闭释放，并断言 factory 收到的命令与任务定义完全相同。

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f backend/pom.xml -Dtest=SshReadOnlyDiagnosticExecutorTest test`  
Expected: FAIL，执行器尚不存在。

- [ ] **Step 3: 实现 exec channel 生命周期**

通过 `ClientSession.createExecChannel(task.command())` 创建 channel；独立读取 stdout/stderr，按总字节预算收集并截断；在固定 deadline 内等待 exit status；无论成功、超时或异常都关闭 channel。不要调用 `OperationRuntime.write()`。

- [ ] **Step 4: 接入 SSH runtime capability**

实现基于 Apache SSHD `ClientSession` 和 `ChannelExec` 的 channel adapter；让 `SshRuntime` 实现 `ReadOnlyDiagnosticAccess` 并委托执行器；在 registry 注册 runtime 的方式保持不变。

- [ ] **Step 5: 运行执行器测试确认通过**

Run: `mvn -f backend/pom.xml -Dtest=SshReadOnlyDiagnosticExecutorTest test`  
Expected: PASS，退出状态、输出上限、超时和资源释放均有断言。

- [ ] **Step 6: 提交本任务**

```bash
git add backend/src/main/java/com/smartops/operations/SshReadOnlyDiagnosticExecutor.java backend/src/main/java/com/smartops/operations/ReadOnlyDiagnosticChannel.java backend/src/test/java/com/smartops/operations/SshReadOnlyDiagnosticExecutorTest.java backend/src/main/java/com/smartops/operations/SshConnectionAdapter.java
git commit -m "feat: execute bounded SSH diagnostics"
```

### Task 3: 实现诊断服务、授权与审计元数据

**Files:**
- Create: `backend/src/main/java/com/smartops/service/ReadOnlyDiagnosticService.java`
- Create: `backend/src/test/java/com/smartops/service/ReadOnlyDiagnosticServiceTest.java`
- Modify: `backend/src/main/java/com/smartops/operations/DiagnosticResult.java`

**Interfaces:**
- Consumes: `OperationRuntimeRegistry`、`ReadOnlyDiagnosticAccess`、`DiagnosticTask`、`OperationRedactor`。
- Produces: `ReadOnlyDiagnosticService.run(Long userId, String runtimeId, String taskId)` 返回 `DiagnosticResult`。

- [ ] **Step 1: 写服务授权与输入测试**

测试已知任务执行一次；未知任务执行器零调用；不属于当前用户的 runtime 抛 `BusinessException(404, "RUNTIME_NOT_FOUND")` 且执行器零调用；未开放 runtime 与离线 runtime 失败关闭；传入额外命令文本不被服务接口接受。

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f backend/pom.xml -Dtest=ReadOnlyDiagnosticServiceTest test`  
Expected: FAIL，服务尚不存在。

- [ ] **Step 3: 实现任务解析和 runtime 校验**

先调用 `registry.requireOwned(runtimeId, userId)`，再检查 `runtime.isOpen()`、`instanceof ReadOnlyDiagnosticAccess`，再解析 taskId；任何检查失败都不得调用 runtime 能力。

- [ ] **Step 4: 加入脱敏与最小审计**

对所有输出及可返回错误应用 `OperationRedactor.redact`；记录用户 ID、runtime ID、task ID、开始/结束时间和结果状态，不记录未脱敏输出。审计采用项目现有日志机制，不新增数据库表。

- [ ] **Step 5: 运行服务单测确认通过**

Run: `mvn -f backend/pom.xml -Dtest=ReadOnlyDiagnosticServiceTest test`  
Expected: PASS，越权、未知任务、离线和不支持 runtime 均不执行命令。

- [ ] **Step 6: 提交本任务**

```bash
git add backend/src/main/java/com/smartops/service/ReadOnlyDiagnosticService.java backend/src/test/java/com/smartops/service/ReadOnlyDiagnosticServiceTest.java backend/src/main/java/com/smartops/operations/DiagnosticResult.java
git commit -m "feat: secure read-only diagnostic service"
```

### Task 4: 暴露只读诊断 API

**Files:**
- Create: `backend/src/main/java/com/smartops/controller/ReadOnlyDiagnosticController.java`
- Create: `backend/src/test/java/com/smartops/controller/ReadOnlyDiagnosticControllerTest.java`

**Interfaces:**
- Consumes: `ReadOnlyDiagnosticService.run(userId, runtimeId, taskId)`。
- Produces: `POST /api/operations/runtimes/{runtimeId}/diagnostics`，请求 DTO 仅含 `@NotBlank String taskId`，响应使用 `ApiResponse<DiagnosticResult>`。

- [ ] **Step 1: 写控制器请求测试**

用 MockMvc 验证有效 taskId 委托 service；空 taskId 为 400；额外 `command` 属性即使由 JSON mapper 忽略也不能进入 service 或影响任务；BusinessException 保留项目现有错误响应映射。

- [ ] **Step 2: 运行测试确认失败**

Run: `mvn -f backend/pom.xml -Dtest=ReadOnlyDiagnosticControllerTest test`  
Expected: FAIL，route 尚不存在。

- [ ] **Step 3: 实现窄 DTO 与 route**

在 `/api/operations/runtimes/{runtimeId}/diagnostics` 添加 POST；读取既有 `X-User-Id` header 模式；控制器只把 `taskId` 传给 service，不声明 command、args 或 path。

- [ ] **Step 4: 运行控制器测试确认通过**

Run: `mvn -f backend/pom.xml -Dtest=ReadOnlyDiagnosticControllerTest test`  
Expected: PASS，任意附加字段不能改变静态任务或绕开 service 校验。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/src/main/java/com/smartops/controller/ReadOnlyDiagnosticController.java backend/src/test/java/com/smartops/controller/ReadOnlyDiagnosticControllerTest.java
git commit -m "feat: expose read-only diagnostics endpoint"
```

### Task 5: 在连接中心接入任务与结果视图

**Files:**
- Modify: `frontend/src/api/operations.js`
- Modify: `frontend/src/api/operationsState.js`
- Modify: `frontend/src/views/operations/ConnectionsView.vue`
- Test: `frontend/test/operations-workspace.test.mjs`

**Interfaces:**
- Produces: `runReadOnlyDiagnostic(runtimeId, taskId)`；不传 command 或任务参数。
- UI 使用当前 `ConnectionsView.vue` 已有的 `runtimeId` 和 `selectedSession`，不创建全局 runtime 状态。

- [ ] **Step 1: 写 API 与 UI 状态测试**

在 `frontend/src/api/operationsState.js` 增加纯函数 `canRunReadOnlyDiagnostic(runtimeId, runtimeSessionId, selectedSession)` 并测试：仅当 runtime 在线、runtime 所属 session ID 与当前所选 session ID 相同且协议为 SSH 时返回 true。另验证切换会话后旧 runtime 不可触发任务；通过代码审查确认 API wrapper 的请求体只有 `taskId`。

- [ ] **Step 2: 运行前端测试确认失败**

Run: `node --test test/operations-workspace.test.mjs`（工作目录 `frontend`）  
Expected: FAIL，诊断 API 和 UI 尚未接入。

- [ ] **Step 3: 添加窄 API wrapper**

新增 `runReadOnlyDiagnostic(runtimeId, taskId)`，POST 到 `/api/operations/runtimes/${runtimeId}/diagnostics`，body 形如 `{ taskId }`；不暴露 command/args/path 参数。连接成功后记录 `runtimeSessionId = selectedSession.id`；切换 session 时保留 runtime 但让 `canRunReadOnlyDiagnostic` 返回 false，只有重新成功连接当前 session 后才允许诊断。

- [ ] **Step 4: 在连接中心增加只读诊断工作区**

增加固定任务选择控件、只读数据范围提示和运行按钮；仅 `canRunReadOnlyDiagnostic(...)` 为 true 时可运行；没有匹配的在线 SSH runtime 时提示先选中并连接 SSH 会话。对 loading、空结果、超时、连接错误、非零退出和截断显示明确状态。结果以纯文本显示，不插入 HTML；不提供执行命令编辑框。

- [ ] **Step 5: 运行前端测试和构建确认通过**

Run: `npm test` 和 `npm run build`（工作目录 `frontend`）  
Expected: PASS；现有连接、终端、隧道和知识页面不回归。

- [ ] **Step 6: 提交本任务**

```bash
git add frontend/src/api/operations.js frontend/src/api/operationsState.js frontend/src/views/operations/ConnectionsView.vue frontend/test/operations-workspace.test.mjs
git commit -m "feat: add SSH read-only diagnostics workspace"
```

### Task 6: 全量验证与安全回归

**Files:**
- Verify: 后端诊断与现有运维测试。
- Verify: `frontend` 测试、lint、build。

**Interfaces:**
- Consumes: Tasks 1–5 的交付。
- Produces: 可复现验证结果；无真实主机连接。

- [ ] **Step 1: 运行后端全量测试**

Run: `mvn -f backend/pom.xml test`  
Expected: PASS；若有失败，按失败测试定位并修复，不跳过或删除既有测试。

- [ ] **Step 2: 运行前端测试、lint 和 build**

Run（工作目录 `frontend`）：`npm test`、`npm run lint`、`npm run build`。  
Expected: 全部 PASS。

- [ ] **Step 3: 检查差异和工作区隔离**

Run: `git diff --check`、`git status --short`。确认只读诊断不触碰 `OperationRuntime.write()`、MultiExec 审批、SFTP 写能力或数据库 schema；确认用户先前的未提交改动未被覆盖。前端额外运行 `npm run visual-check` 检查连接中心诊断状态无重叠且结果区非空白。

- [ ] **Step 4: 汇总验证并提交最终集成**

若前三个任务提交已覆盖全部功能，不创建空提交；记录各测试命令和结果，并将任何需要用户决定的问题单独列出。
