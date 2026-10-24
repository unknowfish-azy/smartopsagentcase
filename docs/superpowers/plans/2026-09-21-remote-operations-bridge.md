# Remote Operations Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real local SSH/SFTP operations workspace with secure sessions, terminal tabs/panes, gateway/tunnels, command approval, and Agent/Knowledge/Memory integration boundaries.

**Architecture:** Spring Boot becomes the local Operations Bridge using Apache Mina SSHD for SSH/SFTP and Spring WebSocket for terminal streams. Vue renders a dense but original Connections workspace through xterm.js, while REST owns persistent metadata and WebSocket owns live terminal I/O. Deferred protocols are capability-gated rather than simulated.

**Tech Stack:** Vue 3, Vue Router, Pinia, Axios, xterm.js, Element Plus, Spring Boot 3.3, Java 17, MyBatis, MySQL, Spring WebSocket, Apache Mina SSHD 2.12.1, JUnit 5, MockMvc.

**Spec:** `docs/superpowers/specs/2026-09-21-remote-operations-bridge-design.md`

## Global Constraints

- Retain the Personal System, Stellar Ocean, organisms, typography, and existing Knowledge Space architecture.
- The backend process is the only component allowed to establish SSH/SFTP connections.
- SSH/SFTP are the only connectable remote protocols in this release; RDP, VNC, Serial, Mosh, WSL, FTP/FTPS, S3, X11, XDMCP, and local shell must be capability-gated as `REQUIRES_NATIVE_BRIDGE`.
- Never store or expose plaintext passwords, private-key bytes, tokens, or secrets in browser storage, API responses, exports, terminal logs, history, Agent prompts, or audit records.
- Unknown and changed SSH host keys always require `TRUST ONCE`, `TRUST AND SAVE`, or `CANCEL`.
- Agent analysis is read-only; every execution uses user-visible command, target, risk, and approval.
- MultiExec requires target preview; high-risk commands require confirmation and critical/production batches require a second confirmation.
- SFTP actions and transfer states must represent real bridge operations; destructive remote operations require confirmation.
- Remote Operations integrates with Knowledge only through its HTTP search contract and must not modify Knowledge schema or scanning behavior.

## Review Focus

- Credential ciphertext and private-key references must never be returned from any API, WebSocket frame, history row, error response, or export payload.
- A changed host key must block terminal creation until a new explicit trust decision, even when the host/port match an existing session.
- A blocked MultiExec command must not write bytes to any target channel before every required confirmation is present.
- Terminal close, browser disconnect, and pane close must release only the correct runtime and must not leave SSH channels or tunnel sockets orphaned.
- Deferred protocol session creation must be rejected by the API as well as disabled in the UI; a direct REST request must not bypass capability gating.

---

### Task 1: Bridge Dependencies, Schema, And Protocol Capability Service

**Files:**
- Modify: `backend/pom.xml`
- Modify: `frontend/package.json`
- Modify: `backend/src/main/resources/db/local-schema.sql`
- Modify: `backend/src/test/resources/schema.sql`
- Modify: `backend/src/test/resources/data.sql`
- Create: `backend/src/main/java/com/smartops/operations/ProtocolCapability.java`
- Create: `backend/src/main/java/com/smartops/operations/OperationsCapabilityService.java`
- Create: `backend/src/main/java/com/smartops/operations/OperationsProtocol.java`
- Test: `backend/src/test/java/com/smartops/operations/OperationsCapabilityServiceTest.java`

**Interfaces:**
- Produces `OperationsCapabilityService.list()` and `requireSupported(OperationsProtocol protocol)`.
- Produces all operations tables: groups, sessions, credentials, known hosts, tunnels, transfers, commands, audit events, and workspace layout.

- [ ] **Step 1: Write the failing capability test**

```java
@Test
void reports_only_ssh_and_sftp_as_connectable_in_first_release() {
    Map<OperationsProtocol, ProtocolCapability> capabilities = service.list();
    assertThat(capabilities.get(OperationsProtocol.SSH).status()).isEqualTo("SUPPORTED");
    assertThat(capabilities.get(OperationsProtocol.SFTP).status()).isEqualTo("SUPPORTED");
    assertThat(capabilities.get(OperationsProtocol.RDP).status()).isEqualTo("REQUIRES_NATIVE_BRIDGE");
}
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `mvn -q -Dtest=OperationsCapabilityServiceTest test`

Expected: compilation failure for the missing operations capability types.

- [ ] **Step 3: Add minimal runtime dependencies and schema**

Add `spring-boot-starter-websocket`, `org.apache.sshd:sshd-core:2.12.1`, `org.apache.sshd:sshd-sftp:2.12.1`, and frontend `@xterm/xterm:5.5.0`, `@xterm/addon-fit:0.10.0`. Add FK-constrained operations tables, unique session known-host key `(session_id, host, port)`, and no secret columns outside `operation_credential.secret_ciphertext`.

- [ ] **Step 4: Implement the fixed capability map**

```java
public ProtocolCapability requireSupported(OperationsProtocol protocol) {
    ProtocolCapability capability = list().get(protocol);
    if (!"SUPPORTED".equals(capability.status())) {
        throw new BusinessException(409, "REQUIRES_NATIVE_BRIDGE: " + protocol);
    }
    return capability;
}
```

- [ ] **Step 5: Run capability tests and mapper smoke tests**

Run: `mvn -q -Dtest=OperationsCapabilityServiceTest test`

Expected: PASS.

- [ ] **Step 6: Commit if repository metadata exists**

Run: `git add backend/pom.xml frontend/package.json backend/src && git commit -m "feat: add operations bridge foundation"`

Expected: skip only after `git rev-parse --show-toplevel` confirms that no Git repository exists.

### Task 2: Session Groups, Encrypted Credentials, And Session API

**Files:**
- Create: `backend/src/main/java/com/smartops/entity/OperationSessionGroup.java`
- Create: `backend/src/main/java/com/smartops/entity/OperationSession.java`
- Create: `backend/src/main/java/com/smartops/entity/OperationCredential.java`
- Create: `backend/src/main/java/com/smartops/mapper/OperationSessionGroupMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/OperationSessionMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/OperationCredentialMapper.java`
- Create: `backend/src/main/resources/mapper/OperationSessionGroupMapper.xml`
- Create: `backend/src/main/resources/mapper/OperationSessionMapper.xml`
- Create: `backend/src/main/resources/mapper/OperationCredentialMapper.xml`
- Create: `backend/src/main/java/com/smartops/dto/operations/CreateOperationSessionRequest.java`
- Create: `backend/src/main/java/com/smartops/dto/operations/OperationSessionResponse.java`
- Create: `backend/src/main/java/com/smartops/dto/operations/OperationCredentialResponse.java`
- Create: `backend/src/main/java/com/smartops/service/OperationSessionService.java`
- Create: `backend/src/main/java/com/smartops/service/impl/OperationSessionServiceImpl.java`
- Create: `backend/src/main/java/com/smartops/controller/OperationSessionController.java`
- Test: `backend/src/test/java/com/smartops/service/OperationSessionServiceTest.java`
- Test: `backend/src/test/java/com/smartops/controller/OperationSessionControllerTest.java`

**Interfaces:**
- Consumes `AesGcmCryptoService` and `OperationsCapabilityService`.
- Produces group/session/credential CRUD under `/api/operations`, session search/favorite/recent fields, and secret-free response DTOs.

- [ ] **Step 1: Write failing credential disclosure and protocol-gating tests**

```java
@Test
void creates_password_credential_without_returning_ciphertext_or_plaintext() {
    OperationSessionResponse response = service.create(userId, sshRequest("operator-password"));
    assertThat(response.credential()).doesNotContain("operator-password");
    assertThat(response.credential()).contains("****");
}

@Test
void rejects_deferred_protocol_even_when_posted_directly_to_api() {
    assertThatThrownBy(() -> service.create(userId, sessionRequest(OperationsProtocol.RDP)))
        .hasMessageContaining("REQUIRES_NATIVE_BRIDGE");
}
```

- [ ] **Step 2: Run service tests and verify they fail**

Run: `mvn -q -Dtest=OperationSessionServiceTest test`

Expected: compilation failure for `OperationSessionService`.

- [ ] **Step 3: Implement encrypted credential references and session persistence**

Encrypt a submitted password immediately with `AesGcmCryptoService`; retain only masked last four characters in response DTOs. Validate `identityPath` with `Path.of(...).toRealPath()` and retain only canonical, readable regular-file references. Session create accepts only SSH/SFTP, validates host/port/user, and stores group, tag JSON, favorite, jump-session ID, working directory, and safe display metadata.

- [ ] **Step 4: Write a failing MockMvc test for session tree response**

```java
mockMvc.perform(get("/api/operations/sessions").header("X-User-Id", "1"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.data[0].name").value("prod-web-01"))
    .andExpect(jsonPath("$.data[0].credential.secretCiphertext").doesNotExist());
```

- [ ] **Step 5: Implement CRUD/search/favorite/recent controller endpoints and run tests**

Run: `mvn -q -Dtest=OperationSessionServiceTest,OperationSessionControllerTest test`

Expected: PASS.

- [ ] **Step 6: Commit if Git is available**

Run: `git add backend/src && git commit -m "feat: manage secure operation sessions"`

### Task 3: SSH Connection Runtime And Host-Key Trust Flow

**Files:**
- Create: `backend/src/main/java/com/smartops/operations/ConnectionAdapter.java`
- Create: `backend/src/main/java/com/smartops/operations/SshConnectionAdapter.java`
- Create: `backend/src/main/java/com/smartops/operations/OperationRuntimeRegistry.java`
- Create: `backend/src/main/java/com/smartops/entity/OperationKnownHost.java`
- Create: `backend/src/main/java/com/smartops/mapper/OperationKnownHostMapper.java`
- Create: `backend/src/main/resources/mapper/OperationKnownHostMapper.xml`
- Create: `backend/src/main/java/com/smartops/dto/operations/HostKeyDecisionRequest.java`
- Create: `backend/src/main/java/com/smartops/service/OperationConnectionService.java`
- Create: `backend/src/main/java/com/smartops/controller/OperationConnectionController.java`
- Test: `backend/src/test/java/com/smartops/operations/SshConnectionAdapterTest.java`
- Test: `backend/src/test/java/com/smartops/integration/OperationSshIntegrationTest.java`

**Interfaces:**
- `ConnectionAdapter.connect(OperationSession session, HostKeyDecision decision)` returns `OperationRuntime` or `HostKeyRequired`.
- `OperationRuntimeRegistry.open(Long userId, Long sessionId)` creates exactly one user-owned runtime and `close(String runtimeId)` closes its channels and client.

- [ ] **Step 1: Write a failing host-key test with a controlled Mina SSH server**

```java
@Test
void unknown_host_key_requires_explicit_decision_before_shell_opens() {
    ConnectResult result = adapter.connect(session, HostKeyDecision.none());
    assertThat(result.status()).isEqualTo("HOST_KEY_REQUIRED");
    assertThat(result.fingerprint()).startsWith("SHA256:");
}
```

- [ ] **Step 2: Run the adapter test and verify it fails**

Run: `mvn -q -Dtest=SshConnectionAdapterTest test`

Expected: compilation failure for SSH adapter types.

- [ ] **Step 3: Implement explicit known-host verification and connection runtime**

Configure Apache Mina SSHD to reject unknown/changed keys unless the request carries `TRUST_ONCE` or `TRUST_AND_SAVE`. Persist trusted key algorithm, fingerprint, and encoded public key only after `TRUST_AND_SAVE`. Open sessions with password or canonical private-key reference; do not reuse or log decrypted secrets after connection setup.

- [ ] **Step 4: Add a failing changed-key test, then implement changed-key rejection**

```java
@Test
void changed_key_blocks_reconnect_until_new_trust_decision() {
    trust(serverAKey);
    server.replaceHostKey(serverBKey);
    assertThat(adapter.connect(session, HostKeyDecision.none()).status()).isEqualTo("HOST_KEY_REQUIRED");
}
```

- [ ] **Step 5: Add HTTP connect/trust/diagnostics endpoints and run integration tests**

Return safe stage values `DNS`, `TCP`, `HOST_KEY`, `AUTH`, `JUMP_HOST`, `CHANNEL`; never return a password, identity contents, or raw backend stack trace.

Run: `mvn -q -Dtest=SshConnectionAdapterTest,OperationSshIntegrationTest test`

Expected: PASS.

- [ ] **Step 6: Commit if Git is available**

Run: `git add backend/src && git commit -m "feat: connect SSH sessions with host key trust"`

### Task 4: WebSocket Terminal, Runtime Lifecycle, And Jump Hosts

**Files:**
- Create: `backend/src/main/java/com/smartops/config/OperationsWebSocketConfig.java`
- Create: `backend/src/main/java/com/smartops/operations/TerminalSession.java`
- Create: `backend/src/main/java/com/smartops/operations/SshTerminalSession.java`
- Create: `backend/src/main/java/com/smartops/operations/OperationsTerminalWebSocketHandler.java`
- Create: `backend/src/main/java/com/smartops/operations/TerminalMessage.java`
- Modify: `backend/src/main/java/com/smartops/config/SecurityConfig.java`
- Test: `backend/src/test/java/com/smartops/operations/OperationsTerminalWebSocketHandlerTest.java`
- Test: `backend/src/test/java/com/smartops/integration/OperationJumpHostIntegrationTest.java`

**Interfaces:**
- Browser messages: `OPEN`, `INPUT`, `RESIZE`, `INTERRUPT`, `CLOSE`.
- Bridge messages: `OUTPUT`, `EXIT`, `HOST_KEY_REQUIRED`, `STATUS`, `ERROR`.
- `TerminalSession.write(String)`, `resize(int columns, int rows)`, `interrupt()`, `close()`.

- [ ] **Step 1: Write a failing message-validation test**

```java
@Test
void rejects_input_for_a_runtime_not_owned_by_the_websocket_user() {
    TerminalMessage message = TerminalMessage.input("other-users-runtime", "id\n");
    assertThat(handler.accept(userOne, message).type()).isEqualTo("ERROR");
}
```

- [ ] **Step 2: Run the WebSocket test and verify it fails**

Run: `mvn -q -Dtest=OperationsTerminalWebSocketHandlerTest test`

Expected: compilation failure for handler/message types.

- [ ] **Step 3: Implement authenticated local WebSocket terminal multiplexing**

Bind each runtime to the same `X-User-Id` identity model used by current local APIs. Opening a channel creates an SSH shell only after host-key trust; input writes bytes only to that runtime; resize updates PTY columns/rows; close and socket disconnect cleanly release the channel and client reference.

- [ ] **Step 4: Write a failing jump-host integration test**

```java
@Test
void opens_target_channel_through_a_saved_ssh_jump_session() {
    OperationSession target = sshSession(targetServerPort, jumpSession.getId());
    assertThat(connectionService.connect(userId, target.getId(), HostKeyDecision.trustOnce()).status())
        .isEqualTo("ONLINE");
}
```

- [ ] **Step 5: Implement `local bridge -> jump runtime -> target session` forwarding and rerun tests**

Run: `mvn -q -Dtest=OperationsTerminalWebSocketHandlerTest,OperationJumpHostIntegrationTest test`

Expected: PASS.

- [ ] **Step 6: Commit if Git is available**

Run: `git add backend/src && git commit -m "feat: stream SSH terminals through local bridge"`

### Task 5: SFTP Files And Transfer Queue

**Files:**
- Create: `backend/src/main/java/com/smartops/operations/FileTransferProvider.java`
- Create: `backend/src/main/java/com/smartops/operations/SftpTransferProvider.java`
- Create: `backend/src/main/java/com/smartops/entity/OperationTransfer.java`
- Create: `backend/src/main/java/com/smartops/mapper/OperationTransferMapper.java`
- Create: `backend/src/main/resources/mapper/OperationTransferMapper.xml`
- Create: `backend/src/main/java/com/smartops/service/OperationFileService.java`
- Create: `backend/src/main/java/com/smartops/controller/OperationFileController.java`
- Test: `backend/src/test/java/com/smartops/integration/OperationSftpIntegrationTest.java`

**Interfaces:**
- `FileTransferProvider.list(runtimeId, path)`, `upload(runtimeId, remotePath, InputStream)`, `download(runtimeId, remotePath)`, `mkdir`, `rename`, `delete`.
- `/api/operations/runtimes/{id}/files` exposes directory metadata; transfer responses expose only real status and byte counts.

- [ ] **Step 1: Write a failing SFTP integration test**

```java
@Test
void uploads_then_lists_then_downloads_a_real_remote_file() throws Exception {
    String runtimeId = openTrustedRuntime();
    fileService.upload(runtimeId, "/workspace/中文.txt", new ByteArrayInputStream("observed".getBytes(UTF_8)));
    assertThat(fileService.list(runtimeId, "/workspace")).extracting(RemoteFile::name).contains("中文.txt");
    assertThat(fileService.download(runtimeId, "/workspace/中文.txt")).hasContent("observed");
}
```

- [ ] **Step 2: Run the SFTP test and verify it fails**

Run: `mvn -q -Dtest=OperationSftpIntegrationTest test`

Expected: compilation failure for SFTP provider/service.

- [ ] **Step 3: Implement online-runtime-only SFTP operations and persisted transfers**

Reject SFTP calls unless the runtime is an online user-owned SSH runtime. For upload/download, create transfer records before streaming, update exact transferred byte count while streaming, and mark `READY`, `RUNNING`, `COMPLETED`, `FAILED`, or `CANCELLED`. Require a confirmation token for `delete` and return remote errors such as permission denied without fake success.

- [ ] **Step 4: Add failing remote-delete confirmation test and implement it**

```java
@Test
void remote_delete_requires_a_confirmation_token() {
    assertThatThrownBy(() -> fileService.delete(runtimeId, "/workspace/a.txt", null))
        .hasMessageContaining("CONFIRMATION_REQUIRED");
}
```

- [ ] **Step 5: Run SFTP integration tests**

Run: `mvn -q -Dtest=OperationSftpIntegrationTest test`

Expected: PASS.

- [ ] **Step 6: Commit if Git is available**

Run: `git add backend/src && git commit -m "feat: transfer files through SFTP bridge"`

### Task 6: SSH Tunnels, Risk Policy, MultiExec, And Audit

**Files:**
- Create: `backend/src/main/java/com/smartops/entity/OperationTunnel.java`
- Create: `backend/src/main/java/com/smartops/entity/OperationCommand.java`
- Create: `backend/src/main/java/com/smartops/entity/OperationAuditEvent.java`
- Create: `backend/src/main/java/com/smartops/operations/TunnelProvider.java`
- Create: `backend/src/main/java/com/smartops/operations/SshTunnelProvider.java`
- Create: `backend/src/main/java/com/smartops/operations/OperationRiskPolicy.java`
- Create: `backend/src/main/java/com/smartops/operations/OperationRedactor.java`
- Create: `backend/src/main/java/com/smartops/service/MultiExecService.java`
- Create: `backend/src/main/java/com/smartops/controller/OperationTunnelController.java`
- Create: `backend/src/main/java/com/smartops/controller/MultiExecController.java`
- Test: `backend/src/test/java/com/smartops/operations/OperationRiskPolicyTest.java`
- Test: `backend/src/test/java/com/smartops/service/MultiExecServiceTest.java`

**Interfaces:**
- `OperationRiskPolicy.assess(String command, boolean multiTarget, boolean productionTarget)` returns risk and required approval count.
- `MultiExecService.preview(userId, command, runtimeIds)` returns immutable target set, risk, redacted command, and approval nonce.
- `MultiExecService.execute(userId, previewId, confirmationNonce, secondConfirmationNonce)` writes only after approvals pass.

- [ ] **Step 1: Write failing risk and no-write tests**

```java
@Test
void classifies_kubectl_delete_for_production_batch_as_critical() {
    assertThat(policy.assess("kubectl delete pod api", true, true).risk()).isEqualTo("CRITICAL");
}

@Test
void critical_multiexec_writes_to_zero_targets_without_second_confirmation() {
    MultiExecPreview preview = service.preview(userId, "kubectl delete pod api", productionRuntimes);
    assertThatThrownBy(() -> service.execute(userId, preview.id(), preview.firstNonce(), null));
    assertThat(fakeTerminal.writes()).isEmpty();
}
```

- [ ] **Step 2: Run risk tests and verify they fail**

Run: `mvn -q -Dtest=OperationRiskPolicyTest,MultiExecServiceTest test`

Expected: compilation failure for policy/service.

- [ ] **Step 3: Implement transparent risk policy, redaction, preview, audit, and confirmed send**

Recognize destructive patterns including `rm`, `shutdown`, `reboot`, `systemctl stop|restart`, `docker rm`, `docker system prune`, `kubectl delete`, `DROP`, `TRUNCATE`, `chmod`, and `mv`. Redact password/token/key assignments and `Authorization` values before persistence. Validate every target runtime is online and owned by the caller before creating a preview. Persist command and audit rows before/after confirmed writes.

- [ ] **Step 4: Write a failing tunnel lifecycle test and implement actual SSH tunnel start/stop**

```java
@Test
void starts_and_stops_a_local_forward_on_the_ssh_runtime() {
    OperationTunnel tunnel = tunnels.create(localForward(runtimeId, "127.0.0.1", 15432, "db.internal", 5432));
    assertThat(tunnels.start(userId, tunnel.getId()).status()).isEqualTo("LISTENING");
    assertThat(tunnels.stop(userId, tunnel.getId()).status()).isEqualTo("STOPPED");
}
```

- [ ] **Step 5: Run risk, MultiExec, and tunnel tests**

Run: `mvn -q -Dtest=OperationRiskPolicyTest,MultiExecServiceTest test`

Expected: PASS.

- [ ] **Step 6: Commit if Git is available**

Run: `git add backend/src && git commit -m "feat: protect multiexec and manage SSH tunnels"`

### Task 7: Operations REST, Agent/Knowledge/Memory Contracts, And Workspace Persistence

**Files:**
- Create: `backend/src/main/java/com/smartops/entity/OperationWorkspace.java`
- Create: `backend/src/main/java/com/smartops/operations/AgentOperationContext.java`
- Create: `backend/src/main/java/com/smartops/service/OperationAgentService.java`
- Create: `backend/src/main/java/com/smartops/service/OperationMemoryService.java`
- Create: `backend/src/main/java/com/smartops/controller/OperationAgentController.java`
- Create: `backend/src/main/java/com/smartops/controller/OperationWorkspaceController.java`
- Test: `backend/src/test/java/com/smartops/service/OperationAgentServiceTest.java`
- Test: `backend/src/test/java/com/smartops/controller/OperationWorkspaceControllerTest.java`

**Interfaces:**
- `OperationAgentService.preview(userId, runtimeId, selectedOutput, question)` returns sanitized context, knowledge source list, suggested command, risk, and `requiresApproval=true`.
- `OperationMemoryService.captureApproved(...)` stores a sanitized reference to session, command, result, diagnosis, and knowledge sources.
- Workspace API persists `tabs`, `panes`, and `activePane` only.

- [ ] **Step 1: Write failing Agent sanitization and workspace persistence tests**

```java
@Test
void agent_context_redacts_tokens_and_never_contains_credential_material() {
    AgentOperationContext context = agentService.context(runtimeId, "TOKEN=abc123\nservice healthy");
    assertThat(context.selectedOutput()).doesNotContain("abc123");
    assertThat(context).hasNoNullFieldsOrProperties();
}

@Test
void workspace_layout_persists_tabs_and_panes_without_terminal_input() {
    workspace.save(userId, new WorkspaceLayout(List.of("runtime-1"), "SPLIT_VERTICAL", "pane-1"));
    assertThat(workspace.get(userId).toString()).doesNotContain("password");
}
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `mvn -q -Dtest=OperationAgentServiceTest,OperationWorkspaceControllerTest test`

Expected: compilation failure for missing services.

- [ ] **Step 3: Implement narrow integration contracts**

Use selected output only, cap retained output size, run `OperationRedactor`, and call Knowledge only through `/api/knowledge/search` once its earlier plan is implemented. Agent command previews cannot invoke `TerminalSession.write`. Memory capture requires an explicit approved command/result reference and stores redacted excerpts. Workspace persistence rejects terminal input, credential fields, and unknown runtime ownership.

- [ ] **Step 4: Add REST tests for capabilities, history, Agent preview, and memory approval rejection**

Run: `mvn -q -Dtest=OperationAgentServiceTest,OperationWorkspaceControllerTest test`

Expected: PASS.

- [ ] **Step 5: Commit if Git is available**

Run: `git add backend/src && git commit -m "feat: connect operations with agent knowledge memory"`

### Task 8: Connections Workspace Frontend, Tabs, And Panes

**Files:**
- Create: `frontend/src/api/operations.js`
- Create: `frontend/src/stores/operations.js`
- Create: `frontend/src/views/operations/ConnectionsView.vue`
- Create: `frontend/src/components/operations/SessionTree.vue`
- Create: `frontend/src/components/operations/TerminalWorkspace.vue`
- Create: `frontend/src/components/operations/TerminalPane.vue`
- Create: `frontend/src/components/operations/OperationsToolbar.vue`
- Create: `frontend/src/components/operations/OperationsAgentPanel.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Test: `frontend/test/operations-workspace.test.mjs`
- Test: `frontend/test/operations-capabilities.test.mjs`

**Interfaces:**
- Consumes operations REST API and terminal WebSocket messages.
- Produces route `/connections`, actions `openSession`, `closeTab`, `splitVertical`, `splitHorizontal`, `setPaneLayout`, and `selectRuntime`.

- [ ] **Step 1: Write failing workspace reducer tests**

```js
test('splitting one active terminal creates two panes without duplicating the session runtime', () => {
  const state = splitPane({ tabs: [{ runtimeId: 'r1' }], panes: [{ id: 'p1', runtimeId: 'r1' }] }, 'p1', 'vertical')
  assert.equal(state.panes.length, 2)
  assert.equal(new Set(state.panes.map(pane => pane.runtimeId)).size, 1)
})

test('deferred protocols remain non-connectable from session tree data', () => {
  assert.equal(canConnect({ protocol: 'RDP', capability: 'REQUIRES_NATIVE_BRIDGE' }), false)
})
```

- [ ] **Step 2: Run frontend tests and verify they fail**

Run: `npm test -- test/operations-workspace.test.mjs test/operations-capabilities.test.mjs`

Expected: module resolution failure for operations store/helpers.

- [ ] **Step 3: Implement the route, API module, session tree, and workspace store**

Add `CONNECTIONS / 远程运维` to the primary navigation without removing existing modules. Use an editorial session tree and dense terminal workspace rather than cards. Cap layout at four panes, preserve active tab/pane state, and show exact capability status for deferred protocols.

- [ ] **Step 4: Implement xterm panes and bridge message handling**

Create xterm instances only after a runtime opens; send `RESIZE` through fit-addon sizing; route `INPUT`, `OUTPUT`, `EXIT`, `STATUS`, and `ERROR` by runtime ID. Dispose terminal and websocket references when the final pane closes. Do not render terminal output under background organisms.

- [ ] **Step 5: Run frontend workspace tests**

Run: `npm test -- test/operations-workspace.test.mjs test/operations-capabilities.test.mjs`

Expected: PASS.

- [ ] **Step 6: Commit if Git is available**

Run: `git add frontend/src frontend/test && git commit -m "feat: add remote operations workspace"`

### Task 9: Session Creation, Host-Key UI, SFTP, MultiExec, And Agent Panels

**Files:**
- Create: `frontend/src/components/operations/CreateSessionDialog.vue`
- Create: `frontend/src/components/operations/HostKeyVerificationDialog.vue`
- Create: `frontend/src/components/operations/SftpBrowser.vue`
- Create: `frontend/src/components/operations/TransferQueue.vue`
- Create: `frontend/src/components/operations/MultiExecDialog.vue`
- Create: `frontend/src/components/operations/OperationRiskDialog.vue`
- Create: `frontend/src/components/operations/ProtocolCapabilities.vue`
- Test: `frontend/test/operations-create-session.test.mjs`
- Test: `frontend/test/operations-risk.test.mjs`
- Test: `frontend/test/operations-source-rendering.test.mjs`

**Interfaces:**
- Creation draft fields: `name`, `protocol`, `host`, `port`, `username`, `credential`, `identityPath`, `jumpSessionId`, `tags`, `description`, `favorite`.
- MultiExec requires preview response `id`, `targets`, `risk`, `firstNonce`, and optionally `secondNonce`.

- [ ] **Step 1: Write failing protocol and confirmation tests**

```js
test('SSH creation defaults port to 22 and requires a host and user', () => {
  assert.deepEqual(validateSessionDraft({ protocol: 'SSH', port: 22, host: '', username: '' }), ['HOST_REQUIRED', 'USERNAME_REQUIRED'])
})

test('critical batch execution cannot submit before both confirmations are present', () => {
  assert.equal(canExecutePreview({ risk: 'CRITICAL', firstConfirmed: true, secondConfirmed: false }), false)
})
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `npm test -- test/operations-create-session.test.mjs test/operations-risk.test.mjs`

Expected: import failure for the missing operations form helpers.

- [ ] **Step 3: Implement real session/host-key/transfer workflows**

Create dialog fields map directly to the session API. The key picker records only a returned local path reference; it never reads a key into Vue state. Host-key dialog exposes trust once/save/cancel only when bridge requests it. SFTP browser calls bridge-backed list/upload/download APIs and requires a confirmation dialog before remote delete/rename. Transfer queue uses returned records rather than synthetic progress.

- [ ] **Step 4: Implement MultiExec and Ops Agent safety surfaces**

Show exact target names, group/environment, command, and risk before preview execution. Enforce both confirmation stages for critical batches. Agent panel displays sanitized selected output, source labels from Knowledge search, suggestions, risk, and `EXECUTE` only through the same preview/approval endpoint; it is not a chat clone.

- [ ] **Step 5: Write and run a failing-then-passing Knowledge source label test**

```js
test('knowledge source shows domain, base, and source file without content from a secret', () => {
  assert.equal(sourceLabel({ domainName: 'Linux', baseName: 'Runbooks', relativePath: 'nginx/status.md' }), 'LINUX / Runbooks / nginx/status.md')
})
```

Run: `npm test`

Expected: PASS.

- [ ] **Step 6: Commit if Git is available**

Run: `git add frontend/src frontend/test && git commit -m "feat: operate remote SSH sessions safely"`

### Task 10: Controlled Integration Server, Visual Checks, And Documentation

**Files:**
- Create: `backend/src/test/java/com/smartops/integration/OperationsBridgeIntegrationTest.java`
- Create: `frontend/test/operations-visual-check.mjs`
- Modify: `README.md`
- Modify: `backend/src/main/resources/application-local.yml`

**Interfaces:**
- Consumes all operations bridge, APIs, WebSocket, terminal, and UI components.
- Produces local configuration and verified supported/deferred protocol documentation.

- [ ] **Step 1: Write a failing full-flow integration test against an in-process Mina SSH/SFTP server**

```java
@Test
void creates_trusts_connects_transfers_previews_and_blocks_unconfirmed_critical_batch() throws Exception {
    Long sessionId = createPasswordSession(testServer.port());
    assertHostKeyRequired(sessionId);
    String runtimeId = trustAndOpen(sessionId);
    uploadAndDownload(runtimeId, "runbook.md", "safe operations");
    MultiExecPreview preview = previewCritical(runtimeId, "systemctl restart nginx");
    assertBlockedWithoutConfirmation(preview);
}
```

- [ ] **Step 2: Run the integration test and verify it fails before final wiring**

Run: `mvn -q -Dtest=OperationsBridgeIntegrationTest test`

Expected: failure at the first unimplemented bridge/API integration boundary.

- [ ] **Step 3: Complete wiring and document runtime requirements**

Document that the backend must run on the Windows machine that performs connections, configure AES encryption key and local WebSocket origin, list SSH/SFTP as supported, and list all deferred protocols as `REQUIRES_NATIVE_BRIDGE`. Document no plaintext secret export, no background Agent execution, and original source preservation for Knowledge.

- [ ] **Step 4: Run backend tests**

Run: `mvn -q test`

Expected: PASS.

- [ ] **Step 5: Run frontend checks and visual checks**

Run:

```powershell
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' run lint
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' run typecheck
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' test
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' run build
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' run visual-check
```

Expected: all commands PASS. Inspect Connections at 1440, 1920, 1024, and 768 pixels; verify terminal does not overflow the sidebar, panes remain readable, and reduced motion leaves organisms unobtrusive.

- [ ] **Step 6: Commit documentation and verified integration tests if Git is available**

Run: `git add README.md backend frontend && git commit -m "docs: document remote operations bridge"`

## Plan Self-Review

- Spec coverage: Tasks 1-7 implement the bridge, persistence, capability gating, SSH/SFTP, host-key safety, gateway/tunnel, MultiExec/audit, and Agent/Knowledge/Memory contracts. Tasks 8-9 implement the workspace and safety-driven UI. Task 10 covers end-to-end integration and visual verification.
- Placeholder scan: no unresolved scope markers or generic validation directions are used. Every test task names concrete methods and expected behavior.
- Type consistency: `OperationsCapabilityService`, `OperationSessionService`, `OperationRuntimeRegistry`, `TerminalSession`, `MultiExecService`, and the specified REST/WebSocket message types use consistent names across tasks.
- Review focus: credential disclosure is tested in Task 2 and 7; host-key changes in Task 3; MultiExec zero-write confirmation in Task 6; runtime cleanup in Task 4/8; protocol gating in Tasks 1, 2, and 8.
