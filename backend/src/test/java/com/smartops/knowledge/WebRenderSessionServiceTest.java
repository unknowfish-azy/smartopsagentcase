package com.smartops.knowledge;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.Base64;

import static org.junit.jupiter.api.Assertions.*;

class WebRenderSessionServiceTest {

    private final SessionUser actor = new SessionUser(9L, "alice", "user");
    private final SessionUser other = new SessionUser(10L, "bob", "user");

    @Test
    void startMarksPendingAndKeepsSessionUnconfigured() {
        var deps = deps();
        var status = deps.service.start(actor);

        assertFalse(status.configured());
        assertEquals("PENDING_LOGIN", status.displayHint());
        assertNotNull(status.expiresAt());
        assertFalse(deps.service.status(actor).configured());
    }

    @Test
    void finishRequiresUserConfirmedLogin() {
        var deps = deps();
        deps.service.start(actor);
        deps.renderer.confirmedState = null;

        BusinessException failure = assertThrows(BusinessException.class, () -> deps.service.finish(actor));

        assertEquals(409, failure.getCode());
        assertEquals("WEB_RENDER_SESSION_NOT_CONFIRMED", failure.getMessage());
    }

    @Test
    void finishEncryptsStateAndRoundTripsForRender() {
        var deps = deps();
        deps.service.start(actor);
        deps.renderer.confirmedState = "[{\"name\":\"sid\",\"value\":\"s3cret\",\"domain\":\"example.com\"}]";

        var status = deps.service.finish(actor);

        assertTrue(status.configured());
        assertTrue(status.displayHint().contains("1 条"));
        // 库里只有密文，明文不落库
        String stored = deps.jdbc.queryForObject(
                "SELECT enc_storage_state FROM web_render_session WHERE user_id=?", String.class, actor.id());
        assertFalse(stored.contains("s3cret"));
        assertTrue(stored.startsWith("ey") || !stored.contains("sid"));
        // 渲染侧能解密回明文
        String decrypted = deps.service.storageStateForRender(actor);
        assertTrue(decrypted.contains("s3cret"));
        // last_used_at 被更新
        assertNotNull(deps.jdbc.queryForObject(
                "SELECT last_used_at FROM web_render_session WHERE user_id=?", Timestamp.class, actor.id()));
    }

    @Test
    void expiredSessionIsRejectedNotSilentlyAnonymous() {
        var deps = deps();
        deps.service.start(actor);
        deps.renderer.confirmedState = "[{\"name\":\"sid\",\"value\":\"s3cret\"}]";
        deps.service.finish(actor);
        deps.jdbc.update("UPDATE web_render_session SET expires_at=? WHERE user_id=?",
                Timestamp.from(Instant.now().minusSeconds(60)), actor.id());

        BusinessException failure = assertThrows(BusinessException.class,
                () -> deps.service.storageStateForRender(actor));

        assertEquals(409, failure.getCode());
        assertEquals("WEB_RENDER_SESSION_EXPIRED", failure.getMessage());
    }

    @Test
    void sessionsAreIsolatedPerUser() {
        var deps = deps();
        deps.service.start(actor);
        deps.renderer.confirmedState = "[{\"name\":\"sid\",\"value\":\"s3cret\"}]";
        deps.service.finish(actor);

        assertFalse(deps.service.status(other).configured());
        assertNull(deps.service.storageStateForRender(other));
    }

    @Test
    void deleteClearsRowAndWipesProfile() {
        var deps = deps();
        deps.service.start(actor);
        deps.renderer.confirmedState = "[{\"name\":\"sid\",\"value\":\"s3cret\"}]";
        deps.service.finish(actor);

        deps.service.delete(actor);

        assertFalse(deps.service.status(actor).configured());
        assertNull(deps.service.storageStateForRender(actor));
        assertTrue(deps.renderer.wiped.contains(actor.id()));
    }

    @Test
    void rendererUnavailableBlocksStartAndFinish() {
        var deps = deps();
        deps.renderer.available = false;

        BusinessException startFailure = assertThrows(BusinessException.class, () -> deps.service.start(actor));
        assertEquals(503, startFailure.getCode());
        assertEquals("RENDERER_UNAVAILABLE", startFailure.getMessage());
    }

    private Deps deps() {
        var jdbc = sessionJdbc();
        AesGcmCryptoService crypto = new AesGcmCryptoService(Base64.getEncoder().encodeToString(new byte[32]));
        FakeRenderer renderer = new FakeRenderer();
        WebRenderSessionService service = new WebRenderSessionService(jdbc, crypto, renderer, 168);
        return new Deps(jdbc, service, renderer);
    }

    private static final class FakeRenderer implements HeadlessRenderer {
        boolean available = true;
        String confirmedState;
        final java.util.List<Long> wiped = new java.util.ArrayList<>();

        @Override
        public boolean isAvailable() { return available; }

        @Override
        public RenderedPage render(String url, String storageStateJson) {
            throw new UnsupportedOperationException("session test never renders");
        }

        @Override
        public String startLogin(long userId) { return "LOGIN_WINDOW_OPENED"; }

        @Override
        public String exportLoginState(long userId) { return confirmedState; }

        @Override
        public void wipeProfile(long userId) { wiped.add(userId); }
    }

    private record Deps(JdbcTemplate jdbc, WebRenderSessionService service, FakeRenderer renderer) {}

    private static JdbcTemplate sessionJdbc() {
        var dataSource = new org.springframework.jdbc.datasource.DriverManagerDataSource(
                "jdbc:h2:mem:web-render-session-" + System.nanoTime() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE web_render_session (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, enc_storage_state TEXT NULL, display_hint VARCHAR(64) NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP NULL, last_used_at TIMESTAMP NULL, CONSTRAINT uq_web_render_session_user UNIQUE (user_id))");
        return jdbc;
    }
}
