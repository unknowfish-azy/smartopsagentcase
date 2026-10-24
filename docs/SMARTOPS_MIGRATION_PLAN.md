# SmartOpsAgent Migration Plan

Phase 0 records the path from the current SmartOpsAgent baseline to the knowledge-centered platform. It intentionally contains no code or schema changes.

## Legacy concept mapping

The requested WMS mapping is treated as a conceptual migration guide, not a column-by-column rename:

| Existing/legacy concept | SmartOps target | Action |
| --- | --- | --- |
| Warehouse | OpsWorkspace / KnowledgeWarehouse | Preserve current-context idea; introduce scoped workspace model |
| WarehouseBin | KnowledgeCategory / folder | Rebuild as taxonomy, not physical location |
| CargoType | KnowledgeType | Map to explicit MANUAL/CASE/COMMAND/RUNBOOK/etc. |
| Cargo | KnowledgeItem | Convert to structured content with source, status, version and risk |
| Customer | KnowledgeSource / provider | Preserve provenance and ownership |
| InventoryRecord | KnowledgeCurrentState | Replace quantity semantics with published/versioned state |
| InventoryRunningRecord | KnowledgeChangeHistory | Preserve audit/history intent |
| StockIn | KnowledgeImportTask | Import, parse, chunk, classify and review |
| StockOut | KnowledgePublishTask / export | Publish/export with approval and audit |
| InventoryCheck | KnowledgeReview | Review content and version validity |
| AppUser | User | Keep identity; upgrade hashing, sessions and permissions |
| WarehouseRelativeUser | WorkspaceMember | Scope access by workspace |

## Ordered phases

0. **Inspection (current):** inventory code, routes, schema, APIs, knowledge packs and risks; produce architecture/database/module/migration documents.
1. **Platform shell:** preserve login/layout and add current operations-space context without changing knowledge behavior.
2. **Identity and authorization:** users, roles, permissions, workspaces and membership; close preview-only authorization gaps.
3. **Knowledge core:** persisted KnowledgeItem/type/category/source/tag CRUD, pagination and search, while retaining catalog compatibility.
4. **Version and review:** draft/review/publish/archive/expire lifecycle and revision history.
5. **Relations and retrieval:** relations, chunks, SearchProvider abstraction, then full-text/vector adapters.
6. **Runtime library:** run records, outputs, evidence, storage configuration and trace IDs.
7. **Runbooks:** structured steps, variables, pre/post checks and rollback; begin with safe local execution only.
8. **Incident center:** incident lifecycle, evidence, timeline, resolution, postmortem and candidate knowledge generation.
9. **Question bank:** questions, options, wrong-question and exam records.
10. **Agent integration:** retrieval, evidence-grounded answers, tools, approvals and audit.
11. **Kubernetes/remote/visual extensions:** add only after the preceding contracts are stable.

## Phase gates

Each phase must pass compilation, focused unit/API/UI tests, migration checks, permission checks and a documented acceptance checklist before the next phase starts. A phase must not opportunistically implement later AI, vector, SSH or Kubernetes execution features.

