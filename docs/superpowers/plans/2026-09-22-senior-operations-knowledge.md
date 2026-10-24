# Senior Operations Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an offline-first Operations Knowledge Engine, a deterministic Knowledge Center, structured Smart Inquiry investigations, and an explicit-only external browser search launcher without granting any component permission to execute operations.

**Architecture:** Spring Boot owns local knowledge persistence, import, citations, investigation history, and asynchronous search contracts. Vue 3 renders the Knowledge Center and Investigation Drawer and can search the same local API directly without an AI provider. A browser-search adapter remains client-side, only receives pre-redacted user-created queries, and is reachable exclusively from an explicit click handler.

**Tech Stack:** Vue 3, Vue Router, Element Plus, Axios, Spring Boot 3.3, Java 17, MyBatis, MySQL, H2, JUnit 5, MockMvc, Node test runner, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-22-visual-sentinel-smart-inquiry-design.md`

## Global Constraints

- Local Knowledge Search is the default and must work without an AI provider or network connectivity.
- Knowledge is read-only: it must not invoke SSH, Docker, Kubernetes, database, shell, browser page, or remote-operation actions.
- `BrowserSearchLauncher.launch(query)` is available only from an explicit user gesture after sensitive-data redaction. No Agent, Spider, event, effect, watcher, or mounted component may invoke it.
- Imported and built-in material remains cited with source, section, match, quality, source type, version, visibility, and retrieval time.
- Assertions use exactly `FACT`, `OBSERVATION`, `EVIDENCE`, `INFERENCE`, `HYPOTHESIS`, `RECOMMENDATION`, `ACTION`, and `RESULT`; hypotheses are never presented as facts.
- Diagnosis Runbooks and Repair Runbooks are distinct. Commands are reference data, never executable controls.
- Command risk is one of `READ_ONLY`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, or `DESTRUCTIVE`; non-read-only entries display prerequisite, impact, rollback, and verification.
- Visibility is `PUBLIC`, `INTERNAL`, `RESTRICTED`, or `SECRET`; inaccessible documents, excerpts, and metadata must not enter results.
- The initial importer accepts Markdown, TXT, and JSON, deduplicates by source/path/hash/version, and never indexes sensitive files.
- Built-in V1 packs cover Docker, MySQL, Nginx, Ubuntu, and CentOS production diagnosis. Version-dependent conclusions carry a product/version range.
- This plan does not implement Chromium extension capture, OCR/CV, automatic repair, remote command execution, external-result scraping, semantic/vector search, or browser automation.

## Review Focus

- A 502 or a recent deployment must remain a symptom/correlation until direct evidence supports a root-cause hypothesis; Task 5 pins the labels and timeline semantics.
- Secret knowledge and query secrets must not leak through search cards, citations, exports, browser suggestions, or browser URLs; Tasks 3, 4, 6, and 10 pin each path.
- A command reference containing a destructive command must remain reference-only and display its full risk metadata; Task 2 pins this model and Task 8 pins the UI.
- A stable local knowledge search must complete without any model/Agent configuration or browser-launch side effect; Tasks 4 and 7 pin this boundary.
- Re-importing a changed or unchanged source must update or reuse one document rather than duplicate chunks/citations; Task 3 pins the lifecycle.

---

## File Structure

| Area | Responsibility |
| --- | --- |
| `backend/src/main/java/com/smartops/knowledge/model` | Closed enums and immutable records for assertions, citations, command risk, searches, fault events, questions, answers, timeline, and hypotheses. |
| `backend/src/main/java/com/smartops/entity`, `mapper`, `resources/mapper` | MyBatis persistence for knowledge documents/chunks/relationships and investigation history. |
| `backend/src/main/java/com/smartops/knowledge` | Import normalization, sensitive-data policy, document parsing, pack installation, query generation, deterministic ranking, and question selection. |
| `backend/src/main/java/com/smartops/service` | Stable `KnowledgeSearchService` and `InvestigationService` contracts used by controllers and future Agent code. |
| `backend/src/main/java/com/smartops/controller` | Read-only knowledge search/document endpoints and investigation create/update/history/export endpoints. |
| `backend/src/main/resources/knowledge-packs` | Curated, versioned built-in Markdown/JSON knowledge packs with provenance metadata. |
| `frontend/src/api` | Thin request wrappers with no UI state or browser side effects. |
| `frontend/src/features/knowledge` | Pure search-query, citation, and external-search helper functions that Node tests can import. |
| `frontend/src/features/investigation` | Pure inquiry transition, assertion presentation, and fixture-event helpers. |
| `frontend/src/components/knowledge`, `components/investigation`, `views/knowledge` | Focused Knowledge Center and Investigation Drawer UI surfaces. |

### Task 1: Shared Domain Contracts And Fault Fixture Adapter

**Files:**
- Create: `backend/src/main/java/com/smartops/knowledge/model/AssertionKind.java`
- Create: `backend/src/main/java/com/smartops/knowledge/model/CommandRisk.java`
- Create: `backend/src/main/java/com/smartops/knowledge/model/KnowledgeVisibility.java`
- Create: `backend/src/main/java/com/smartops/knowledge/model/KnowledgeSearchQuery.java`
- Create: `backend/src/main/java/com/smartops/knowledge/model/KnowledgeCitation.java`
- Create: `backend/src/main/java/com/smartops/investigation/model/FaultEvent.java`
- Create: `backend/src/main/java/com/smartops/investigation/model/InvestigationStatus.java`
- Create: `backend/src/main/java/com/smartops/investigation/model/InquiryQuestion.java`
- Create: `backend/src/main/java/com/smartops/investigation/model/InquiryAnswer.java`
- Create: `backend/src/main/java/com/smartops/investigation/model/Hypothesis.java`
- Create: `backend/src/main/java/com/smartops/investigation/FaultEventAdapter.java`
- Create: `backend/src/main/java/com/smartops/investigation/FixtureFaultEventAdapter.java`
- Test: `backend/src/test/java/com/smartops/investigation/FixtureFaultEventAdapterTest.java`

**Interfaces:**
- Produces `FaultEventAdapter.current()` returning a redacted `FaultEvent` and `FaultEventAdapter.accept(FaultEvent)` for a future extension bridge.
- Produces `KnowledgeSearchQuery(String text, String errorCode, String platform, String service, String version, String environment, String type, String risk, int limit)` and `KnowledgeCitation` for every later service.
- Produces closed `AssertionKind` and `CommandRisk` values so controllers cannot accept unchecked assertion or risk strings.

- [ ] **Step 1: Write a failing fixture-adapter test for immutable, redacted 502 evidence.**

```java
@Test
void exposes_a_fixture_event_without_sensitive_url_parameters() {
    FaultEvent event = adapter.current();

    assertThat(event.type()).isEqualTo("HTTP_502");
    assertThat(event.page().url()).doesNotContain("token=");
    assertThat(event.evidence()).allSatisfy(evidence ->
            assertThat(evidence.assertionKind()).isEqualTo(AssertionKind.EVIDENCE));
}
```

- [ ] **Step 2: Run the test to verify the adapter contracts are absent.**

Run: `mvn -q -Dtest=FixtureFaultEventAdapterTest test`

Expected: compilation failure naming `FaultEventAdapter` or `FaultEvent`.

- [ ] **Step 3: Add closed enums, immutable records, and a fixture adapter.**

```java
public enum AssertionKind {
    FACT, OBSERVATION, EVIDENCE, INFERENCE,
    HYPOTHESIS, RECOMMENDATION, ACTION, RESULT
}

public enum CommandRisk {
    READ_ONLY, LOW, MEDIUM, HIGH, CRITICAL, DESTRUCTIVE
}

public interface FaultEventAdapter {
    FaultEvent current();
    void accept(FaultEvent event);
}
```

Keep `FaultEvent` as records of event/page/region/evidence values. Use `OperationRedactor` or a new `KnowledgeRedactor` in later tasks before an event crosses a controller boundary; fixture data must demonstrate a redacted URL now.

- [ ] **Step 4: Run the focused test and full existing backend test suite.**

Run: `mvn -q -Dtest=FixtureFaultEventAdapterTest test`

Expected: PASS.

Run: `mvn -q test`

Expected: PASS.

- [ ] **Step 5: Commit the independent contract change.**

```powershell
git add backend/src/main/java/com/smartops/knowledge backend/src/main/java/com/smartops/investigation backend/src/test/java/com/smartops/investigation
git commit -m "feat: add knowledge and investigation contracts"
```

### Task 2: Knowledge And Investigation Persistence Schema

**Files:**
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeDomain.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeBase.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeDocument.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeChunk.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeCommand.java`
- Create: `backend/src/main/java/com/smartops/entity/KnowledgeRelationship.java`
- Create: `backend/src/main/java/com/smartops/entity/InvestigationEntity.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeDomainMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeDocumentMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeChunkMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeCommandMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/KnowledgeRelationshipMapper.java`
- Create: `backend/src/main/java/com/smartops/mapper/InvestigationMapper.java`
- Create: `backend/src/main/resources/mapper/KnowledgeDomainMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeDocumentMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeChunkMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeCommandMapper.xml`
- Create: `backend/src/main/resources/mapper/KnowledgeRelationshipMapper.xml`
- Create: `backend/src/main/resources/mapper/InvestigationMapper.xml`
- Modify: `backend/src/main/resources/db/local-schema.sql`
- Modify: `backend/src/test/resources/schema.sql`
- Test: `backend/src/test/java/com/smartops/mapper/KnowledgeDocumentMapperTest.java`
- Test: `backend/src/test/java/com/smartops/mapper/KnowledgeCommandMapperTest.java`

**Interfaces:**
- Produces mapper methods `KnowledgeDocumentMapper.findBySourceAndHash`, `replaceChunks`, `findVisible`, `KnowledgeCommandMapper.findByDocumentId`, and `InvestigationMapper.findById`.
- Persists the relationships that let a runbook cite an incident, command, service dependency, version range, or anti-pattern without duplicating document text.

- [ ] **Step 1: Write failing mapper tests for visibility and full command-risk metadata.**

```java
@Test
void excludes_secret_document_metadata_from_visible_search_rows() {
    mapper.insert(document("SECRET", "private/mysql-credentials.md"));
    assertThat(mapper.findVisible("mysql", "INTERNAL")).isEmpty();
}

@Test
void persists_destructive_command_as_reference_metadata_not_an_operation() {
    commandMapper.insert(command("DROP DATABASE app", CommandRisk.DESTRUCTIVE));
    KnowledgeCommand stored = commandMapper.findByDocumentId(1L).get(0);
    assertThat(stored.getRollback()).isNotBlank();
    assertThat(stored.getExpectedOutput()).isNotBlank();
    assertThat(stored.isReadOnly()).isFalse();
}
```

- [ ] **Step 2: Run the mapper tests to verify schema and mapper resolution fail.**

Run: `mvn -q -Dtest=KnowledgeDocumentMapperTest,KnowledgeCommandMapperTest test`

Expected: compilation or mapper-resolution failure naming the new mappers.

- [ ] **Step 3: Add the normalized MySQL and H2 schema plus MyBatis mapper XML.**

Create tables `knowledge_domain`, `knowledge_base`, `knowledge_document`, `knowledge_section`, `knowledge_chunk`, `knowledge_command`, `knowledge_relationship`, `investigation`, and `investigation_entry`. Use foreign keys with metadata-only delete behavior for source files. Store dynamic evidence/answer/timeline payloads as JSON text in `investigation_entry`; retain `kind`, timestamp, and stable order in separate columns. Add indexes for visible document search, chunk lookup, source/hash/version, command document, relationship source/target, and investigation updated time.

Store these minimum `knowledge_document` fields: `title`, `type`, `category`, `service`, `environment`, `platform`, `version_range`, `visibility`, `quality`, `source_type`, `review_status`, `source`, `path`, `content_hash`, `status`, `created_at`, and `updated_at`. Store all command fields named in the spec, including `command_text`, but do not add an execution status or operation-session foreign key.

- [ ] **Step 4: Run focused mapper tests.**

Run: `mvn -q -Dtest=KnowledgeDocumentMapperTest,KnowledgeCommandMapperTest test`

Expected: PASS.

- [ ] **Step 5: Commit the persistence layer.**

```powershell
git add backend/src/main/java/com/smartops/entity backend/src/main/java/com/smartops/mapper backend/src/main/resources/mapper backend/src/main/resources/db/local-schema.sql backend/src/test/resources/schema.sql backend/src/test/java/com/smartops/mapper
git commit -m "feat: persist operations knowledge and investigations"
```

### Task 3: Offline Import, Built-In Packs, And Safe Index Lifecycle

**Files:**
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeFileClassifier.java`
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeRedactor.java`
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeDocumentParser.java`
- Create: `backend/src/main/java/com/smartops/knowledge/KnowledgeChunker.java`
- Create: `backend/src/main/java/com/smartops/knowledge/BuiltInKnowledgePackInstaller.java`
- Create: `backend/src/main/java/com/smartops/service/KnowledgeImportService.java`
- Create: `backend/src/main/java/com/smartops/service/impl/KnowledgeImportServiceImpl.java`
- Create: `backend/src/main/resources/knowledge-packs/docker/manifest.json`
- Create: `backend/src/main/resources/knowledge-packs/mysql/manifest.json`
- Create: `backend/src/main/resources/knowledge-packs/nginx/manifest.json`
- Create: `backend/src/main/resources/knowledge-packs/ubuntu/manifest.json`
- Create: `backend/src/main/resources/knowledge-packs/centos/manifest.json`
- Create: `backend/src/main/resources/knowledge-packs/*/diagnosis/*.md`
- Create: `backend/src/main/resources/knowledge-packs/*/anti-patterns/*.md`
- Test: `backend/src/test/java/com/smartops/knowledge/KnowledgeDocumentParserTest.java`
- Test: `backend/src/test/java/com/smartops/service/KnowledgeImportServiceTest.java`
- Test: `backend/src/test/java/com/smartops/knowledge/BuiltInKnowledgePackInstallerTest.java`

**Interfaces:**
- Produces `KnowledgeImportService.importPath(Path source, KnowledgeVisibility visibility)` and `installBuiltInPacks()` returning counts for created, updated, unchanged, archived, skipped-sensitive, and failed files.
- Consumes the Task 2 mappers and produces source-preserving documents, sections, chunks, commands, and relationships.

- [ ] **Step 1: Write failing tests for structured runbook parsing, sensitive-file exclusion, and idempotent import.**

```java
@Test
void parses_diagnosis_runbook_into_sections_commands_and_expected_results() {
    ParsedKnowledgeDocument document = parser.parse(markdown("502 Runbook", """
        ## Diagnosis
        Check upstream health.
        ## Commands
        `curl -fsS http://upstream:8080/health`
        ## Expected Result
        HTTP 200
        """));

    assertThat(document.sections()).extracting(ParsedSection::heading)
            .contains("Diagnosis", "Commands", "Expected Result");
}

@Test
void reimporting_an_unchanged_source_keeps_one_document_and_its_chunks() {
    service.importPath(source, KnowledgeVisibility.INTERNAL);
    service.importPath(source, KnowledgeVisibility.INTERNAL);
    assertThat(documentMapper.findBySource(source.toString())).hasSize(1);
}

@Test
void refuses_to_index_dotenv_and_private_key_content() {
    assertThat(classifier.classify(Path.of("D:/ops/.env")).status()).isEqualTo("SENSITIVE");
    assertThat(classifier.classify(Path.of("D:/ops/server.key")).status()).isEqualTo("SENSITIVE");
}
```

- [ ] **Step 2: Run the focused import tests to verify they fail.**

Run: `mvn -q -Dtest=KnowledgeDocumentParserTest,KnowledgeImportServiceTest,BuiltInKnowledgePackInstallerTest test`

Expected: compilation failure naming the importer/parser classes.

- [ ] **Step 3: Implement parsing, hashing, redaction, and lifecycle rules.**

Accept only `.md`, `.txt`, and `.json`; decode as UTF-8 with BOM handling. Skip sensitive names (`.env`, `*.pem`, `*.key`, and names containing `credential`, `secret`, `password`, or `token`) without retaining content or previews. Split documents by parsed heading then bounded paragraphs, retaining document/section/position/tags/platform/version metadata. SHA-256 hash content; a same source/path/hash/version is unchanged, a changed hash replaces sections/chunks atomically, and a missing re-import source is archived instead of duplicated or deleted from disk.

Parse Markdown front matter and JSON metadata for `type`, `visibility`, `quality`, `sourceType`, `platform`, `versionRange`, `service`, `tags`, and document relationships. Require `sourceType: BUILT_IN_REFERENCE` in the five bundled manifests, and set `reviewStatus: REVIEWED`. Reject a manifest that claims `OFFICIAL_REFERENCE` without an external source URL.

- [ ] **Step 4: Add the first curated production knowledge fixtures.**

Create one diagnosis Runbook and one anti-pattern document per built-in pack. The Docker runbook distinguishes `container up` from `application ready`; MySQL distinguishes connection exhaustion from database unavailability; Nginx traces 502 through upstream/network/DNS/application branches; Ubuntu covers systemd, filesystem, process, port, and DNS evidence; CentOS includes ownership, ACL, and SELinux context before permission changes. Include one version-range field and one cited source in each manifest. No document may make a command executable.

- [ ] **Step 5: Run importer and built-in-pack tests.**

Run: `mvn -q -Dtest=KnowledgeDocumentParserTest,KnowledgeImportServiceTest,BuiltInKnowledgePackInstallerTest test`

Expected: PASS.

- [ ] **Step 6: Commit the offline knowledge pipeline.**

```powershell
git add backend/src/main/java/com/smartops/knowledge backend/src/main/java/com/smartops/service backend/src/main/resources/knowledge-packs backend/src/test/java/com/smartops/knowledge backend/src/test/java/com/smartops/service
git commit -m "feat: import and seed operations knowledge packs"
```

### Task 4: Deterministic Local Knowledge Search And Citations

**Files:**
- Create: `backend/src/main/java/com/smartops/service/KnowledgeSearchService.java`
- Create: `backend/src/main/java/com/smartops/service/impl/LocalKnowledgeSearchService.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/KnowledgeSearchResponse.java`
- Create: `backend/src/main/java/com/smartops/dto/knowledge/KnowledgeDocumentResponse.java`
- Create: `backend/src/main/java/com/smartops/controller/KnowledgeController.java`
- Modify: `backend/src/main/resources/mapper/KnowledgeChunkMapper.xml`
- Modify: `backend/src/main/java/com/smartops/mapper/KnowledgeChunkMapper.java`
- Test: `backend/src/test/java/com/smartops/service/LocalKnowledgeSearchServiceTest.java`
- Test: `backend/src/test/java/com/smartops/controller/KnowledgeControllerTest.java`

**Interfaces:**
- Produces `CompletableFuture<List<KnowledgeSearchResponse>> search(KnowledgeSearchQuery query, KnowledgeVisibility callerVisibility)`.
- Produces `GET /api/knowledge/search`, `GET /api/knowledge/documents/{id}`, and `POST /api/knowledge/documents/{id}/citations` endpoints. The citation endpoint adds an existing visible source to an investigation only; it never invokes an operation.

- [ ] **Step 1: Write failing ranking and controller tests.**

```java
@Test
void ranks_error_code_and_service_match_above_plain_token_match() {
    List<KnowledgeSearchResponse> results = service.search(
            new KnowledgeSearchQuery("502", "502", "Linux", "nginx", null, "prod", null, null, 10),
            KnowledgeVisibility.INTERNAL).join();

    assertThat(results.get(0).title()).isEqualTo("502 Bad Gateway Diagnosis Runbook");
    assertThat(results.get(0).citation().section()).isEqualTo("Diagnosis");
    assertThat(results.get(0).citation().retrievedAt()).isNotNull();
}

@Test
void search_never_returns_secret_document_title_or_excerpt() throws Exception {
    mockMvc.perform(get("/api/knowledge/search").param("q", "mysql"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data[*].visibility").value(not(hasItem("SECRET"))));
}
```

- [ ] **Step 2: Run the tests to verify search and endpoints are absent.**

Run: `mvn -q -Dtest=LocalKnowledgeSearchServiceTest,KnowledgeControllerTest test`

Expected: compilation or 404 failure naming the service/controller.

- [ ] **Step 3: Implement local ranking and citations.**

Use MyBatis queries to match exact error codes, normalized keywords/tokens, tags, category, service, environment, platform, version range, type, risk, and relationships. Normalize input by trimming, collapsing whitespace, lowercasing ASCII keys, and rejecting a blank query. Deterministically score exact error code and service above tag and token matches; return an explanation list such as `ERROR_CODE`, `SERVICE`, `TAG`, or `TOKEN`. Enforce visibility before ranking so `SECRET` content, metadata, and score cannot escape. Build every response from a `KnowledgeCitation(documentId, title, source, section, matchedText, score, retrievedAt)`.

- [ ] **Step 4: Add non-blocking service execution and tests for no-model operation.**

Use a bounded Spring `TaskExecutor` for search. Configure no AI, model, vector, or network dependency. Add a test that constructs `LocalKnowledgeSearchService` with only mappers and verifies a completed future without `ModelProviderClient` interaction.

- [ ] **Step 5: Run focused and full backend tests.**

Run: `mvn -q -Dtest=LocalKnowledgeSearchServiceTest,KnowledgeControllerTest test`

Expected: PASS.

Run: `mvn -q test`

Expected: PASS.

- [ ] **Step 6: Commit the local search API.**

```powershell
git add backend/src/main/java/com/smartops/service backend/src/main/java/com/smartops/dto/knowledge backend/src/main/java/com/smartops/controller/KnowledgeController.java backend/src/main/java/com/smartops/mapper/KnowledgeChunkMapper.java backend/src/main/resources/mapper/KnowledgeChunkMapper.xml backend/src/test/java/com/smartops/service backend/src/test/java/com/smartops/controller
git commit -m "feat: search local operations knowledge"
```

### Task 5: Smart Inquiry State Machine, Timeline, And Hypothesis Ranking

**Files:**
- Create: `backend/src/main/java/com/smartops/investigation/InvestigationStateMachine.java`
- Create: `backend/src/main/java/com/smartops/investigation/InvestigationQuestionSelector.java`
- Create: `backend/src/main/java/com/smartops/investigation/InvestigationQueryFactory.java`
- Create: `backend/src/main/java/com/smartops/service/InvestigationService.java`
- Create: `backend/src/main/java/com/smartops/service/impl/InvestigationServiceImpl.java`
- Create: `backend/src/main/java/com/smartops/dto/investigation/CreateInvestigationRequest.java`
- Create: `backend/src/main/java/com/smartops/dto/investigation/AnswerInquiryRequest.java`
- Create: `backend/src/main/java/com/smartops/dto/investigation/InvestigationResponse.java`
- Create: `backend/src/main/java/com/smartops/controller/InvestigationController.java`
- Test: `backend/src/test/java/com/smartops/investigation/InvestigationStateMachineTest.java`
- Test: `backend/src/test/java/com/smartops/investigation/InvestigationQuestionSelectorTest.java`
- Test: `backend/src/test/java/com/smartops/service/InvestigationServiceTest.java`
- Test: `backend/src/test/java/com/smartops/controller/InvestigationControllerTest.java`

**Interfaces:**
- Produces `create(FaultEvent)`, `answer(String investigationId, AnswerInquiryRequest)`, `get(String id)`, `history(int limit)`, and `exportMarkdown(String id)`.
- Consumes `FaultEventAdapter` and `KnowledgeSearchService`; produces a next `InquiryQuestion` plus cited `KnowledgeSearchResponse` values, never an operation or browser-launch request.

- [ ] **Step 1: Write failing tests for state transitions, causation labeling, and next-question ordering.**

```java
@Test
void starts_with_blast_radius_before_a_low_value_free_text_question() {
    InquiryQuestion question = selector.next(contextWith502AndNoScope());
    assertThat(question.id()).isEqualTo("blast-radius");
    assertThat(question.priority()).isEqualTo("CRITICAL");
}

@Test
void records_nearby_deployment_as_correlation_not_root_cause() {
    InvestigationResponse response = service.answer(id, answer("recent-change", "DEPLOYED_2_MINUTES_BEFORE"));
    assertThat(response.timeline()).anySatisfy(entry ->
            assertThat(entry.assertionKind()).isEqualTo(AssertionKind.OBSERVATION));
    assertThat(response.hypotheses()).allSatisfy(hypothesis ->
            assertThat(hypothesis.assertionKind()).isEqualTo(AssertionKind.HYPOTHESIS));
}
```

- [ ] **Step 2: Run focused tests to verify the state machine is missing.**

Run: `mvn -q -Dtest=InvestigationStateMachineTest,InvestigationQuestionSelectorTest,InvestigationServiceTest,InvestigationControllerTest test`

Expected: compilation or 404 failure naming the investigation classes.

- [ ] **Step 3: Implement the read-only investigation flow.**

Implement states `IDLE`, `STARTING`, `COLLECTING`, `WAITING_USER`, `ANALYZING`, `SEARCHING_KNOWLEDGE`, `REFINING`, `READY`, `RESOLVED`, `CANCELLED`, and `ERROR`. Persist every question, original answer, normalized answer, answer confidence, evidence, hypothesis, recommendation, and timeline entry with its assertion kind. Start each incident by asking blast radius and time/persistence, then recent change correlation, then the read-only check that has greatest information gain among active hypotheses. Give each question a rationale and one cited source when a knowledge result informed it.

`ACTION` stores only a proposed/user-reported check. Prohibit action payloads with `execute`, `command`, `sessionId`, `host`, or `operationId` fields in the DTO validation layer. Generate `KnowledgeSearchQuery` from fault text, page/service/platform, environment, answers, and highest-ranked hypotheses. Do not invoke `ModelProviderClient`, operations services, or a browser launcher.

- [ ] **Step 4: Add history and export endpoints with redaction.**

Expose `POST /api/investigations`, `POST /api/investigations/{id}/answers`, `GET /api/investigations/{id}`, `GET /api/investigations`, and `GET /api/investigations/{id}/export?format=json|markdown`. Use `KnowledgeRedactor` before persistence and export to remove credentials/tokens/unredacted sensitive page content. Return `400` for unknown export format and `404` for unknown investigation id.

- [ ] **Step 5: Run the complete investigation test suite.**

Run: `mvn -q -Dtest=InvestigationStateMachineTest,InvestigationQuestionSelectorTest,InvestigationServiceTest,InvestigationControllerTest test`

Expected: PASS.

- [ ] **Step 6: Commit Smart Inquiry backend.**

```powershell
git add backend/src/main/java/com/smartops/investigation backend/src/main/java/com/smartops/service/InvestigationService.java backend/src/main/java/com/smartops/service/impl/InvestigationServiceImpl.java backend/src/main/java/com/smartops/dto/investigation backend/src/main/java/com/smartops/controller/InvestigationController.java backend/src/test/java/com/smartops/investigation backend/src/test/java/com/smartops/service/InvestigationServiceTest.java backend/src/test/java/com/smartops/controller/InvestigationControllerTest.java
git commit -m "feat: add structured smart investigations"
```

### Task 6: Frontend API Contracts And Pure Safety Helpers

**Files:**
- Create: `frontend/src/api/knowledge.js`
- Create: `frontend/src/api/investigations.js`
- Create: `frontend/src/features/knowledge/searchQuery.js`
- Create: `frontend/src/features/knowledge/browserSearchLauncher.js`
- Create: `frontend/src/features/investigation/investigationPresentation.js`
- Test: `frontend/test/knowledge-api.test.mjs`
- Test: `frontend/test/browser-search-launcher.test.mjs`
- Test: `frontend/test/investigation-presentation.test.mjs`

**Interfaces:**
- Produces `searchKnowledge(filters)`, `getKnowledgeDocument(id)`, `addCitation(investigationId, documentId)`, `createInvestigation(faultEvent)`, `answerInvestigation(id, answer)`, `getInvestigation(id)`, `listInvestigations()`, and `exportInvestigation(id, format)`.
- Produces `createBrowserSearchLauncher({ openWindow, baseUrl })` whose `suggest(rawText)` returns redacted text and whose `launch(query)` only opens when a caller invokes it directly.

- [ ] **Step 1: Write failing frontend API and launcher tests.**

```js
test('local knowledge search forwards deterministic filters without an AI request', async () => {
  await searchKnowledge({ query: '502 nginx', errorCode: '502', service: 'nginx' })
  assert.equal(lastRequest.url, '/api/knowledge/search')
  assert.equal(lastRequest.params.errorCode, '502')
})

test('search suggestion redacts secrets and never opens a window', () => {
  const opened = []
  const launcher = createBrowserSearchLauncher({ openWindow: url => opened.push(url), baseUrl: 'https://www.baidu.com/s' })
  assert.equal(launcher.suggest('mysql password=abc123 timeout'), 'mysql [REDACTED] timeout')
  assert.deepEqual(opened, [])
})

test('launch opens the encoded external query only after direct invocation', () => {
  const opened = []
  const launcher = createBrowserSearchLauncher({ openWindow: url => opened.push(url), baseUrl: 'https://www.baidu.com/s' })
  launcher.launch('mysql connection timeout')
  assert.equal(opened[0], 'https://www.baidu.com/s?wd=mysql%20connection%20timeout')
})
```

- [ ] **Step 2: Run the tests to verify modules are absent.**

Run: `npm test -- test/knowledge-api.test.mjs test/browser-search-launcher.test.mjs test/investigation-presentation.test.mjs`

Expected: module-resolution failure.

- [ ] **Step 3: Implement API clients and pure presentation helpers.**

Use the existing `request` client. Preserve API response envelopes and leave browser opening out of all API modules. In `browserSearchLauncher.js`, use an injected `openWindow` function and URL/`URLSearchParams` construction; do not create timers, watchers, lifecycle hooks, network calls, or Agent imports. Redact key/value secrets, bearer tokens, private URLs, and internal hostnames before `suggest` and again before `launch`. `launch` returns `false` for blank/redacted-only input and otherwise returns `true` only after `openWindow(url, '_blank', 'noopener,noreferrer')` is called.

`investigationPresentation.js` maps assertion kinds to visual labels and explicitly labels correlation as `RELATED CHANGE`, not `ROOT CAUSE`.

- [ ] **Step 4: Run focused frontend tests.**

Run: `npm test -- test/knowledge-api.test.mjs test/browser-search-launcher.test.mjs test/investigation-presentation.test.mjs`

Expected: PASS.

- [ ] **Step 5: Commit API and safety primitives.**

```powershell
git add frontend/src/api frontend/src/features frontend/test/knowledge-api.test.mjs frontend/test/browser-search-launcher.test.mjs frontend/test/investigation-presentation.test.mjs
git commit -m "feat: add local knowledge and browser search contracts"
```

### Task 7: Knowledge Center Navigation, Search, And Source Detail

**Files:**
- Create: `frontend/src/components/knowledge/KnowledgeSearchForm.vue`
- Create: `frontend/src/components/knowledge/KnowledgeSearchResults.vue`
- Create: `frontend/src/components/knowledge/KnowledgeDocumentDetail.vue`
- Create: `frontend/src/views/knowledge/KnowledgeDocumentView.vue`
- Modify: `frontend/src/views/knowledge/KnowledgeView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Test: `frontend/test/knowledge-search-results.test.mjs`
- Test: `frontend/test/knowledge-routing.test.mjs`

**Interfaces:**
- Consumes Task 6 API functions and renders document citations from Task 4 unchanged.
- Produces routes `/knowledge`, `/knowledge/documents/:id`, and query-backed `/knowledge?q=&errorCode=&service=&platform=&version=&environment=&type=&risk=`.

- [ ] **Step 1: Write failing tests for filters and citation rendering.**

```js
test('search result renders source, section, score, quality, and match reason', () => {
  const view = toSearchResultView({
    title: '502 Bad Gateway Diagnosis Runbook', quality: 'REVIEWED',
    matchReasons: ['ERROR_CODE', 'SERVICE'],
    citation: { source: 'built-in/nginx', section: 'Diagnosis', score: 0.96 }
  })
  assert.equal(view.sourceLabel, 'built-in/nginx / Diagnosis')
  assert.equal(view.matchLabel, 'ERROR CODE + SERVICE')
})

test('knowledge routes preserve selected search filters in the URL', () => {
  assert.equal(toKnowledgeSearchPath({ errorCode: '502', service: 'nginx' }), '/knowledge?errorCode=502&service=nginx')
})
```

- [ ] **Step 2: Run the tests to verify the render helpers/routes are missing.**

Run: `npm test -- test/knowledge-search-results.test.mjs test/knowledge-routing.test.mjs`

Expected: import failure naming the new helper modules.

- [ ] **Step 3: Implement the Knowledge Center.**

Replace the placeholder-only section in `KnowledgeView.vue` with a work-focused local search surface: text query, error code, platform, service, version, environment, document type, category, visibility, and risk controls. Use compact filter controls, a table/list of result rows, and a source-detail panel rather than nested cards. Results show title, content type, service/platform/version, source/section, score, quality, access level, match reasons, and safe excerpt. Add actions to open the document or add its citation to the active investigation; do not add an execute-command action.

Update `MainLayout.vue` only to keep `Knowledge` navigation and route context correct for the new detail route. Keep the existing visual ecosystem and avoid altering Spider behavior in this task.

- [ ] **Step 4: Implement source detail and navigation.**

`KnowledgeDocumentView.vue` loads one document by id, renders its metadata and sections, and excludes `SECRET` content on authorization failure. Its command references display risk badge, read-only status, purpose, expected/abnormal result, prerequisites, impact, rollback, and verification as text. The primary action is navigation back to local results; external search has no automatic trigger.

- [ ] **Step 5: Run frontend unit tests and build.**

Run: `npm test -- test/knowledge-search-results.test.mjs test/knowledge-routing.test.mjs`

Expected: PASS.

Run: `npm run build`

Expected: PASS.

- [ ] **Step 6: Commit the Knowledge Center.**

```powershell
git add frontend/src/components/knowledge frontend/src/views/knowledge frontend/src/router/index.js frontend/src/layouts/MainLayout.vue frontend/test/knowledge-search-results.test.mjs frontend/test/knowledge-routing.test.mjs
git commit -m "feat: add operations knowledge center"
```

### Task 8: Investigation Drawer, History, And Evidence-Backed Recommendations

**Files:**
- Create: `frontend/src/components/investigation/InvestigationDrawer.vue`
- Create: `frontend/src/components/investigation/InvestigationEvidenceList.vue`
- Create: `frontend/src/components/investigation/InquiryQuestionForm.vue`
- Create: `frontend/src/components/investigation/HypothesisList.vue`
- Create: `frontend/src/components/investigation/InvestigationHistoryList.vue`
- Create: `frontend/src/views/investigation/InvestigationView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/components/common/OpsSpiderPet.vue`
- Test: `frontend/test/inquiry-question-form.test.mjs`
- Test: `frontend/test/investigation-drawer.test.mjs`
- Test: `frontend/test/ops-spider-investigation-entry.test.mjs`

**Interfaces:**
- Consumes Task 1 fixture event adapter data through an injected app adapter and Task 6 investigation API client.
- Produces `/investigations/:id` for durable history and an on-demand drawer opened by a Spider alert click; it does not convert the Spider into a chat application.

- [ ] **Step 1: Write failing tests for structured answers and assertion-safe presentation.**

```js
test('single choice answer retains original and normalized values', () => {
  const answer = buildInquiryAnswer(question('persistence', 'SINGLE_CHOICE'), 'CONTINUOUS')
  assert.deepEqual(answer, { questionId: 'persistence', originalValue: 'CONTINUOUS', normalizedValue: 'CONTINUOUS' })
})

test('hypothesis and recommendation remain visibly distinct from observed evidence', () => {
  assert.equal(assertionLabel('HYPOTHESIS'), 'HYPOTHESIS')
  assert.equal(assertionLabel('RECOMMENDATION'), 'RECOMMENDATION')
  assert.notEqual(assertionTone('HYPOTHESIS'), assertionTone('EVIDENCE'))
})
```

- [ ] **Step 2: Run the drawer tests to verify the components/helpers are absent.**

Run: `npm test -- test/inquiry-question-form.test.mjs test/investigation-drawer.test.mjs test/ops-spider-investigation-entry.test.mjs`

Expected: module-resolution failure.

- [ ] **Step 3: Implement the drawer and one-question interaction.**

Render FaultEvent summary, confidence, first/last seen, evidence, one prioritized question, its rationale, answer controls, cited local knowledge, hypotheses, and read-only recommended checks. Support choice, multi-choice, text, number, boolean, URL, time range, service, and environment answers. Preserve the free-text original response and show a normalized value only when returned by the API. Do not render a generic model chat transcript, a command terminal, or any execution control.

Clicking a Spider alert may call `createInvestigation(faultEvent)` and open the drawer; it must not call `BrowserSearchLauncher`, an Agent API, or any operations API. Closing the drawer returns control to the existing Spider state without interrupting page interaction.

- [ ] **Step 4: Implement history and export affordances.**

`InvestigationView.vue` lists timestamp, fault type, page, status, and cited knowledge for prior investigations. Add export JSON and Markdown links to the existing export endpoint. Render empty/error/loading states, including `INSUFFICIENT_EVIDENCE` and `UNSAFE_TO_CONTINUE`, with no suggested remote action.

- [ ] **Step 5: Run tests and a responsive browser check.**

Run: `npm test -- test/inquiry-question-form.test.mjs test/investigation-drawer.test.mjs test/ops-spider-investigation-entry.test.mjs`

Expected: PASS.

Run: `npm run build`

Expected: PASS.

Run: `npm run visual-check`

Expected: PASS after extending the Playwright script to verify that the desktop and mobile drawer have no horizontal overflow and that the Spider alert opens a drawer only after a click.

- [ ] **Step 6: Commit the investigation UI.**

```powershell
git add frontend/src/components/investigation frontend/src/views/investigation frontend/src/components/common/OpsSpiderPet.vue frontend/src/router/index.js frontend/test/inquiry-question-form.test.mjs frontend/test/investigation-drawer.test.mjs frontend/test/ops-spider-investigation-entry.test.mjs frontend/test/visual-check.mjs
git commit -m "feat: investigate spider fault events"
```

### Task 9: Explicit Browser Search Command In Knowledge And Investigation UI

**Files:**
- Create: `frontend/src/components/knowledge/ExternalSearchAction.vue`
- Modify: `frontend/src/components/knowledge/KnowledgeSearchForm.vue`
- Modify: `frontend/src/components/investigation/InvestigationDrawer.vue`
- Modify: `frontend/src/features/knowledge/browserSearchLauncher.js`
- Test: `frontend/test/external-search-action.test.mjs`
- Test: `frontend/test/no-automatic-browser-search.test.mjs`

**Interfaces:**
- Consumes `createBrowserSearchLauncher` from Task 6 and receives explicit `query` plus injected launcher as props.
- Produces a button click event that calls `launcher.launch(query)` exactly once; it does not accept FaultEvent, Agent, watcher, timer, or lifecycle callback props.

- [ ] **Step 1: Write failing tests for the user-gesture boundary.**

```js
test('mounting an external search action never launches a browser', () => {
  const calls = []
  renderExternalSearchAction({ query: 'mysql timeout', launcher: { launch: query => calls.push(query) } })
  assert.deepEqual(calls, [])
})

test('only the button click launches the redacted query once', () => {
  const calls = []
  const view = renderExternalSearchAction({ query: 'nginx token=secret 502', launcher: { launch: query => calls.push(query) } })
  view.click()
  assert.deepEqual(calls, ['nginx [REDACTED] 502'])
})

test('spider state module has no browser search import or launch reference', async () => {
  const source = await readFile('src/components/common/opsSpiderState.js', 'utf8')
  assert.doesNotMatch(source, /BrowserSearchLauncher|browserSearchLauncher|\.launch\(/)
})
```

- [ ] **Step 2: Run the tests to verify the action boundary is missing.**

Run: `npm test -- test/external-search-action.test.mjs test/no-automatic-browser-search.test.mjs`

Expected: module-resolution or assertion failure.

- [ ] **Step 3: Implement the button-only external search action.**

Use a clear icon-plus-label command with a tooltip identifying that it opens an external search in the local browser. It appears after local results and in the investigation knowledge section, populated with a local suggestion. The visible query is redacted before display. Bind `@click` directly to a component method that calls the launcher once; never invoke from `watch`, `watchEffect`, `onMounted`, route changes, result changes, state-machine transitions, or automated retries.

- [ ] **Step 4: Run the explicit-only tests and build.**

Run: `npm test -- test/external-search-action.test.mjs test/no-automatic-browser-search.test.mjs`

Expected: PASS.

Run: `npm run build`

Expected: PASS.

- [ ] **Step 5: Commit the browser-search boundary.**

```powershell
git add frontend/src/components/knowledge/ExternalSearchAction.vue frontend/src/components/knowledge/KnowledgeSearchForm.vue frontend/src/components/investigation/InvestigationDrawer.vue frontend/src/features/knowledge/browserSearchLauncher.js frontend/test/external-search-action.test.mjs frontend/test/no-automatic-browser-search.test.mjs
git commit -m "feat: add explicit external knowledge search"
```

### Task 10: End-To-End Verification, Documentation, And Safety Audit

**Files:**
- Create: `backend/src/test/java/com/smartops/integration/KnowledgeInvestigationIntegrationTest.java`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-22-visual-sentinel-smart-inquiry-design.md` only if implementation reveals an objective contract mismatch
- Test: `frontend/test/knowledge-investigation-e2e.test.mjs`

**Interfaces:**
- Consumes the finished local import/search/investigation API and frontend routes.
- Produces documented local configuration, pack provenance, search scope, visibility policy, and explicit browser-search policy.

- [ ] **Step 1: Write the failing backend integration test for the safe end-to-end path.**

```java
@SpringBootTest
@AutoConfigureMockMvc
class KnowledgeInvestigationIntegrationTest {
    @Test
    void imports_searches_investigates_and_exports_without_an_operation_or_browser_call() throws Exception {
        // Import a temporary Nginx 502 diagnosis file, search it, create an investigation,
        // answer blast radius, add a citation, export Markdown, and assert command tables,
        // operation audit tables, and model interactions remain unchanged.
    }
}
```

- [ ] **Step 2: Run the integration test before final wiring.**

Run: `mvn -q -Dtest=KnowledgeInvestigationIntegrationTest test`

Expected: failing API/persistence assertion until all features are connected.

- [ ] **Step 3: Add final integration assertions and documentation.**

The test must assert: a `SECRET` document never appears in search/export; a 502 evidence event creates a `HYPOTHESIS` rather than a confirmed root cause; a correlated deployment is timeline evidence; exported Markdown has citations and no secret; no `operation_command` or `operation_audit_event` record is created. The frontend E2E test must search the local Knowledge Center, open cited source detail, start an investigation from a simulated Spider alert, answer one question, and verify the external-search browser opener remains untouched until its button is clicked.

Document the import formats, sensitive-file exclusion, source-preserving lifecycle, built-in pack provenance, supported search filters, visibility rules, assertion vocabulary, read-only command policy, and the hard external-search user-click boundary. State plainly that no command, browser-page action, SSH, Kubernetes, Docker, database, or automated remediation is available in this release.

- [ ] **Step 4: Run all required verification.**

Run: `mvn -q test`

Expected: PASS.

Run: `npm run lint`

Expected: PASS.

Run: `npm run typecheck`

Expected: PASS.

Run: `npm test`

Expected: PASS.

Run: `npm run build`

Expected: PASS.

Run: `npm run visual-check`

Expected: PASS.

- [ ] **Step 5: Perform a local smoke check with no external search click.**

Run the backend and frontend locally, import a non-sensitive Markdown runbook, search `502 nginx`, create and answer an investigation, inspect a citation, and export the result. Verify no new browser tab/window opens until clicking the external-search action. Verify no network operation/command is created while using all local flows.

- [ ] **Step 6: Commit verification and documentation.**

```powershell
git add README.md backend/src/test/java/com/smartops/integration frontend/test/knowledge-investigation-e2e.test.mjs docs/superpowers/specs/2026-09-22-visual-sentinel-smart-inquiry-design.md
git commit -m "docs: verify senior operations knowledge workflow"
```

## Plan Self-Review

- Spec coverage: Tasks 1 and 5 cover versioned fault data, assertion labels, blast radius, timelines, correlation, question priority, stop states, hypotheses, history, and exports. Tasks 2 and 3 cover structured knowledge, command/evidence/risk metadata, relationships, source quality, import lifecycle, and curated production packs. Tasks 4 and 7 cover asynchronous local/offline search, citations, filters, source detail, and visibility. Tasks 6 and 9 cover deterministic non-AI search and explicit-only browser launch. Task 10 verifies end-to-end safety and user workflow.
- Placeholder scan: no `TBD`, `TODO`, or deferred implementation text is present. The integration-test comment identifies exact setup and is followed by the concrete required assertions in Step 3.
- Type consistency: `KnowledgeSearchQuery`, `KnowledgeCitation`, `FaultEvent`, `InquiryQuestion`, `AnswerInquiryRequest`, `InvestigationResponse`, `KnowledgeSearchService`, and `BrowserSearchLauncher` retain the same names and roles across tasks.
- Review focus coverage: Task 5 tests fact/correlation/hypothesis distinction; Tasks 3, 4, 6, 9, and 10 test sensitive-content prevention; Tasks 2 and 7 test command-risk reference-only rendering; Tasks 4 and 6 test no-model local search; Task 3 tests idempotent import.
