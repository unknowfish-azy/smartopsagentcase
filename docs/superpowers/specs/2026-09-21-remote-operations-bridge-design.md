# Remote Operations Bridge Design

## Goal

Extend SmartOpsAgent into a personal remote operations workspace without changing the established Personal System visual framework, Stellar Ocean, organisms, or local Knowledge Space architecture. The first release provides real SSH and SFTP operations from the Windows machine hosting the local backend, with safe session management, terminal workspace controls, jump hosts, tunnels, MultiExec approval, and Agent/Knowledge/Memory integration boundaries.

## Current Architecture Audit

SmartOpsAgent currently runs as a Vue 3 + Vite browser client and a local Spring Boot 3.3 / Java 17 service using MyBatis and MySQL. It is not Electron, Tauri, Wails, or another desktop runtime. There is no existing terminal renderer, WebSocket terminal stream, SSH/SFTP library, protocol adapter, PTY bridge, native serial access, or RDP/VNC implementation.

The backend already has AES-256-GCM encryption for model API keys. This is the initial encrypted credential store for connection passwords. Private keys are stored as validated local-path references, never copied into a database or frontend storage. Future Windows Credential Manager support can replace the encrypted password implementation behind the credential provider interface.

## Product Scope

### Real, First-Release Capabilities

- Session manager: folders/groups, session metadata, tags, favorites, search, recent history
- SSH shell sessions through a local backend bridge
- SFTP listing, upload, download, folder creation, rename, delete with confirmation, and transfer status
- xterm.js terminal over authenticated local WebSocket transport
- Multiple tabs and 2/4-pane layouts; layout state is independent from session lifecycle
- SSH password and identity-file authentication, host-key verification, jump host support, and SSH local/remote/dynamic tunnel lifecycle
- MultiExec across active SSH sessions with target preview and mandatory risk confirmation
- Session, connection, terminal-command, operation-approval, and transfer history
- Ops Agent command analysis/preview; it is read-only by default and cannot silently execute commands
- Knowledge search/source references and optional operational-memory capture through stable API boundaries

### Explicitly Not Available In The First Release

RDP, VNC, Serial, Mosh, WSL, FTP/FTPS, AWS S3, X11, XDMCP, and local shell are not implemented and must not present a connect action. The UI may list them only as `REQUIRES NATIVE BRIDGE`, based on a capability endpoint. Browser iframes are not a substitute for RDP or VNC.

## Operations Bridge

The Spring Boot backend is the local Operations Bridge. A protocol adapter layer prevents terminal and session UI from depending on SSH implementation details:

- `ConnectionAdapter`: `connect`, `disconnect`, `diagnose`, `capabilities`
- `TerminalSession`: `open`, `write`, `resize`, `interrupt`, `close`
- `FileTransferProvider`: `list`, `upload`, `download`, `mkdir`, `rename`, `delete`
- `TunnelProvider`: `start`, `stop`, `restart`, `status`

The first concrete adapters are SSH and SFTP. They operate only from the machine running the backend. The browser sends an explicit session ID and receives terminal events over a local WebSocket channel; it never receives credentials or raw private-key content.

## Session And Credential Model

`operation_session_group`

- `id`, `user_id`, `parent_id`, `name`, `sort_order`, `created_at`, `updated_at`

`operation_session`

- `id`, `user_id`, `group_id`, `name`, `protocol`, `host`, `port`, `username`, `credential_id`, `identity_path`, `jump_session_id`, `working_directory`, `tags_json`, `description`, `accent`, `favorite`, `status`, `last_connected_at`, `created_at`, `updated_at`

`operation_credential`

- `id`, `user_id`, `name`, `type`, `secret_ciphertext`, `last4`, `created_at`, `updated_at`

Password secrets use existing AES-256-GCM encryption and are never returned in API responses, logs, exports, browser storage, terminal history, or model prompts. Identity files use a canonicalized readable local path; the backend reads the file only when opening that SSH session. Import/export serializes credential references only.

`operation_known_host`

- `id`, `session_id`, `host`, `port`, `algorithm`, `fingerprint`, `public_key`, `trusted_at`

Unknown and changed host keys require an explicit `TRUST ONCE`, `TRUST AND SAVE`, or `CANCEL` decision. The bridge never silently trusts a key.

## Workspace, Tabs, And Panes

The Connections route is a dense, original remote-workspace surface under the existing shell. The left region is an editorial session tree; the central region holds session tabs and one, two, or four panes; the right region is the Ops Agent/context panel. The background organisms are subdued to preserve terminal readability.

Tabs reference a session runtime ID. A pane references a tab runtime ID. Closing a pane does not necessarily close a live session until the final tab/pane reference is closed. Reconnect creates a new bridge channel while preserving local terminal scrollback where possible. Workspace layout is persisted per user as tab IDs, pane layout, and active pane only; it does not persist passwords or terminal input.

## SSH, Gateway, And Tunnels

SSH is the only connectable remote shell in this release. Session creation supports host, port 22 default, user name, credential reference or local identity file, timeout, keepalive, terminal type, character set, remote working directory, tags, and optional jump session.

Gateway connection flow is local bridge -> saved jump session -> target host. The jump session must be an SSH session owned by the same user. Gateway diagnostics identify the failing stage: DNS, TCP, host-key verification, authentication, jump host, or target channel.

`operation_tunnel` stores `id`, `session_id`, `name`, `type`, `listen_address`, `listen_port`, `target_host`, `target_port`, `status`, `last_error`, timestamps. `LOCAL`, `REMOTE`, and `DYNAMIC` tunnel types are supported only when the SSH adapter confirms them. The UI shows actual bridge status and does not simulate listening sockets.

## SFTP And Transfers

SFTP is exposed only for an online SSH session. The bridge performs remote directory/file operations and returns real metadata. Destructive remote actions require explicit confirmation. File upload and download are streamed through backend endpoints and stored in `operation_transfer` with `id`, `session_id`, `direction`, `source_path`, `target_path`, `size_bytes`, `transferred_bytes`, `status`, `error_message`, timestamps.

Transfers never execute imported files. The browser may select a local file through its normal file picker; local-path upload access remains constrained to the selected file. The bridge does not claim drag-and-drop operating-system file access beyond browser-supported user-selected files.

## Command Safety, MultiExec, And Audit

Every terminal command has explicit origin: `USER`, `AGENT_SUGGESTION`, or `MULTI_EXEC`. The UI always shows command, exact targets, and risk before a non-interactive action.

`OperationRiskPolicy` assigns `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` using transparent command-pattern rules. Read-only diagnostics remain low risk. Commands including deletion, restart/stop, permission changes, destructive Docker/Kubernetes actions, and SQL destructive statements require confirmation. Critical and production MultiExec actions require a second explicit confirmation. Pattern matching is a safety prompt, not a claim of perfect shell parsing; unknown commands are at least medium risk for batch execution.

`operation_command` stores session/runtime context, normalized command, origin, risk, approval state, exit status, timestamps, and output redaction status. `operation_audit_event` records who, when, target, command reference, approval, and result. Raw passwords and detected secret values are redacted before history, audit, memory, Agent context, or logs are written.

## Agent, Knowledge, And Memory Integration

The existing Agent remains analysis-first. It can inspect selected terminal output, connection metadata, sanitized recent commands, and user-requested Knowledge search results. It must not read password prompts, private keys, full environment dumps, credential files, or unbounded terminal scrollback.

The Agent output is a command suggestion with target and risk. Execution is a separate user action and uses the same approval/audit path as a manual operation. Agent actions cannot directly write to a terminal channel.

Knowledge integration consumes the local Knowledge API search contract and shows base/file/chunk source labels. It does not bulk-load knowledge bases. Memory integration writes a user-approved sanitized incident or runbook record that references session, command, output excerpt, diagnosis, resolution, and Knowledge sources.

## API And WebSocket Surface

REST endpoints under `/api/operations` provide session groups/sessions CRUD, credential metadata CRUD, known-host decisions, tunnel CRUD/lifecycle, transfer metadata, command history, audit, capability discovery, Agent previews, and workspace persistence.

Terminal channels use an authenticated local WebSocket endpoint. Messages are structured as `OPEN`, `INPUT`, `RESIZE`, `INTERRUPT`, `CLOSE`, `OUTPUT`, `EXIT`, `HOST_KEY_REQUIRED`, `STATUS`, and `ERROR`. A channel is bound to the authenticated user and one runtime session. Terminal output is not exposed through broad REST polling.

Diagnostic and connection failures expose protocol, host, port, stage, safe reason, retry action, and editable session ID. They never return a secret or private key content.

## Visual And Capability Rules

Connection Center adds `CONNECTIONS / 远程运维` while retaining the visual hierarchy, bilingual typography, reduced-motion behavior, and organisms established in the Personal System. The terminal is highest visual priority. Stellar Ocean, Whale, Jellyfish, and Spider remain faint and non-interactive behind operations content; a Kubernetes session may expose Spider only as a contextual visual, not an operational control.

The capability endpoint reports each protocol as `SUPPORTED`, `PARTIAL`, `REQUIRES_NATIVE_BRIDGE`, or `NOT_AVAILABLE` with an explanation. First release returns `SUPPORTED` for SSH/SFTP and `REQUIRES_NATIVE_BRIDGE` for the explicitly deferred protocols. UI buttons must honor this response.

## Testing And Verification

Unit tests cover session persistence, encrypted credential non-disclosure, host-key decision flow, path-reference validation, risk classification, redaction, layout independence, and capability gating. Integration tests use a controlled local SSH/SFTP test server to validate SSH shell, SFTP upload/download, host-key rejection, jump-host behavior, tunnel lifecycle, and MultiExec approval blocking. Frontend tests cover API contracts, tab/pane state, risk confirmation, non-connectable protocol states, and Agent source rendering. Browser visual checks cover 1440, 1920, 1024, and 768 widths, terminal overflow, split panes, and reduced motion.

## Non-Goals

- No fake protocol sessions, terminal screenshots, file lists, transfer progress, or connection states
- No direct browser SSH/RDP/VNC/serial/WSL access
- No plaintext password, private key, token, or session-log secret storage
- No background Agent command execution
- No automatic high-risk or batch command execution
- No replacement of established Personal System, stellar ecosystem, or Knowledge Space design
