package com.smartops.service;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.sql.Timestamp;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class KnowledgeCandidateServiceTest {
    private JdbcTemplate jdbc;
    private KnowledgeCandidateService service;

    @BeforeEach
    void setUp() {
        var dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:knowledge-candidate-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE operation_run_record (id BIGINT AUTO_INCREMENT PRIMARY KEY, trace_id VARCHAR(64) NOT NULL, user_id BIGINT NOT NULL, session_id BIGINT, runtime_id VARCHAR(128) NOT NULL, tool_id VARCHAR(128) NOT NULL, status VARCHAR(32) NOT NULL, started_at TIMESTAMP NOT NULL, ended_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE operation_run_output (id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, sequence_no INT NOT NULL, command_text CLOB NOT NULL, exit_code INT NOT NULL, stdout_text CLOB, stderr_text CLOB, truncated TINYINT(1) NOT NULL DEFAULT 0, output_bytes BIGINT NOT NULL DEFAULT 0, started_at TIMESTAMP NOT NULL, ended_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE operation_run_evidence (id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NOT NULL, evidence_type VARCHAR(64) NOT NULL, content CLOB NOT NULL, source_ref VARCHAR(255), created_at TIMESTAMP NOT NULL)");
        jdbc.execute("CREATE TABLE knowledge_candidate (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, source_type VARCHAR(32) NOT NULL, source_run_id BIGINT NULL, source_task_id BIGINT NULL, source_url VARCHAR(255), source_content_hash VARCHAR(64), source_fetched_at TIMESTAMP NULL, trace_id VARCHAR(64) NOT NULL, tool_id VARCHAR(128) NOT NULL, title VARCHAR(255) NOT NULL, summary CLOB NOT NULL, content_markdown CLOB NOT NULL, status VARCHAR(32) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, source_run_id), UNIQUE(user_id, source_task_id))");
        jdbc.execute("CREATE TABLE web_research_page (task_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, url VARCHAR(255) NOT NULL, title VARCHAR(255) NOT NULL, excerpt CLOB NOT NULL, content CLOB NOT NULL, content_hash VARCHAR(64) NOT NULL, fetched_at TIMESTAMP NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        service = new KnowledgeCandidateService(jdbc, new OperationRunQueryService(jdbc));
    }

    @Test
    void createsChineseMarkdownCandidateFromOwnedRunAndKeepsItPendingReview() {
        long runId = insertRun(1, "trace-k8s", "k8s.pods", "FAILED");
        insertOutput(runId, 1, "kubectl get pods -A", 1, "", "Unable to connect");
        insertEvidence(runId, "COMMAND_RESULT", "API Server 连接失败", "command:1");

        var candidate = service.createFromRun(1L, runId);

        assertThat(candidate.status()).isEqualTo("PENDING_REVIEW");
        assertThat(candidate.sourceRunId()).isEqualTo(runId);
        assertThat(candidate.title()).contains("k8s.pods").contains("执行失败");
        assertThat(candidate.contentMarkdown())
                .contains("# 运维知识候选")
                .contains("## 操作步骤")
                .contains("kubectl get pods -A")
                .contains("Unable to connect")
                .contains("API Server 连接失败")
                .contains("待人工审核");
    }

    @Test
    void returnsExistingCandidateWhenSameRunIsSubmittedAgain() {
        long runId = insertRun(1, "trace-repeat", "docker.ps", "SUCCESS");

        var first = service.createFromRun(1L, runId);
        var second = service.createFromRun(1L, runId);

        assertThat(second.id()).isEqualTo(first.id());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM knowledge_candidate", Integer.class)).isEqualTo(1);
    }

    @Test
    void doesNotRevealOrCreateCandidateFromAnotherUsersRun() {
        long runId = insertRun(2, "trace-private", "linux.uptime", "SUCCESS");

        assertThatThrownBy(() -> service.createFromRun(1L, runId))
                .isInstanceOf(BusinessException.class)
                .hasMessage("OPERATION_RUN_NOT_FOUND");
    }

    @Test
    void listsOnlyCurrentUsersCandidatesWithStatusFilterAndPaging() {
        long firstRun = insertRun(1, "trace-first", "docker.ps", "SUCCESS");
        long secondRun = insertRun(1, "trace-second", "k8s.pods", "FAILED");
        long privateRun = insertRun(2, "trace-private-list", "linux.uptime", "SUCCESS");
        service.createFromRun(1L, firstRun);
        service.createFromRun(1L, secondRun);
        service.createFromRun(2L, privateRun);

        var page = service.list(1L, "PENDING_REVIEW", 1, 1);

        assertThat(page.total()).isEqualTo(2);
        assertThat(page.page()).isEqualTo(1);
        assertThat(page.pageSize()).isEqualTo(1);
        assertThat(page.items()).hasSize(1);
        assertThat(page.items().get(0).traceId()).isEqualTo("trace-second");
    }

    @Test
    void returnsOwnedCandidateDetailAndHidesOtherUsersCandidate() {
        long ownedRun = insertRun(1, "trace-owned-candidate", "k8s.services", "FAILED");
        long privateRun = insertRun(2, "trace-hidden-candidate", "docker.inspect", "SUCCESS");
        var owned = service.createFromRun(1L, ownedRun);
        var hidden = service.createFromRun(2L, privateRun);

        assertThat(service.detail(1L, owned.id()).contentMarkdown()).contains("待人工审核");
        assertThatThrownBy(() -> service.detail(1L, hidden.id()))
                .isInstanceOf(BusinessException.class)
                .hasMessage("KNOWLEDGE_CANDIDATE_NOT_FOUND");
    }

    @Test
    void createsIdempotentWebCandidateWithServerSideProvenanceAndSafeFence() {
        String body = "Before\n```html\n<script>alert(1)</script>\n```\nAfter";
        insertWebPage(41L, 1L, "https://example.com/guide", "Public guide", "A public excerpt", body, "a".repeat(64));

        var candidate = service.createFromWebResearch(1L, 41L);
        var repeated = service.createFromWebResearch(1L, 41L);

        assertThat(repeated.id()).isEqualTo(candidate.id());
        assertThat(candidate.sourceRunId()).isNull();
        assertThat(candidate.sourceTaskId()).isEqualTo(41L);
        assertThat(candidate.sourceType()).isEqualTo("WEB_RESEARCH");
        assertThat(candidate.sourceUrl()).isEqualTo("https://example.com/guide");
        assertThat(candidate.sourceContentHash()).isEqualTo("a".repeat(64));
        assertThat(candidate.contentMarkdown())
                .contains("未核验资料")
                .contains("````text\n" + body + "\n````")
                .contains("人工审核清单");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM knowledge_candidate", Integer.class)).isEqualTo(1);
    }

    @Test
    void hidesAnotherUsersWebSnapshot() {
        insertWebPage(42L, 2L, "https://example.com/private", "Private", "Private", "Private", "b".repeat(64));

        assertThatThrownBy(() -> service.createFromWebResearch(1L, 42L))
                .isInstanceOf(BusinessException.class)
                .hasMessage("WEB_RESEARCH_PAGE_NOT_FOUND");
    }

    @Test
    void promotesWebCandidateWithRealUrlInsteadOfOperationTrace() {
        insertWebPage(43L, 1L, "https://example.com/source", "Web source", "Excerpt", "Evidence", "c".repeat(64));
        var candidate = service.createFromWebResearch(1L, 43L);
        var personalKnowledge = org.mockito.Mockito.mock(PersonalKnowledgeService.class);
        var reviewService = new KnowledgeCandidateService(jdbc, new OperationRunQueryService(jdbc), personalKnowledge);
        var entry = new PersonalKnowledgeService.Entry(31L, 9L, 1L, candidate.title(), candidate.summary(),
                candidate.contentMarkdown(), "WEB_RESEARCH", candidate.sourceUrl(), "UNVERIFIED", 1, Instant.EPOCH, Instant.EPOCH);
        org.mockito.Mockito.when(personalKnowledge.createEntry(1L, 9L, candidate.title(), candidate.summary(),
                candidate.contentMarkdown(), "WEB_RESEARCH", candidate.sourceUrl())).thenReturn(entry);

        var promoted = reviewService.promote(1L, candidate.id(), 9L, null, null);

        assertThat(promoted.sourceType()).isEqualTo("WEB_RESEARCH");
        assertThat(promoted.sourceRef()).isEqualTo("https://example.com/source");
        assertThat(reviewService.detail(1L, candidate.id()).status()).isEqualTo("PROMOTED");
        org.mockito.Mockito.verify(personalKnowledge).createEntry(1L, 9L, candidate.title(), candidate.summary(),
                candidate.contentMarkdown(), "WEB_RESEARCH", candidate.sourceUrl());
    }

    private void insertWebPage(long taskId, long userId, String url, String title, String excerpt, String content, String hash) {
        jdbc.update("INSERT INTO web_research_page(task_id,user_id,url,title,excerpt,content,content_hash,fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                taskId, userId, url, title, excerpt, content, hash, Timestamp.from(Instant.parse("2026-11-15T10:00:00Z")));
    }

    private long insertRun(long userId, String traceId, String toolId, String status) {
        var started = Timestamp.from(Instant.parse("2026-09-27T01:00:00Z"));
        jdbc.update("INSERT INTO operation_run_record(trace_id,user_id,session_id,runtime_id,tool_id,status,started_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",
                traceId, userId, 9L, "runtime-1", toolId, status, started, Timestamp.from(started.toInstant().plusSeconds(3)));
        return jdbc.queryForObject("SELECT id FROM operation_run_record WHERE trace_id=?", Long.class, traceId);
    }

    private void insertOutput(long runId, int sequence, String command, int exitCode, String stdout, String stderr) {
        jdbc.update("INSERT INTO operation_run_output(run_id,sequence_no,command_text,exit_code,stdout_text,stderr_text,started_at,ended_at) VALUES(?,?,?,?,?,?,?,?)",
                runId, sequence, command, exitCode, stdout, stderr,
                Timestamp.from(Instant.parse("2026-09-27T01:00:00Z")), Timestamp.from(Instant.parse("2026-09-27T01:00:01Z")));
    }

    private void insertEvidence(long runId, String type, String content, String sourceRef) {
        jdbc.update("INSERT INTO operation_run_evidence(run_id,evidence_type,content,source_ref,created_at) VALUES(?,?,?,?,?)",
                runId, type, content, sourceRef, Timestamp.from(Instant.parse("2026-09-27T01:00:02Z")));
    }
}
