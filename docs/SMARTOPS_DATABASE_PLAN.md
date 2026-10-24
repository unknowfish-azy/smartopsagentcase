# SmartOpsAgent Database Plan

This is a design plan only. No database migration is executed in phase 0.

## Current schema inventory

Current tables cover:

- `server`, `server_metric`
- `inspector_event`, `inspector_issue`, `inspection_evidence`, `inspection_verification`
- `model_connections`
- `operation_session_group`, `operation_credential`, `operation_session`, `operation_known_host`
- `operation_tunnel`, `operation_transfer`, `operation_command`, `operation_audit_event`, `operation_workspace`

The test schema is a reduced H2 version of the server, operation, and inspector foundations. There are no persisted `knowledge_item`, workspace membership, review, runbook, incident, question-bank, or chunk tables yet.

## Planned domain groups

### Identity and scope

`app_user`, `role`, `permission`, `user_role`, `role_permission`, `ops_workspace`, `workspace_member`, `storage_config`, `system_setting`.

Every tenant-scoped operational table should carry `workspace_id`; queries must apply scope at the service/repository boundary.

### Knowledge

`knowledge_type`, `knowledge_category`, `knowledge_source`, `tag`, `knowledge_item`, `knowledge_version`, `knowledge_chunk`, `knowledge_relation`, `knowledge_tag_rel`, `knowledge_review`, `knowledge_review_item`.

Important fields include status, revision, source type, author/owner, risk, content hash, review/expiry timestamps, and compatibility metadata. Existing JavaScript catalog entries should be imported as source-preserving records, not replaced.

### Runtime and incidents

`command_item`, `script_item`, `runbook`, `runbook_step`, `runbook_variable`, `runbook_precheck`, `runbook_postcheck`, `runbook_rollback`, `run_record`, `run_output`, `run_evidence`, `incident`, `incident_event`, `incident_evidence`, `incident_timeline`.

Existing operation command/audit and inspector evidence tables should be assessed for reuse or compatibility views before adding duplicates.

### Questions and assets

`question_bank`, `question`, `question_option`, `wrong_question`, `exam_record`, plus `host_asset`, `service_asset`, `database_asset`, `k8s_cluster`, `k8s_node`, `k8s_namespace`, `k8s_workload`.

### Agent and audit

`agent_session`, `agent_message`, `agent_trace`, `audit_log`, with shared `trace_id` and sensitive-field redaction.

## Migration rules

1. Back up and inventory existing data before any DDL.
2. Add new tables through versioned migrations (Flyway/Liquibase decision is deferred until the backend baseline is confirmed).
3. Keep current tables and API contracts working during migration.
4. Import the current knowledge catalog idempotently using `content_hash` and source metadata.
5. Add indexes based on real queries: workspace, status, category/type, source, updated time, content hash, run/incident status and time.
6. Never store plaintext passwords or secrets; use password hashing for login and encryption/KMS/Vault-compatible handling for recoverable credentials.

