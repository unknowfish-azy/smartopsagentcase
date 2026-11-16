package com.smartops.knowledge;

import com.smartops.exception.BusinessException;
import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;

class WebRenderServiceTest {

    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    @Test
    void blockedUrlIsRejectedBeforeAnyNetworkOrTask() {
        var deps = deps();
        var service = new WebRenderService(deps.research, deps.renderer, deps.sessions);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.fetchRendered(actor, "http://127.0.0.1:8080/internal", true));

        assertEquals(400, failure.getCode());
        assertEquals("WEB_RENDER_URL_BLOCKED", failure.getMessage());
        assertTrue(deps.renderer.renderCalls.isEmpty());
        assertEquals(0, deps.jdbc.queryForObject("SELECT COUNT(*) FROM web_research_task", Integer.class));
    }

    @Test
    void staticBranchDelegatesToResearchFetch() {
        var deps = deps();
        var service = new WebRenderService(deps.research, deps.renderer, deps.sessions);

        var page = service.fetchRendered(actor, "https://93.184.216.34/guide?token=secret", false);

        assertEquals("STATIC", page.renderMode());
        assertNull(page.renderNote());
        assertTrue(deps.renderer.renderCalls.isEmpty());
    }

    @Test
    void jsRenderUsesDecryptedSessionAndSavesSnapshot() {
        var deps = deps();
        deps.sessions.start(actor);
        deps.renderer.confirmedState = "[{\"name\":\"sid\",\"value\":\"s3cret\"}]";
        deps.sessions.finish(actor);

        var page = new WebRenderService(deps.research, deps.renderer, deps.sessions)
                .fetchRendered(actor, "https://93.184.216.34/spa?token=secret", true);

        assertEquals("JS", page.renderMode());
        assertTrue(page.renderNote().contains("本人登录接续"));
        assertTrue(page.content().contains("Rendered evidence"));
        assertFalse(page.content().contains("s3cret"));
        assertFalse(page.content().contains("secret"));
        assertEquals("https://93.184.216.34/spa", page.displayUrl());
        assertEquals(1, deps.renderer.renderCalls.size());
        // 传给渲染器的 state 已解密为明文 JSON（进程内转交，不落日志）
        assertTrue(deps.renderer.renderCalls.get(0).storageState().contains("\"sid\""));
        assertEquals("SUCCESS", deps.jdbc.queryForObject(
                "SELECT status FROM web_research_task WHERE id=?", String.class, page.taskId()));
        assertEquals(page.contentHash(), deps.jdbc.queryForObject(
                "SELECT content_hash FROM web_research_page WHERE task_id=?", String.class, page.taskId()));
    }

    @Test
    void jsRenderWithoutSessionStaysAnonymous() {
        var deps = deps();
        var service = new WebRenderService(deps.research, deps.renderer, deps.sessions);

        var page = service.fetchRendered(actor, "https://93.184.216.34/spa", true);

        assertEquals("JS", page.renderMode());
        assertTrue(page.renderNote().contains("匿名"));
        assertNull(deps.renderer.renderCalls.get(0).storageState());
    }

    @Test
    void expiredSessionFailsLoudlyInsteadOfSilentAnonymousFallback() {
        var deps = deps();
        deps.sessions.start(actor);
        deps.renderer.confirmedState = "[{\"name\":\"sid\",\"value\":\"s3cret\"}]";
        deps.sessions.finish(actor);
        deps.jdbc.update("UPDATE web_render_session SET expires_at=? WHERE user_id=?",
                java.sql.Timestamp.from(java.time.Instant.now().minusSeconds(60)), actor.id());

        BusinessException failure = assertThrows(BusinessException.class,
                () -> new WebRenderService(deps.research, deps.renderer, deps.sessions)
                        .fetchRendered(actor, "https://93.184.216.34/spa", true));

        assertEquals(409, failure.getCode());
        assertEquals("WEB_RENDER_SESSION_EXPIRED", failure.getMessage());
        assertTrue(deps.renderer.renderCalls.isEmpty());
    }

    @Test
    void unavailableRendererReportsInsteadOfFakingStaticContent() {
        var deps = deps();
        deps.renderer.available = false;
        var service = new WebRenderService(deps.research, deps.renderer, deps.sessions);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.fetchRendered(actor, "https://93.184.216.34/spa", true));

        assertEquals(503, failure.getCode());
        assertEquals("RENDERER_UNAVAILABLE", failure.getMessage());
    }

    @Test
    void failedRenderLandsExplicitErrorCodeAndFailedTask() {
        var deps = deps();
        deps.renderer.failWith = new BusinessException(504, "RENDER_TIMEOUT");
        var service = new WebRenderService(deps.research, deps.renderer, deps.sessions);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.fetchRendered(actor, "https://93.184.216.34/spa", true));

        assertEquals(504, failure.getCode());
        assertEquals("FAILED", deps.jdbc.queryForObject(
                "SELECT status FROM web_research_task WHERE id=?",
                String.class, deps.jdbc.queryForObject("SELECT MAX(id) FROM web_research_task", Long.class)));
        assertEquals(0, deps.jdbc.queryForObject("SELECT COUNT(*) FROM web_research_page", Integer.class));
    }

    @Test
    void emptyRenderedBodyIsRejected() {
        var deps = deps();
        deps.renderer.nextPage = new HeadlessRenderer.RenderedPage("Empty shell", "  ");
        var service = new WebRenderService(deps.research, deps.renderer, deps.sessions);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.fetchRendered(actor, "https://93.184.216.34/spa", true));

        assertEquals(422, failure.getCode());
        assertEquals("WEB_RESEARCH_EMPTY_CONTENT", failure.getMessage());
    }

    private Deps deps() {
        var jdbc = researchJdbc();
        KnowledgeCrawlService crawler = new KnowledgeCrawlService(new JdbcTemplate(), mock(com.smartops.service.PersonalKnowledgeService.class)) {
            @Override
            String fetch(String url) {
                return "<html><head><title>Static</title></head><body>static body</body></html>";
            }
        };
        WebResearchService research = new WebResearchService(crawler, jdbc, new com.fasterxml.jackson.databind.ObjectMapper());
        AesGcmCryptoService crypto = new AesGcmCryptoService(Base64.getEncoder().encodeToString(new byte[32]));
        FakeRenderer renderer = new FakeRenderer();
        WebRenderSessionService sessions = new WebRenderSessionService(jdbc, crypto, renderer, 168);
        return new Deps(jdbc, research, renderer, sessions);
    }

    private static final class FakeRenderer implements HeadlessRenderer {
        boolean available = true;
        BusinessException failWith;
        HeadlessRenderer.RenderedPage nextPage = new HeadlessRenderer.RenderedPage("SPA title", "Rendered evidence");
        final List<RenderCall> renderCalls = new ArrayList<>();

        record RenderCall(String url, String storageState) {}

        @Override
        public boolean isAvailable() { return available; }

        @Override
        public RenderedPage render(String url, String storageStateJson) {
            renderCalls.add(new RenderCall(url, storageStateJson));
            if (failWith != null) throw failWith;
            return nextPage;
        }

        @Override
        public String startLogin(long userId) { return "LOGIN_WINDOW_OPENED"; }

        @Override
        public String exportLoginState(long userId) { return confirmedState; }

        String confirmedState;
    }

    private record Deps(JdbcTemplate jdbc, WebResearchService research, FakeRenderer renderer,
                        WebRenderSessionService sessions) {}

    private static JdbcTemplate researchJdbc() {
        var dataSource = new org.springframework.jdbc.datasource.DriverManagerDataSource(
                "jdbc:h2:mem:web-render-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE web_research_task (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, task_type VARCHAR(32) NOT NULL, query_text CLOB NOT NULL, result_count INT NOT NULL DEFAULT 0, status VARCHAR(32) NOT NULL, error_code VARCHAR(500), created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMP NULL)");
        jdbc.execute("CREATE TABLE web_research_page (task_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, url VARCHAR(255) NOT NULL, title VARCHAR(255) NOT NULL, excerpt CLOB NOT NULL, content CLOB NOT NULL, content_hash VARCHAR(64) NOT NULL, fetched_at TIMESTAMP NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE web_render_session (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, enc_storage_state TEXT NULL, display_hint VARCHAR(64) NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP NULL, last_used_at TIMESTAMP NULL, CONSTRAINT uq_web_render_session_user UNIQUE (user_id))");
        return jdbc;
    }
}
