package com.smartops.security;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.exception.BusinessException;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

@Service
public class AdminMfaService {
    public static final String SESSION_VERSION = AdminMfaService.class.getName() + ".version";
    private static final String DRAFT = AdminMfaService.class.getName() + ".draft";
    private final JdbcTemplate jdbc;
    private final UserAccountService accounts;
    private final AesGcmCryptoService crypto;
    private final TotpService totp;
    private final SecurityAuditService audit;
    private final SecurityNoticeService notices;
    private final Clock clock;
    private final AccountSessionRegistry sessions;
    private final AccountAttemptLimiter attempts = new AccountAttemptLimiter();
    private final SecureRandom random = new SecureRandom();

    public AdminMfaService(JdbcTemplate jdbc, UserAccountService accounts, AesGcmCryptoService crypto, TotpService totp,
            SecurityAuditService audit, SecurityNoticeService notices, @Qualifier("mfaClock") Clock clock, AccountSessionRegistry sessions) {
        this.jdbc = jdbc; this.accounts = accounts; this.crypto = crypto; this.totp = totp;
        this.audit = audit; this.notices = notices; this.clock = clock;
        this.sessions = sessions;
    }

    public State state(long userId) { return row(userId, false).state(); }

    public boolean validSession(SessionUser user, HttpSession session) {
        if (!"admin".equals(user.role())) return true;
        if (session == null) return false;
        synchronized (session) {
            try {
                long expected = state(user.id()).version();
                Object actual = session.getAttribute(SESSION_VERSION);
                return expected == (actual instanceof Long version ? version : 0L);
            } catch (IllegalStateException expired) { return false; }
        }
    }

    public Status status(SessionUser user) {
        State state = state(user.id());
        Integer remaining = jdbc.queryForObject("SELECT COUNT(*) FROM account_mfa_recovery WHERE user_id=?", Integer.class, user.id());
        return new Status(state.enabled(), remaining == null ? 0 : remaining);
    }

    @Transactional
    public Enrollment setup(SessionUser user, HttpSession session) {
        accounts.requireMutationAuthority(user, true);
        State state = state(user.id());
        if (state.enabled()) throw new BusinessException(409, "已绑定认证器，请勿重复绑定");
        String secret = totp.newSecret(), challenge = UUID.randomUUID().toString();
        session.setAttribute(DRAFT, new Draft(user.id(), user.authVersion(), state.version(), challenge,
                encrypt(user.id(), secret), clock.instant().plusSeconds(300)));
        return new Enrollment(secret, challenge, 300, "SmartOpsAgent", user.username());
    }

    @Transactional
    public Mutation enable(SessionUser user, HttpSession session, String challenge, String code, String address) {
        accounts.requireMutationAuthority(user, true);
        limit(user.id(), address);
        var draft = session.getAttribute(DRAFT) instanceof Draft value ? value : null;
        if (draft == null || draft.userId() != user.id() || draft.authVersion() != user.authVersion()
                || !draft.challenge().equals(challenge) || !draft.expires().isAfter(clock.instant())) throw new BusinessException(409, "绑定请求已失效，请重新开始");
        Row previous = row(user.id(), true);
        if (previous.enabled() || previous.version() != draft.version()) throw new BusinessException(409, "安全设置已变更，请刷新");
        long step = totp.match(decrypt(user.id(), draft.encrypted()), code, -1);
        if (step < 0) throw rejected();
        long version = previous.version() + 1;
        if (previous.exists()) jdbc.update("UPDATE account_mfa SET secret_encrypted=?,enabled=TRUE,last_used_step=?,version=? WHERE user_id=?", draft.encrypted(), step, version, user.id());
        else jdbc.update("INSERT INTO account_mfa(user_id,secret_encrypted,enabled,last_used_step,version) VALUES(?,?,TRUE,?,?)", user.id(), draft.encrypted(), step, version);
        List<String> recovery = replaceRecovery(user.id());
        audit.record(user, "MFA_ENABLE", user.id().toString(), "SUCCESS");
        notices.record(user, "MFA_ENABLED", "管理员二次认证已启用，其他旧会话已撤销。请离线保存恢复码。");
        afterChange(user, session, version);
        return new Mutation(version, recovery);
    }

    @Transactional
    public Mutation change(SessionUser user, HttpSession session, String code, String address, boolean disable) {
        accounts.requireMutationAuthority(user, true);
        limit(user.id(), address);
        Row previous = row(user.id(), true);
        if (!previous.enabled()) throw new BusinessException(409, "尚未绑定认证器");
        consume(user, previous, code);
        long version = previous.version() + 1;
        List<String> recovery;
        if (disable) {
            jdbc.update("UPDATE account_mfa SET enabled=FALSE,secret_encrypted=NULL,last_used_step=-1,version=? WHERE user_id=?", version, user.id());
            jdbc.update("DELETE FROM account_mfa_recovery WHERE user_id=?", user.id());
            recovery = List.of();
        } else {
            jdbc.update("UPDATE account_mfa SET version=? WHERE user_id=?", version, user.id());
            recovery = replaceRecovery(user.id());
        }
        String kind = disable ? "MFA_DISABLE" : "MFA_RECOVERY_ROTATE";
        audit.record(user, kind, user.id().toString(), "SUCCESS");
        notices.record(user, kind, disable ? "管理员二次认证已关闭，其他旧会话已撤销。若非本人操作，请立即检查账号。" : "恢复码已重新生成，全部旧恢复码已失效，其他旧会话已撤销。");
        afterChange(user, session, version);
        return new Mutation(version, recovery);
    }

    @Transactional
    public void verifyLogin(SessionUser user, long expectedVersion, String code, String address) {
        limit(user.id(), address);
        if (!accounts.isCurrent(user)) throw new BusinessException(401, "账号状态已变更，请重新登录");
        Row current = row(user.id(), true);
        if (!current.enabled() || current.version() != expectedVersion) throw new BusinessException(401, "安全设置已变更，请重新登录");
        consume(user, current, code);
        audit.record(user, "MFA_VERIFY", user.id().toString(), "SUCCESS");
        audit.record(user, "LOGIN", user.id().toString(), "SUCCESS");
    }

    public void clearDraft(HttpSession session) { session.removeAttribute(DRAFT); }

    private void afterChange(SessionUser user, HttpSession current, long version) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() {
                try { current.setAttribute(SESSION_VERSION, version); clearDraft(current); }
                catch (IllegalStateException expired) { }
                finally { sessions.revokeOtherSessions(user.id(), current); }
            }
        });
    }

    private void limit(long userId, String address) {
        attempts.consume("mfa-ip:" + address, 20, 900);
        attempts.consume("mfa-account:" + userId, 10, 900);
    }

    private void consume(SessionUser user, Row current, String code) {
        String supplied = code == null ? "" : code.trim();
        if (supplied.matches("[0-9]{6}")) {
            long step = totp.match(decrypt(user.id(), current.encrypted()), supplied, current.lastStep());
            if (step < 0) throw rejected();
            jdbc.update("UPDATE account_mfa SET last_used_step=? WHERE user_id=?", step, user.id());
            return;
        }
        String normalized = supplied.replace("-", "").toLowerCase(java.util.Locale.ROOT);
        if (!normalized.matches("[a-f0-9]{32}") || jdbc.update("DELETE FROM account_mfa_recovery WHERE user_id=? AND code_hash=?", user.id(), hash(user.id(), normalized)) != 1) throw rejected();
        notices.record(user, "MFA_RECOVERY_USED", "已使用一枚恢复码完成二次认证。该恢复码已失效，请检查剩余数量。");
        audit.record(user, "MFA_RECOVERY_USE", user.id().toString(), "SUCCESS");
    }

    private List<String> replaceRecovery(long userId) {
        jdbc.update("DELETE FROM account_mfa_recovery WHERE user_id=?", userId);
        var codes = new ArrayList<String>();
        for (int index = 0; index < 10; index++) {
            byte[] bytes = new byte[16]; random.nextBytes(bytes);
            String raw = HexFormat.of().formatHex(bytes);
            jdbc.update("INSERT INTO account_mfa_recovery(user_id,code_hash) VALUES(?,?)", userId, hash(userId, raw));
            codes.add(raw.substring(0, 8) + "-" + raw.substring(8, 16) + "-" + raw.substring(16, 24) + "-" + raw.substring(24));
        }
        return List.copyOf(codes);
    }

    private Row row(long userId, boolean lock) {
        var rows = jdbc.query("SELECT secret_encrypted,enabled,last_used_step,version FROM account_mfa WHERE user_id=?" + (lock ? " FOR UPDATE" : ""),
                (result, index) -> new Row(true, result.getString(1), result.getBoolean(2), result.getLong(3), result.getLong(4)), userId);
        return rows.isEmpty() ? new Row(false, null, false, -1, 0) : rows.get(0);
    }

    private String encrypt(long userId, String secret) { return crypto.encrypt("mfa:" + userId + ":" + secret); }
    private String decrypt(long userId, String encrypted) {
        String prefix = "mfa:" + userId + ":";
        try {
            String plain = crypto.decrypt(encrypted);
            if (!plain.startsWith(prefix)) throw new IllegalStateException();
            return plain.substring(prefix.length());
        } catch (Exception failure) { throw new BusinessException(503, "二次认证配置无法读取，请联系运维人员"); }
    }
    private static String hash(long userId, String code) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest((userId + ":" + code).getBytes(StandardCharsets.UTF_8))); }
        catch (Exception failure) { throw new IllegalStateException(failure); }
    }
    private static BusinessException rejected() { return new BusinessException(400, "动态码或恢复码无效、已使用，请重试"); }
    public record State(boolean enabled, long version) {}
    public record Status(boolean enabled, int recoveryCodesRemaining) {}
    public record Enrollment(String secret, String challenge, int expiresIn, String issuer, String account) {}
    public record Mutation(long version, List<String> recoveryCodes) {}
    private record Row(boolean exists, String encrypted, boolean enabled, long lastStep, long version) { State state() { return new State(enabled, version); } }
    private record Draft(long userId, long authVersion, long version, String challenge, String encrypted, Instant expires) implements java.io.Serializable {}
}
