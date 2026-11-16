package com.smartops.knowledge;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

/**
 * 显式登录接续的会话保管（T33c，D2 最小版）。
 *
 * <p>一人一会话（unique user_id，重登覆盖）；storage state 经 {@link AesGcmCryptoService} 加密落库；
 * 明文 Cookie/token 不落库、不进日志、不回前端。工具不代填凭据：登录窗口由用户本人显式完成，
 * 会话可随时删除。跨用户访问一律 404。</p>
 */
@Service
public class WebRenderSessionService {

    private final JdbcTemplate jdbc;
    private final AesGcmCryptoService crypto;
    private final HeadlessRenderer renderer;
    private final ObjectMapper mapper = new ObjectMapper();
    private final long ttlHours;

    public WebRenderSessionService(JdbcTemplate jdbc, AesGcmCryptoService crypto, HeadlessRenderer renderer,
                                   @Value("${smartops.web-research.render.session-ttl-hours:168}") long ttlHours) {
        this.jdbc = jdbc;
        this.crypto = crypto;
        this.renderer = renderer;
        this.ttlHours = ttlHours;
    }

    public SessionStatus status(SessionUser actor) {
        requireActor(actor);
        List<SessionStatus> rows = jdbc.query(
                "SELECT display_hint, expires_at, enc_storage_state IS NOT NULL AS configured FROM web_render_session WHERE user_id=?",
                (rs, row) -> new SessionStatus(rs.getBoolean("configured"),
                        rs.getString("display_hint"),
                        rs.getTimestamp("expires_at") == null ? null : rs.getTimestamp("expires_at").toInstant()),
                actor.id());
        return rows.isEmpty()
                ? new SessionStatus(false, null, null)
                : rows.get(0);
    }

    /** 打开受控有头窗口，请用户本人显式登录；旧会话立即失效（重登覆盖）。 */
    public SessionStatus start(SessionUser actor) {
        requireActor(actor);
        requireRenderer();
        renderer.startLogin(actor.id());
        Instant expires = Instant.now().plusSeconds(ttlHours * 3600);
        jdbc.update("DELETE FROM web_render_session WHERE user_id=?", actor.id());
        jdbc.update("INSERT INTO web_render_session(user_id,enc_storage_state,display_hint,created_at,expires_at) VALUES(?,NULL,?,?,?)",
                actor.id(), "PENDING_LOGIN", Timestamp.from(Instant.now()), Timestamp.from(expires));
        return new SessionStatus(false, "PENDING_LOGIN", expires);
    }

    /** 用户确认登录完成后，读取隔离 profile 的 storage state 并加密落库。 */
    public SessionStatus finish(SessionUser actor) {
        requireActor(actor);
        requireRenderer();
        String state = renderer.exportLoginState(actor.id());
        if (state == null) throw new BusinessException(409, "WEB_RENDER_SESSION_NOT_CONFIRMED");
        int entries = countEntries(state);
        if (entries == 0) throw new BusinessException(409, "WEB_RENDER_SESSION_EMPTY");
        String encrypted = crypto.encrypt(state);
        Instant expires = Instant.now().plusSeconds(ttlHours * 3600);
        String hint = trimHint("会话已加密保存 · " + entries + " 条");
        int updated = jdbc.update(
                "UPDATE web_render_session SET enc_storage_state=?,display_hint=?,expires_at=?,last_used_at=? WHERE user_id=?",
                encrypted, hint, Timestamp.from(expires), Timestamp.from(Instant.now()), actor.id());
        if (updated == 0) {
            jdbc.update("INSERT INTO web_render_session(user_id,enc_storage_state,display_hint,created_at,expires_at) VALUES(?,?,?,?,?)",
                    actor.id(), encrypted, hint, Timestamp.from(Instant.now()), Timestamp.from(expires));
        }
        renderer.wipeProfile(actor.id());
        return new SessionStatus(true, hint, expires);
    }

    public void delete(SessionUser actor) {
        requireActor(actor);
        jdbc.update("DELETE FROM web_render_session WHERE user_id=?", actor.id());
        renderer.wipeProfile(actor.id());
    }

    /** 渲染时载入会话；过期按 SESSION_EXPIRED 返回，不静默降级为匿名。 */
    String storageStateForRender(SessionUser actor) {
        requireActor(actor);
        List<Row> rows = jdbc.query(
                "SELECT enc_storage_state, expires_at FROM web_render_session WHERE user_id=?",
                (rs, row) -> new Row(rs.getString("enc_storage_state"),
                        rs.getTimestamp("expires_at") == null ? null : rs.getTimestamp("expires_at").toInstant()),
                actor.id());
        if (rows.isEmpty() || rows.get(0).enc() == null) return null;
        Row row = rows.get(0);
        if (row.expiresAt() != null && row.expiresAt().isBefore(Instant.now())) {
            throw new BusinessException(409, "WEB_RENDER_SESSION_EXPIRED");
        }
        jdbc.update("UPDATE web_render_session SET last_used_at=? WHERE user_id=?", Timestamp.from(Instant.now()), actor.id());
        return crypto.decrypt(row.enc());
    }

    private void requireRenderer() {
        if (!renderer.isAvailable()) throw new BusinessException(503, "RENDERER_UNAVAILABLE");
    }

    private int countEntries(String state) {
        try {
            JsonNode node = mapper.readTree(state);
            if (node.isArray()) return node.size();
            int cookies = node.path("cookies").size();
            int origins = node.path("origins").size();
            return cookies + origins;
        } catch (Exception failure) {
            return 0;
        }
    }

    private static String trimHint(String hint) {
        return hint.length() > 64 ? hint.substring(0, 64) : hint;
    }

    private static void requireActor(SessionUser actor) {
        if (actor == null) throw new BusinessException(401, "登录状态已失效");
    }

    private record Row(String enc, Instant expiresAt) {}
    public record SessionStatus(boolean configured, String displayHint, Instant expiresAt) {}
}
