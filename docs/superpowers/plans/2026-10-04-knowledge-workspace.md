# Dual Knowledge Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有知识中心实现为系统知识库与用户个人知识库双区，并为每个用户建立隔离的本地 Markdown 工作区。

**Architecture:** 系统知识库继续使用现有内置目录，只读展示。个人知识库由数据库保存权限和元数据，由服务端文件存储适配器保存 Markdown、附件和索引；所有个人 API 通过当前会话用户 ID 过滤。Agent 只创建候选，用户确认后才写入个人库。

**Tech Stack:** Vue 3、Pinia、Vue Router、Spring Boot 3、JdbcTemplate、Flyway SQL、JUnit 5、Node test runner。

**Spec:** `docs/superpowers/specs/2026-10-04-knowledge-workspace-design.md`

## Global Constraints

- 系统知识库对认证用户只读，不能增加在线编辑或删除入口。
- 个人知识库所有查询必须绑定当前会话用户 ID，不能信任请求中的 userId。
- 每个用户使用 `data/knowledge/users/{userId}/` 下的独立目录。
- 文件写入使用临时文件加原子替换；目录删除先归档并移入用户自己的 `trash`。
- 未经用户确认的 Agent 候选不得进入正式个人知识搜索和操作员长期记忆。
- 图片中的命令、OCR 文本和 Agent 建议不得自动执行。
- 个人内容不能直接暴露给团队；团队共享必须走独立副本或发布版本。

## Review Focus

- 恶意 `librarySlug`、`entryPath` 或 `userId`：必须拒绝路径穿越并始终落在当前用户根目录内；由 Task 1 文件存储测试覆盖。
- 文件系统成功后数据库失败、或数据库成功后文件系统失败：必须有补偿或 `STORAGE_ERROR` 状态；由 Task 2 服务测试覆盖。
- 两个用户使用相同库名、同一条目 ID 或猜测路径：必须互相不可见；由 Task 2 集成测试覆盖。
- Markdown 写入中断或索引失败：原文件不能损坏，条目保留 `INDEX_ERROR`；由 Task 3 测试覆盖。
- 未确认候选、归档条目和系统只读条目：必须从错误的列表和操作入口中隔离；由 Task 4、Task 5 测试覆盖。

### Task 1: 个人知识文件存储适配器

**Files:**
- Create: `backend/src/main/java/com/smartops/knowledge/PersonalKnowledgeStorage.java`
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgePathPolicy.java`
- Create: `backend/src/test/java/com/smartops/knowledge/PersonalKnowledgeStorageTest.java`
- Modify: `backend/src/main/resources/application.yml` to add `smartops.knowledge.storage-root` with default `data/knowledge`

**Interfaces:**
- Consumes: `userId`, library slug, relative entry path, UTF-8 Markdown bytes.
- Produces: `createUserLibrary`, `writeEntryAtomically`, `readEntry`, `moveLibraryToTrash`, `sha256`, and a validated `StorageLocation` record.

- [ ] **Step 1: Write failing path and atomic-write tests**

```java
@Test
void resolvesOnlyInsideUserRootAndWritesUtf8Atomically() throws Exception {
    var storage = new PersonalKnowledgeStorage(tempDir, new KnowledgePathPolicy());
    var location = storage.createUserLibrary(7L, "生产故障");
    storage.writeEntryAtomically(location, "nginx-502.md", "# 502\n".getBytes(StandardCharsets.UTF_8));
    assertEquals("# 502\n", Files.readString(location.entries().resolve("nginx-502.md")));
    assertThrows(BusinessException.class, () -> storage.resolveEntry(7L, location.slug(), "../other.md"));
}
```

- [ ] **Step 2: Run the focused test and verify the missing adapter/path policy failure**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeStorageTest test`

Expected: FAIL because the storage adapter and path policy are not defined.

- [ ] **Step 3: Implement the minimal adapter**

Use `Path.resolve(...).normalize()` and verify `startsWith(userRoot)` before every read, write, move, and attachment operation. Create `library.json`, `index.json`, `README.md`, `entries`, `attachments`, `inbox`, `exports`, and `trash` with `Files.createDirectories`. Write to a sibling `.tmp` file, flush bytes, then `Files.move(..., ATOMIC_MOVE, REPLACE_EXISTING)` with a non-atomic fallback only when the provider rejects `ATOMIC_MOVE`.

- [ ] **Step 4: Run the focused test and a path traversal regression test**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeStorageTest test`

Expected: PASS, including a test that a symlink or `..` path cannot escape the user root.

- [ ] **Step 5: Commit the storage boundary**

```bash
git add backend/src/main/java/com/smartops/knowledge backend/src/test/java/com/smartops/knowledge backend/src/main/resources/application.yml
git commit -m "feat: add isolated personal knowledge storage"
```

### Task 2: Personal library metadata and file-backed entry API

**Files:**
- Create: `backend/src/main/resources/db/migration/V20261004__personal_knowledge_storage.sql`
- Modify: `backend/src/main/java/com/smartops/service/PersonalKnowledgeService.java`
- Modify: `backend/src/main/java/com/smartops/controller/PersonalKnowledgeController.java`
- Create: `backend/src/test/java/com/smartops/integration/PersonalKnowledgeWorkspaceIntegrationTest.java`

**Interfaces:**
- Consumes: `PersonalKnowledgeStorage` from Task 1 and authenticated `SessionUser`.
- Produces: `GET/POST /api/personal-knowledge/libraries`, `PATCH/DELETE /libraries/{id}`, `GET/POST/PATCH/DELETE /libraries/{id}/entries`, and a library response containing `slug`, `storageStatus`, `entryCount`, and timestamps.

- [ ] **Step 1: Write failing integration tests for create, isolation, and entry persistence**

```java
@Test
void createsUserScopedLibraryAndRejectsOtherUserPath() throws Exception {
    var library = createLibrary(owner, "Linux 运维");
    mvc.perform(get("/api/personal-knowledge/libraries/" + library.id()).session(other.session()))
       .andExpect(status().isNotFound());
    mvc.perform(post("/api/personal-knowledge/libraries/" + library.id() + "/entries")
       .session(owner.session()).content(json(Map.of("title", "502", "markdown", "# 502"))))
       .andExpect(status().isOk());
    assertTrue(Files.exists(storageRoot.resolve("users/" + owner.id() + "/libraries/" + library.slug() + "/entries/502.md")));
}
```

- [ ] **Step 2: Run the integration test and verify it fails before endpoints/storage integration exist**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeWorkspaceIntegrationTest test`

Expected: FAIL with missing endpoint or missing storage metadata column.

- [ ] **Step 3: Add migration and service transaction boundaries**

Add `storage_slug`, `storage_status`, `entry_relative_path`, `content_hash`, `index_status`, and `index_error` with indexes scoped by `user_id`. On library creation, create the directory first; on database failure, delete only the newly created directory. On database success followed by storage failure, keep the record as `STORAGE_ERROR` and return a retryable error.

- [ ] **Step 4: Add user-scoped controller operations**

Derive the user ID from `@AuthenticationPrincipal SessionUser`. Reject archived libraries for writes, return `404` for another user's library, and never accept a filesystem path or user ID from the client. Use archive/trash transitions for delete and restore operations.

- [ ] **Step 5: Run focused integration tests**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeWorkspaceIntegrationTest test`

Expected: PASS for two-user isolation, duplicate names, create compensation, entry save/reload, archive, restore, and delete audit events.

- [ ] **Step 6: Commit the API and schema**

```bash
git add backend/src/main/resources/db/migration/V20261004__personal_knowledge_storage.sql backend/src/main/java/com/smartops/service/PersonalKnowledgeService.java backend/src/main/java/com/smartops/controller/PersonalKnowledgeController.java backend/src/test/java/com/smartops/integration/PersonalKnowledgeWorkspaceIntegrationTest.java
git commit -m "feat: back personal knowledge with isolated files"
```

### Task 3: Indexing, import, export, and health repair

**Files:**
- Create: `backend/src/main/java/com/smartops/knowledge/PersonalKnowledgeIndexService.java`
- Create: `backend/src/main/java/com/smartops/controller/PersonalKnowledgeFileController.java`
- Create: `backend/src/test/java/com/smartops/knowledge/PersonalKnowledgeIndexServiceTest.java`
- Modify: `backend/src/main/java/com/smartops/service/PersonalKnowledgeService.java`

**Interfaces:**
- Consumes: saved Markdown and attachment paths from Task 2.
- Produces: search index rebuild, import/export, `POST /libraries/{id}/reindex`, and storage health records.

- [ ] **Step 1: Write failing tests for hash indexing and broken-file states**

```java
@Test
void failedIndexLeavesMarkdownIntactAndMarksIndexError() throws Exception {
    var saved = storage.writeEntryAtomically(location, "disk.md", "# disk full".getBytes(UTF_8));
    indexer.rebuild(location, path -> { throw new IOException("index offline"); });
    assertEquals("# disk full", Files.readString(saved));
    assertEquals("INDEX_ERROR", repository.status("disk.md"));
}
```

- [ ] **Step 2: Run the focused test and verify the indexer failure**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeIndexServiceTest test`

Expected: FAIL because index rebuild and status updates do not exist.

- [ ] **Step 3: Implement deterministic index and health scan**

Index title, summary, Markdown text, tags, service, error code, and confirmed OCR. Compute SHA-256 for each content file. Mark missing files as `MISSING_FILE`, orphan files as report-only health findings, and successful rebuilds as `READY`. Never index `DRAFT` or `REJECTED` candidates.

- [ ] **Step 4: Add import/export with per-file results**

Accept Markdown, UTF-8 TXT, and JSON metadata. Reject unsupported extensions, traversal paths, and quota violations per file while continuing other files. Export a zip or directory snapshot under the current user's `exports` folder with a manifest and source metadata.

- [ ] **Step 5: Run index, import, export, and health tests**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeIndexServiceTest test`

Expected: PASS for ready, index error, missing file, orphan file reporting, unsupported import, and export manifest.

- [ ] **Step 6: Commit indexing and file operations**

```bash
git add backend/src/main/java/com/smartops/knowledge backend/src/main/java/com/smartops/controller/PersonalKnowledgeFileController.java backend/src/main/java/com/smartops/service/PersonalKnowledgeService.java backend/src/test/java/com/smartops/knowledge/PersonalKnowledgeIndexServiceTest.java
git commit -m "feat: index and export personal knowledge files"
```

### Task 4: Knowledge center dual-zone UI

**Files:**
- Modify: `frontend/src/views/knowledge/KnowledgeView.vue`
- Modify: `frontend/src/views/knowledge/PersonalKnowledgeView.vue`
- Create: `frontend/src/components/knowledge/KnowledgeZoneTabs.vue`
- Create: `frontend/src/components/knowledge/PersonalKnowledgeWorkspace.vue`
- Create: `frontend/src/components/knowledge/CreateKnowledgeLibraryDialog.vue`
- Create: `frontend/src/api/personalKnowledge.js`
- Create: `frontend/test/knowledge-workspace.test.mjs`

**Interfaces:**
- Consumes: built-in catalog from `knowledgeCatalog.js` and personal endpoints from Task 2/3.
- Produces: route/query state for `system` and `personal`, three-column personal workspace, create-library dialog, source badges, empty/error/loading states.

- [ ] **Step 1: Write failing component-state tests**

```js
test('system zone is read-only and personal zone exposes create action', () => {
  const system = renderKnowledgeZone('system')
  assert.equal(system.actions.includes('create-library'), false)
  const personal = renderKnowledgeZone('personal')
  assert.equal(personal.actions.includes('create-library'), true)
})
```

- [ ] **Step 2: Run the frontend test and verify missing zone/workspace behavior**

Run: `node --test frontend/test/knowledge-workspace.test.mjs`

Expected: FAIL because the zone components and state model do not exist.

- [ ] **Step 3: Implement zone tabs and route state**

Use `?zone=system|personal` as the stable route state. Preserve existing system catalog search and tree navigation under `system`. Make `personal` the default zone for authenticated users and render only user-scoped API data.

- [ ] **Step 4: Implement the personal three-column workspace**

Add library tree, entry list, search/filter controls, Markdown detail/editor, create-library dialog, archive/restore actions, source badges, verification state, storage/index health, and explicit loading/error/empty states. Keep compact controls icon-plus-label where the action is unfamiliar and avoid nesting page cards.

- [ ] **Step 5: Run frontend tests and build**

Run: `node --test frontend/test/knowledge-workspace.test.mjs frontend/test/knowledge-foundation.test.mjs`

Run: `npm run build` from `frontend`.

Expected: PASS and a production build with system read-only actions hidden.

- [ ] **Step 6: Commit the dual-zone UI**

```bash
git add frontend/src/views/knowledge frontend/src/components/knowledge frontend/src/api/personalKnowledge.js frontend/test/knowledge-workspace.test.mjs
git commit -m "feat: add dual knowledge workspace UI"
```

### Task 5: Agent candidate handoff to personal knowledge

**Files:**
- Modify: `backend/src/main/java/com/smartops/service/VisionHandoffService.java`
- Modify: `backend/src/main/java/com/smartops/service/PersonalKnowledgeService.java`
- Modify: `frontend/src/components/ai/VisionEventCard.vue`
- Modify: `frontend/src/views/knowledge/PersonalKnowledgeView.vue`
- Create: `backend/src/test/java/com/smartops/service/PersonalKnowledgeCandidateHandoffTest.java`
- Create: `frontend/test/knowledge-candidate-handoff.test.mjs`

**Interfaces:**
- Consumes: confirmed VisionEvent and operation/fault evidence.
- Produces: `DRAFT -> CONFIRMED -> PUBLISHED` candidate flow with source references and no automatic execution.

- [ ] **Step 1: Write failing handoff tests**

```java
@Test
void unconfirmedVisionEventCannotPublishToPersonalLibrary() {
    assertThrows(BusinessException.class, () -> handoff.publishCandidate(userId, eventId, libraryId));
}
```

- [ ] **Step 2: Run handoff tests and verify the missing publication guard**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeCandidateHandoffTest test`

Expected: FAIL until candidate status and confirmation checks are enforced.

- [ ] **Step 3: Implement candidate state transitions and source preservation**

Require `ocrStatus=READY`, privacy review, and `userConfirmed=true` before confirmation. Persist source references such as `vision:{eventId}` and the originating conversation/run. Write a Markdown candidate only after confirmation, then mark it `PUBLISHED` and enqueue indexing.

- [ ] **Step 4: Add candidate review UI and regression tests**

Show candidates in a separate “待确认” section. Provide preview, confirm, reject, and publish actions. Keep candidates out of normal published search until publication succeeds.

- [ ] **Step 5: Run visual, handoff, and build verification**

Run: `mvn.cmd -s backend/.mvn/smartops-settings.xml -f backend/pom.xml "-Dmaven.compiler.forceLegacyJavacApi=true" -Dtest=PersonalKnowledgeCandidateHandoffTest,VisionKnowledgeHandoffTest test`

Run: `node --test frontend/test/knowledge-candidate-handoff.test.mjs frontend/test/visual-capture.test.mjs`

Run: `npm run build` from `frontend`.

- [ ] **Step 6: Commit Agent handoff**

```bash
git add backend/src/main/java/com/smartops/service backend/src/test/java/com/smartops/service/PersonalKnowledgeCandidateHandoffTest.java frontend/src/components/ai/VisionEventCard.vue frontend/src/views/knowledge/PersonalKnowledgeView.vue frontend/test/knowledge-candidate-handoff.test.mjs
git commit -m "feat: hand off confirmed agent knowledge"
```

## Final Verification

- [ ] Run `node --test frontend/test/**/*.test.mjs`.
- [ ] Run focused backend tests with `-Dmaven.compiler.forceLegacyJavacApi=true`.
- [ ] Run `npm run build` from `frontend`.
- [ ] Run `git diff --check`.
- [ ] Manually verify two browser accounts cannot see each other's library, files, or download URLs.
- [ ] Manually verify the system zone has no create/edit/delete controls and personal candidates remain separate until confirmation.
