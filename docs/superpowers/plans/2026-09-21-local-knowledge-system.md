# Local Knowledge System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local-first, Windows-safe knowledge system with six fixed domains, real local-folder creation/scanning, persistent text indexing, source search, and editorial Vue workflows.

**Architecture:** Vue uses a dedicated knowledge API against the local Spring Boot service. Spring Boot owns path validation, directory creation, read-only recursive ingestion, hash-based incremental scan, and MySQL persistence. The frontend keeps the existing sparse Knowledge Map and adds domain, base detail, scan, search, and creation workflows without pretending to own filesystem access.

**Tech Stack:** Vue 3, Vue Router, Axios, Element Plus, Spring Boot 3.3, Java 17, MyBatis, MySQL, JUnit 5, MockMvc, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-21-local-knowledge-system-design.md`

## Global Constraints

- Fixed domains: Docker, Linux, Kubernetes, 可观测性, 数据库, 安全.
- Windows local-first: only user-chosen C: or D: directories; never scan an entire drive.
- Scanning is read-only and must never execute a local file, script, shell, Docker, or Kubernetes command.
- New-folder creation defaults to `<drive>:\\PersonalOps\\Knowledge\\<Domain>\\<KnowledgeBaseName>`.
- Reject traversal and protected Windows locations: Windows, Program Files, Program Files (x86), ProgramData, System32.
- Skip ignored folders, binaries/archives, oversized files, and sensitive names; never index sensitive file content.
- Base removal deletes metadata/index records only, never source folders or files.
- Do not add cloud, embedding, vector database, PDF/DOCX dependencies, fake folder trees, or watcher claims.
- Retain the existing editorial bilingual visual system and six-row Knowledge Map.

## Review Focus

- Windows normalized paths with Chinese names must remain under an approved C: or D: root and must not resolve into protected directories.
- A source directory containing `.env`, `.pem`, `.key`, `secret`, archives, and ignored subdirectories must not expose their contents in documents, previews, or search.
- Rescan must replace changed file chunks and remove deleted-file chunks without duplicating unchanged documents.
- Removing a base must leave the original selected folder and contents intact while removing all relational index metadata.
- A failed file read or invalid encoding must surface the file path and a stable error status without aborting every other eligible file.

---

### Task 1: Knowledge Schema And Domain Repository

**Files:**
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeDomain.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeBase.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeDocument.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeChunk.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeScan.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeDomainMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeBaseMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeDocumentMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeChunkMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeScanMapper.java`
- Create: `backend/src/main/resources/mapper/KnowledgeDomainMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeBaseMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeDocumentMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeChunkMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeScanMapper.xml`
- Modify: `backend/src/main/resources/db/local-schema.sql`
- Modify: `backend/src/test/resources/schema.sql`
- Modify: `backend/src/test/resources/data.sql`
- Test: `backend/src/test/java/com/smartops/mapper/KnowledgeDomainMapperTest.java`

**Interfaces:**
- Produces `KnowledgeDomainMapper.findAll()`, `findBySlug(String)`, and CRUD mapper interfaces for base/document/chunk/scan persistence.
- Produces a relational foreign-key model that later services use for atomic base removal and incremental scan replacement.

- [ ] **Step 1: Write the failing domain-seed mapper test**

```java
@MybatisTest
class KnowledgeDomainMapperTest {
    @Autowired private KnowledgeDomainMapper mapper;

    @Test
    void returns_the_six_fixed_domains_in_editorial_order() {
        assertThat(mapper.findAll())
                .extracting(KnowledgeDomain::getSlug)
                .containsExactly("docker", "linux", "kubernetes", "observability", "database", "security");
    }
}
```

- [ ] **Step 2: Run the mapper test and verify it fails because the mapper/schema is missing**

Run: `mvn -q -Dtest=KnowledgeDomainMapperTest test`

Expected: compilation or mapper-resolution failure naming `KnowledgeDomainMapper`.

- [ ] **Step 3: Add entities, mapper interfaces/XML, schema, and six deterministic seed rows**

Use `BIGINT` identities, `VARCHAR` fields for identifiers/status/path, `TEXT` for content/error data, and `ON DELETE CASCADE` from base to documents/scans and document to chunks. Keep `knowledge_domain` seed IDs stable and ordered 1 through 6.

- [ ] **Step 4: Run the mapper test and verify it passes**

Run: `mvn -q -Dtest=KnowledgeDomainMapperTest test`

Expected: PASS with exact fixed-domain order.

- [ ] **Step 5: Commit the focused schema change if the workspace is a Git repository**

Run: `git add backend/src backend/src/test && git commit -m "feat: add knowledge persistence schema"`

Expected: skip only when `git rev-parse --show-toplevel` confirms no repository metadata exists.

### Task 2: Windows Path Policy And Create-Base Service

**Files:**
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgePathPolicy.java`
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeStorageProperties.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/CreateKnowledgeBaseRequest.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/KnowledgeBaseResponse.java`
- Create: `backend/src/main/java/com/smartops/service/KnowledgeBaseService.java`
- Create: `backend/src/main/java/com/smartops/service/impl/KnowledgeBaseServiceImpl.java`
- Modify: `backend/src/main/resources/application.yml`
- Test: `backend/src/test/java/com/smartops/knowledge/KnowledgePathPolicyTest.java`
- Test: `backend/src/test/java/com/smartops/service/KnowledgeBaseServiceTest.java`

**Interfaces:**
- Consumes `KnowledgeDomainMapper` and `KnowledgeBaseMapper`.
- Produces `create(CreateKnowledgeBaseRequest)`, `get(Long)`, `listByDomain(String)`, and `remove(Long)` service methods.
- `CreateKnowledgeBaseRequest` fields: `domainSlug`, `name`, `description`, `storageMode`, `drive`, `existingPath`.

- [ ] **Step 1: Write failing path-policy tests for safe C:/D: validation and protected path rejection**

```java
@Test
void creates_a_domain_folder_under_the_selected_drive() {
    Path target = policy.newBasePath("D", "docker", "Docker 实战");
    assertThat(target.toString()).endsWith("D:\\PersonalOps\\Knowledge\\Docker\\Docker 实战");
}

@ParameterizedTest
@ValueSource(strings = {"C:\\Windows", "D:\\Program Files", "C:\\foo\\..\\Windows", "D:\\"})
void rejects_protected_or_drive_root_paths(String path) {
    assertThatThrownBy(() -> policy.existingBasePath(path)).isInstanceOf(BusinessException.class);
}
```

- [ ] **Step 2: Run path-policy tests and verify they fail because the policy is missing**

Run: `mvn -q -Dtest=KnowledgePathPolicyTest test`

Expected: compilation failure naming `KnowledgePathPolicy`.

- [ ] **Step 3: Implement the normalized path policy and configuration binding**

Use `Path.of(...).toAbsolutePath().normalize()`. Accept only a drive-rooted `C:` or `D:` path, reject `C:\\`/`D:\\` themselves, validate leaf names against separators/control characters, resolve the new default folder from the selected drive, and check every protected path after normalization.

- [ ] **Step 4: Write a failing service test for metadata-only removal**

```java
@Test
void removing_a_base_keeps_the_source_folder() throws Exception {
    Path source = tempDir.resolve("Docker 实战");
    Files.createDirectories(source);
    KnowledgeBaseResponse base = service.create(existingFolderRequest(source));

    service.remove(base.id());

    assertThat(Files.isDirectory(source)).isTrue();
    assertThat(baseMapper.findById(base.id())).isNull();
}
```

- [ ] **Step 5: Run the service test and verify it fails because base creation/removal is missing**

Run: `mvn -q -Dtest=KnowledgeBaseServiceTest test`

Expected: failure naming the unimplemented service method.

- [ ] **Step 6: Implement create/list/get/remove with transactional metadata cleanup**

For `NEW_FOLDER`, create only the validated constructed domain/base folder. For `EXISTING_FOLDER`, require a readable existing directory. Persist the canonical root path and never invoke file deletion in `remove`.

- [ ] **Step 7: Run both service and policy tests and verify they pass**

Run: `mvn -q -Dtest=KnowledgePathPolicyTest,KnowledgeBaseServiceTest test`

Expected: PASS.

- [ ] **Step 8: Commit the focused service change if Git is available**

Run: `git add backend/src && git commit -m "feat: add safe local knowledge bases"`

### Task 3: Read-Only Scanner, Incremental Index, And Search

**Files:**
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeFileClassifier.java`
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeTextReader.java`
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeChunker.java`
- Create: `backend/src/main/java/com/smartops/service/KnowledgeIndexService.java`
- Create: `backend/src/main/java/com/smartops/service/impl/KnowledgeIndexServiceImpl.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/KnowledgeFileResponse.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/KnowledgeSearchResult.java`
- Modify: `backend/src/main/resources/mapper/KnowledgeDocumentMapper.xml`
- Modify: `backend/src/main/resources/mapper/KnowledgeChunkMapper.xml`
- Test: `backend/src/test/java/com/smartops/knowledge/KnowledgeFileClassifierTest.java`
- Test: `backend/src/test/java/com/smartops/service/KnowledgeIndexServiceTest.java`

**Interfaces:**
- Consumes `KnowledgeBaseService`, document/chunk/scan mappers, and `KnowledgePathPolicy`.
- Produces `scan(Long)`, `files(Long, String, String)`, `file(Long, Long)`, and `search(String, String)`.
- Search result includes domain, base, document ID, relative path, match excerpt, and chunk index.

- [ ] **Step 1: Write failing classifier tests for eligible, ignored, binary, and sensitive files**

```java
@Test
void marks_env_and_private_key_files_sensitive_without_indexing_content() {
    assertThat(classifier.classify(Path.of("D:/docs/.env")).status()).isEqualTo("SENSITIVE");
    assertThat(classifier.classify(Path.of("D:/docs/access.key")).status()).isEqualTo("SENSITIVE");
}

@Test
void skips_ignored_directories_and_archives() {
    assertThat(classifier.classify(Path.of("D:/docs/node_modules/a.md")).status()).isEqualTo("SKIPPED");
    assertThat(classifier.classify(Path.of("D:/docs/archive.zip")).status()).isEqualTo("SKIPPED");
}
```

- [ ] **Step 2: Run classifier tests and verify they fail**

Run: `mvn -q -Dtest=KnowledgeFileClassifierTest test`

Expected: compilation failure naming `KnowledgeFileClassifier`.

- [ ] **Step 3: Implement supported-type classification and UTF-8 reader**

Support exactly `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.xml`, `.csv`, `.log`, `.conf`, `.ini`, `.toml`; enforce a configurable maximum file size; detect BOM; store per-file skipped/error reason without storing sensitive content.

- [ ] **Step 4: Write a failing incremental-index test with Chinese names and a changed/deleted source file**

```java
@Test
void rescan_updates_changed_chunks_and_removes_deleted_documents() throws Exception {
    Path root = createBaseWith("网络/排查.md", "docker network bridge first version");
    Long baseId = createBase(root).id();
    indexService.scan(baseId);

    write(root.resolve("网络/排查.md"), "docker network bridge revised version");
    Files.delete(root.resolve("网络/排查.md"));
    indexService.scan(baseId);

    assertThat(documentMapper.findByBaseId(baseId)).isEmpty();
    assertThat(chunkMapper.search("first version", null)).isEmpty();
}
```

- [ ] **Step 5: Run the index test and verify it fails because scanning is missing**

Run: `mvn -q -Dtest=KnowledgeIndexServiceTest test`

Expected: failure naming `scan` or missing document/chunk behavior.

- [ ] **Step 6: Implement recursive scan, SHA-256 hashing, chunks, and metadata reconciliation**

Walk only below the stored base root. Reuse unchanged documents by hash, atomically replace chunks for changed files, create scan statistics, record per-file failures, and delete database records for no-longer-seen files. Split text at paragraph/newline boundaries with a bounded maximum character length and include source metadata for each chunk.

- [ ] **Step 7: Add a failing search-source test and implement chunk search**

```java
@Test
void search_returns_excerpt_and_real_source_path() {
    index("Docker/网络.md", "Bridge networking connects containers on an isolated network");
    assertThat(indexService.search("bridge networking", "docker"))
            .singleElement()
            .satisfies(result -> {
                assertThat(result.relativePath()).isEqualTo("Docker/网络.md");
                assertThat(result.excerpt()).containsIgnoringCase("Bridge networking");
            });
}
```

Run: `mvn -q -Dtest=KnowledgeIndexServiceTest test`

Expected before implementation: FAIL; after mapper/service implementation: PASS.

- [ ] **Step 8: Run scanner and full backend unit tests**

Run: `mvn -q test`

Expected: PASS.

- [ ] **Step 9: Commit the focused scan/index change if Git is available**

Run: `git add backend/src && git commit -m "feat: index local knowledge folders"`

### Task 4: Knowledge REST API

**Files:**
- Create: `backend/src/main/java/com/smartops/controller/KnowledgeController.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/KnowledgeDomainResponse.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/KnowledgeBaseDetailResponse.java`
- Test: `backend/src/test/java/com/smartops/controller/KnowledgeControllerTest.java`

**Interfaces:**
- Consumes `KnowledgeBaseService` and `KnowledgeIndexService`.
- Produces the endpoints specified in the design document with `ApiResponse<T>` envelopes.

- [ ] **Step 1: Write failing MockMvc tests for creating a base and rejecting a protected existing folder**

```java
@Test
void creates_a_new_docker_base_in_the_selected_drive() throws Exception {
    mockMvc.perform(post("/api/knowledge/bases")
            .contentType(APPLICATION_JSON)
            .content("{\"domainSlug\":\"docker\",\"name\":\"Docker 实战\",\"storageMode\":\"NEW_FOLDER\",\"drive\":\"D\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.name").value("Docker 实战"));
}
```

- [ ] **Step 2: Run controller tests and verify they fail because the controller is missing**

Run: `mvn -q -Dtest=KnowledgeControllerTest test`

Expected: 404 or missing controller failure.

- [ ] **Step 3: Implement domain, base, scan, file, preview, delete, and search endpoints**

Map business validation errors to clear `ApiResponse.error` messages that include the stable status code. Keep scans synchronous for this first release so the UI always displays real, completed counts; return the latest scan record in the response.

- [ ] **Step 4: Add endpoint tests for scan/search/source preview and metadata-only delete**

```java
@Test
void search_returns_source_metadata_without_sensitive_content() throws Exception {
    mockMvc.perform(get("/api/knowledge/search").param("q", "bridge"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data[0].relativePath").exists())
        .andExpect(jsonPath("$.data[0].excerpt").exists());
}
```

- [ ] **Step 5: Run controller and full backend tests**

Run: `mvn -q test`

Expected: PASS.

- [ ] **Step 6: Commit the API change if Git is available**

Run: `git add backend/src && git commit -m "feat: expose local knowledge API"`

### Task 5: Frontend API And Knowledge Routes

**Files:**
- Create: `frontend/src/api/knowledge.js`
- Create: `frontend/src/views/knowledge/knowledgeDomains.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/knowledge/KnowledgeView.vue`
- Test: `frontend/test/knowledge-api.test.mjs`
- Test: `frontend/test/knowledge-domains.test.mjs`

**Interfaces:**
- Consumes `/api/knowledge` API contract from Task 4.
- Produces `getKnowledgeDomains`, `getKnowledgeDomain`, `createKnowledgeBase`, `getKnowledgeBase`, `scanKnowledgeBase`, `getKnowledgeFiles`, `getKnowledgeFile`, `removeKnowledgeBase`, `searchKnowledge`.
- Produces routes `/knowledge/:domainSlug` and `/knowledge/bases/:id`.

- [ ] **Step 1: Write failing frontend tests for fixed domain configuration and endpoint construction**

```js
test('knowledge map exposes the six fixed domains in order', () => {
  assert.deepEqual(knowledgeDomains.map(domain => domain.slug), [
    'docker', 'linux', 'kubernetes', 'observability', 'database', 'security'
  ])
})

test('createKnowledgeBase sends the selected storage mode to the local API', async () => {
  await createKnowledgeBase({ domainSlug: 'docker', name: 'Docker 实战', storageMode: 'NEW_FOLDER', drive: 'D' })
  assert.equal(lastRequest.url, '/api/knowledge/bases')
})
```

- [ ] **Step 2: Run the new frontend tests and verify they fail because modules are missing**

Run: `npm test -- test/knowledge-domains.test.mjs test/knowledge-api.test.mjs`

Expected: module-resolution failure.

- [ ] **Step 3: Implement the API module, canonical six-domain config, map links, and lazy routes**

Replace current hash anchors with `RouterLink` rows. Preserve numbers, descriptions, thin borders, bilingual labels, and current Knowledge Map whitespace.

- [ ] **Step 4: Run the new frontend tests and verify they pass**

Run: `npm test -- test/knowledge-domains.test.mjs test/knowledge-api.test.mjs`

Expected: PASS.

- [ ] **Step 5: Commit frontend routing/API changes if Git is available**

Run: `git add frontend/src frontend/test && git commit -m "feat: add knowledge domain routes"`

### Task 6: Domain Page And Real Create-Knowledge-Base Flow

**Files:**
- Create: `frontend/src/views/knowledge/KnowledgeDomainView.vue`
- Create: `frontend/src/components/knowledge/CreateKnowledgeBaseDialog.vue`
- Modify: `frontend/src/assets/styles/variables.css` only if a missing semantic token is required
- Test: `frontend/test/knowledge-create-flow.test.mjs`

**Interfaces:**
- Consumes domain/base API functions and route param `domainSlug`.
- Produces a creation request with exact fields `{ domainSlug, name, description, storageMode, drive, existingPath }`.

- [ ] **Step 1: Write a failing pure-flow test for creation mode validation**

```js
test('existing-folder mode requires a real selected path', () => {
  assert.equal(validateKnowledgeBaseDraft({ storageMode: 'EXISTING_FOLDER', name: 'Docker 实战', existingPath: '' }), 'SELECT_A_FOLDER')
})

test('new-folder mode requires only a valid C or D drive and name', () => {
  assert.equal(validateKnowledgeBaseDraft({ storageMode: 'NEW_FOLDER', name: 'Docker 实战', drive: 'D' }), null)
})
```

- [ ] **Step 2: Run the test and verify it fails because the flow helper is missing**

Run: `npm test -- test/knowledge-create-flow.test.mjs`

Expected: import failure for `validateKnowledgeBaseDraft`.

- [ ] **Step 3: Implement editorial domain list and creation dialog**

Use Element Plus form controls only inside the creation flow. Offer `Create new folder` and `Use existing folder` as radio choices, C:/D: as a segmented choice, native `showDirectoryPicker` when available, and a visible existing-path field otherwise. Do not represent local files until the backend response confirms creation.

- [ ] **Step 4: Wire creation to the API, trigger a real scan, and route to base detail after success**

Show `INDEXING KNOWLEDGE` only while the scan API call is executing. Render the returned scan counts/current path, error states, and real base status.

- [ ] **Step 5: Run the create-flow test and frontend suite**

Run: `npm test`

Expected: PASS.

- [ ] **Step 6: Commit the domain/create UI change if Git is available**

Run: `git add frontend/src frontend/test && git commit -m "feat: create local knowledge bases"`

### Task 7: Base Detail, File Index, Preview, And Search

**Files:**
- Create: `frontend/src/views/knowledge/KnowledgeBaseDetailView.vue`
- Create: `frontend/src/components/knowledge/KnowledgeFilePreview.vue`
- Create: `frontend/src/components/knowledge/KnowledgeSearchResults.vue`
- Modify: `frontend/src/router/index.js`
- Test: `frontend/test/knowledge-source-rendering.test.mjs`

**Interfaces:**
- Consumes base/file/search API functions and route param `id`.
- Produces source links from a search result to `/knowledge/bases/:id?file=:fileId`.

- [ ] **Step 1: Write a failing source-rendering test**

```js
test('search source labels preserve domain, base, and relative file path', () => {
  assert.equal(sourceLabel({ domainName: 'Docker', baseName: 'Docker 实战', relativePath: '网络/bridge.md' }), 'DOCKER / Docker 实战 / 网络/bridge.md')
})
```

- [ ] **Step 2: Run the source-rendering test and verify it fails because the formatter is missing**

Run: `npm test -- test/knowledge-source-rendering.test.mjs`

Expected: import failure for `sourceLabel`.

- [ ] **Step 3: Implement the editorial file index and safe document preview**

Render document number, relative path, size, and index status as rows. Render no content for sensitive/skipped files. Provide `RESCAN KNOWLEDGE BASE` and `REMOVE KNOWLEDGE BASE`, with explicit UI copy that removal preserves local source files.

- [ ] **Step 4: Implement search and source navigation**

Search calls the real API, shows match excerpt with domain/base/path metadata, and opens the corresponding safe preview. Keep search controls compact and outside the six-domain map first viewport.

- [ ] **Step 5: Run source rendering and all frontend tests**

Run: `npm test`

Expected: PASS.

- [ ] **Step 6: Commit detail/search UI change if Git is available**

Run: `git add frontend/src frontend/test && git commit -m "feat: browse and search local knowledge"`

### Task 8: End-To-End Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `backend/src/main/resources/application-local.yml`
- Test: `backend/src/test/java/com/smartops/integration/KnowledgePersistenceIntegrationTest.java`

**Interfaces:**
- Consumes all completed API, persistence, scanning, and frontend workflows.
- Produces configuration documentation for `SMARTOPS_KNOWLEDGE_ROOT` and local-first safety boundaries.

- [ ] **Step 1: Write a failing integration test using a temporary Windows-compatible folder tree**

```java
@SpringBootTest
@AutoConfigureMockMvc
class KnowledgePersistenceIntegrationTest {
    @Test
    void creates_scans_searches_and_removes_metadata_without_removing_source_files() throws Exception {
        // Create a temporary approved test root, create a base, write Markdown, scan, search, remove metadata.
        // Assert that source Markdown still exists after API deletion.
    }
}
```

- [ ] **Step 2: Run the integration test and verify it fails before the full flow is wired**

Run: `mvn -q -Dtest=KnowledgePersistenceIntegrationTest test`

Expected: failing endpoint/persistence assertion before integration wiring.

- [ ] **Step 3: Complete integration wiring and document local configuration**

Document the backend process must run on the user’s Windows machine to access its C:/D: filesystem, the default creation location, supported extensions, exclusions, sensitive-file policy, and source-preserving removal. Do not document unsupported folder watching as available.

- [ ] **Step 4: Run backend verification**

Run: `mvn -q test`

Expected: PASS.

- [ ] **Step 5: Run frontend verification**

Run:

```powershell
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' run lint
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' run typecheck
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' test
& 'D:\\RuanJianKaiFa\\RuanJianKaiFa Package\\nodejs\\npm.cmd' run build
```

Expected: all commands PASS; record any pre-existing bundle-size warning separately.

- [ ] **Step 6: Perform local Windows smoke verification**

Create a non-sensitive temporary sample directory beneath the configured approved root containing Chinese paths and `.md`, `.txt`, `.json`, `.yaml`, `.log`, `.env`, and `.zip` files. Verify UI/API creation, scanning, search source metadata, skipped sensitive/archive files, rescan after content change, and metadata-only removal.

- [ ] **Step 7: Commit documentation and final integration test if Git is available**

Run: `git add README.md backend frontend && git commit -m "docs: document local knowledge system"`

## Plan Self-Review

- Spec coverage: Tasks 1-4 implement all persistence, path, scan, search, and API requirements. Tasks 5-7 implement map/domain/create/detail/search UI. Task 8 covers configuration and Windows smoke verification.
- Placeholder scan: no unresolved implementation placeholders are used; the integration-test comment is a test setup description followed by exact required assertions in its task.
- Type consistency: route parameters use `domainSlug` and `id`; base creation uses the same request fields in service, controller, API, and UI tasks; scanner/search names remain `scan`, `files`, `file`, and `search`.
- Review focus: each identified safety/failure input is assigned to Task 2, 3, or 8 tests.
