# SmartOpsAgent Architecture Baseline

This document records the phase 0 inspection baseline. It does not change runtime behavior or the uploaded knowledge packs.

## Current system

The repository already contains a SmartOpsAgent-oriented application rather than an intact legacy WMS implementation.

| Layer | Current baseline | Evidence |
| --- | --- | --- |
| Backend | Spring Boot 3.3.5, Java 17, Spring Web/WebSocket/Security/Validation/Actuator, MyBatis, Redis, MySQL runtime, H2 tests | `backend/pom.xml` |
| Backend modules | Server and metrics, inspector/investigation persistence, model connections/analytics, remote operation sessions, SSH/SFTP/tunnels/files, risk/redaction/audit support | `backend/src/main/java/com/smartops` |
| Persistence | MySQL schema in `backend/src/main/resources/db/local-schema.sql`; H2 test schema in `backend/src/test/resources/schema.sql`; mapper XML for selected modules | `backend/src/main/resources` |
| API envelope | `ApiResponse<T>` and `PageResponse<T>`; current API paths are `/api/servers`, `/api/inspector`, `/api/model-connections`, `/api/operations` and `/api/model-analytics` | `backend/src/main/java/com/smartops/common`, `controller` |
| Security | Spring Security filter chain exists, but `/api/**` is currently permitted and preview authentication is frontend local-storage based | `SecurityConfig.java`, router guard |
| Frontend | Vue 3, Vue Router 4, Pinia, Element Plus, Axios, ECharts, Three.js/Vite | `frontend/package.json` |
| Frontend routes | Dashboard, servers, inspector, agent, knowledge, plugins, skills, connections, tools and model views | `frontend/src/router/index.js` |
| Knowledge | Read-only in-process catalog assembled from JavaScript knowledge packs; tree/search/read APIs exist; no persisted KnowledgeItem CRUD yet | `frontend/src/views/knowledge/knowledgeCatalog.js`, `knowledgeLibrary.js` |
| Runtime evidence | Operation command/session/audit and inspector evidence tables already provide a partial runtime/evidence foundation | `local-schema.sql`, operation and inspector modules |

## Target architecture, staged

```text
Identity / Workspace / Permission
              |
Knowledge domain ---- SearchProvider ---- Agent retrieval
              |             |
Review / Version / Relation  Chunks / embeddings
              |
Runbook ---- Runtime ---- Evidence ---- Incident ---- Knowledge candidate
              |
Assets / Kubernetes observations / Audit / Trace
```

The target is a knowledge-centered operations platform. The current catalog remains the source of truth for uploaded knowledge until a later import/persistence phase is explicitly implemented.

## Non-negotiable boundaries

- Do not delete, rewrite, summarize away, or silently alter uploaded knowledge packs.
- Keep the current read-only catalog and its IDs stable while persistence is designed.
- Do not introduce AI execution, SSH automation, vector storage, or Kubernetes tools in phase 0.
- Passwords, API keys, credentials, certificates, and private keys require hashing/encryption and redaction; no default `admin/admin` behavior may be carried forward.
- Mutating operations require authorization, risk classification, confirmation, audit, and verification.

