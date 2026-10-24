# Local Knowledge System Design

## Goal

Build a local-first Personal Operations Knowledge Space for Docker, Linux, Kubernetes, Observability, Database, and Security. Users create and manage multiple local knowledge bases backed by folders on the Windows machine running SmartOpsAgent.

## Architecture

SmartOpsAgent remains a Vue 3 browser client backed by the local Spring Boot service. The browser never receives unrestricted filesystem access. The frontend calls a knowledge API; the backend validates Windows paths, creates approved folders, recursively reads supported text files, and persists metadata and text chunks in MySQL.

The optional browser `showDirectoryPicker()` is only used as a convenience to obtain a selected directory name where the browser supports it. The backend remains the authority for path validation, directory creation, scanning, and indexing. Unsupported browsers show a real path entry field and never simulate a C: or D: folder tree.

## Knowledge Domains

The six fixed domains are seeded and cannot be renamed through this feature:

| Order | Slug | Name | Focus |
| --- | --- | --- | --- |
| 01 | docker | Docker | Containers, images, Compose, registry |
| 02 | linux | Linux | Processes, Systemd, network, storage |
| 03 | kubernetes | Kubernetes | Deployments, services, Ingress, recovery |
| 04 | observability | 可观测性 | Metrics, logs, tracing, alerts |
| 05 | database | 数据库 | Connections, backups, recovery, queries |
| 06 | security | 安全 | Access, evidence, policy, audit |

The existing Knowledge Map stays as six editorial rows. Each row routes to its domain page rather than exposing creation controls on the map.

## Data Model

`knowledge_domain`

- `id`, `slug`, `name`, `description`, `sort_order`

`knowledge_base`

- `id`, `domain_id`, `name`, `description`, `root_path`, `storage_mode`, `status`, `created_at`, `updated_at`

`knowledge_document`

- `id`, `knowledge_base_id`, `path`, `relative_path`, `filename`, `extension`, `size_bytes`, `content_hash`, `status`, `sensitive`, `indexed_at`, `updated_at`

`knowledge_chunk`

- `id`, `document_id`, `chunk_index`, `content`, `created_at`, `updated_at`

`knowledge_scan`

- `id`, `knowledge_base_id`, `status`, `started_at`, `finished_at`, `total_files`, `indexed_files`, `skipped_files`, `failed_files`, `current_path`, `error_message`

## Storage And Path Safety

The configured root is `SMARTOPS_KNOWLEDGE_ROOT`, defaulting to `D:\\PersonalOps\\Knowledge` on Windows. The configuration is a default creation location, not a restriction that prevents an explicit, validated existing folder under C: or D: from being indexed.

Creating a new base accepts a drive (`C` or `D`) and a safe folder name. The service constructs:

`<drive>:\\PersonalOps\\Knowledge\\<Domain>\\<KnowledgeBaseName>`

Users may instead select an existing absolute folder under C: or D:. The service normalizes each submitted path, rejects path traversal, requires an existing readable directory, and blocks Windows, Program Files, Program Files (x86), ProgramData, and System32 paths. The service never scans an entire drive from a drive-only path.

Removing a knowledge base deletes only database metadata, chunks, documents, and scan records. It never deletes source files or the source folder.

## Ingestion And Sensitive Data

Scanning is read-only. The service never executes local files, scripts, commands, Docker, or Kubernetes commands.

Supported formats in the first release are `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.xml`, `.csv`, `.log`, `.conf`, `.ini`, and `.toml`. Files are decoded as UTF-8 with BOM handling. PDF and DOCX are deliberately out of scope until a parser dependency is selected independently.

The scanner skips `.git`, `node_modules`, `dist`, `build`, `target`, `.next`, `.cache`, and `coverage`; binary/archive extensions such as `.exe`, `.dll`, `.so`, `.bin`, `.iso`, `.zip`, `.7z`, and `.rar`; and oversized files. Sensitive names such as `.env`, `*.pem`, `*.key`, and names containing `credential`, `secret`, `password`, or `token` are recorded as skipped sensitive files without content indexing or content preview.

Each eligible file is content-hashed. Rescan updates only added or changed files and removes index records for source files no longer present. Text is split into bounded chunks with document and source metadata.

## API

All endpoints are local APIs under `/api/knowledge`:

- `GET /domains` returns the six domains and aggregate base/file/index status
- `GET /domains/{slug}` returns one domain with knowledge bases
- `POST /bases` creates a base from either a new folder request or validated existing path
- `GET /bases/{id}` returns base metadata and latest scan
- `DELETE /bases/{id}` removes index metadata only
- `POST /bases/{id}/scan` runs an incremental scan
- `GET /bases/{id}/files` lists indexed files with query, status, and sort options
- `GET /bases/{id}/files/{fileId}` returns safe content preview and metadata
- `GET /search?q=...&domain=...` searches chunks and returns source information and excerpts

Errors use explicit codes and messages for `PERMISSION_DENIED`, `FOLDER_NOT_FOUND`, `READ_FAILED`, `ENCODING_ERROR`, `PARSE_FAILED`, `SENSITIVE_FILE`, and path validation failures.

## User Interface

The Knowledge Map remains sparse and editorial. Domain pages contain the domain header, a technical metadata row, an editorial list of knowledge bases, and a `+ CREATE KNOWLEDGE BASE` command.

The creation flow has two steps in a compact editorial drawer or dialog:

1. Name and optional description
2. Storage mode: `Create new folder` or `Use existing folder`; choose C: or D: for new folders, or select/provide a validated existing C:/D: path

After creation, the client triggers a real scan and displays live scan counts, current path, and failures from the API. The base detail page supplies file filtering, search, metadata, source preview, and a `RESCAN KNOWLEDGE BASE` command. It must not use card grids or fabricated counts.

The Kubernetes domain may visually coordinate with the Kubernetes Spider, but all file and index behavior is independent of visual organisms. The search response is the stable Agent integration contract; Agent source citation can be implemented without coupling Agent workflows to scanner internals.

## Testing And Verification

Backend tests cover path validation, system path rejection, Chinese directory/file names, folder creation, recursive scans, ignored directories/extensions, sensitive-file exclusion, content hashing/incremental updates, source-preserving deletion, and chunk search. Controller tests cover API contracts and error statuses.

Frontend tests cover domain routing, API request construction, creation mode validation, and source rendering. Final verification runs backend tests, frontend lint/typecheck/tests/build, and a Windows local smoke test against a temporary folder under an approved drive.

## Non-Goals

- No cloud upload, remote embedding, or vector database
- No execution of imported content
- No fake native filesystem browser
- No deletion of original local files through normal knowledge-base removal
- No filesystem watcher claim until a persistent local watcher is implemented
