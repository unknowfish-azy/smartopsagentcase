# SmartOpsAgent Module Map

## Current modules

| Current module | Current location | Responsibility | Target relationship |
| --- | --- | --- | --- |
| Server assets | `backend/.../server`, `frontend/src/views/server` | Hosts and metrics CRUD | Asset foundation |
| Inspector | `backend/.../InspectorController`, inspector entities; `frontend/src/views/inspector` | Evidence, issues, verification and statistics | Incident/diagnosis foundation |
| Operations | `backend/.../Operation*`, `backend/.../operations`; `frontend/src/views/operations` | Sessions, credentials, SSH/SFTP, tunnels, files, commands and audit | Runtime/Runbook foundation |
| Model integration | `ModelConnection*`, analytics, frontend model views | Provider configuration, invocation and usage | Agent provider boundary |
| Knowledge catalog | `knowledge/linux/*.js`, `knowledge/cloud_ops`, `frontend/src/views/knowledge` | Read-only searchable built-in knowledge | Import source and compatibility layer |
| Agent/companion | `frontend/src/views/agent`, `domain/companion`, `stores/companion` | Inquiry, execution trace and contextual assistant UI | Agent session/trace boundary |
| Plugins/skills | `frontend/src/domain/plugins`, `domain/skills`, corresponding views | Extensible capability metadata | Future tool and source adapters |

## Target module boundaries

```text
identity       User / Role / Permission / Workspace
knowledge      Item / Type / Category / Source / Version / Review / Relation / Chunk
retrieval      SearchProvider / keyword / semantic / reranker
runbook        Definition / Step / Variable / PreCheck / PostCheck / Rollback
runtime        RunRecord / Output / Evidence / Storage / Trace
incident       Incident / Evidence / Timeline / Resolution / Postmortem
question       Bank / Question / Option / WrongQuestion / Exam
asset          Host / Service / Database / Kubernetes inventory
agent          Session / Message / Diagnosis / Tool / Trace
audit          AuditLog / security events / redaction
```

## Frontend target information architecture

The current routes are intentionally retained during migration. New navigation should be added incrementally behind stable route names and APIs:

```text
Dashboard
Knowledge (catalog, manuals, cases, commands, runbooks, relations)
Agent / Inquiry
Incident
Runbook / Runtime
Question Bank
Assets / Environment
Import
Analytics
System (users, roles, workspaces, sources, settings, audit)
```

The existing `Knowledge` page remains the read-only entry point until persisted CRUD is available. The current workspace-switching concept is a future context layer and must not silently change global search or mutate unrelated users' state.

## API boundary

Controllers should call services, services should enforce workspace/permission/risk rules, and mappers/repositories should own persistence. Existing `ApiResponse` and `PageResponse` contracts should be preserved or adapted through DTO/VO compatibility rather than breaking current frontend consumers.

