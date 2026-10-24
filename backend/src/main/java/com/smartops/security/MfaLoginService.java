package com.smartops.security;

import com.smartops.exception.BusinessException;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

@Service
public class MfaLoginService {
    private static final String PENDING = MfaLoginService.class.getName() + ".pending";
    private final AdminMfaService mfa;
    private final SecurityNoticeService notices;
    private final Clock clock;
    public MfaLoginService(AdminMfaService mfa, SecurityNoticeService notices, @Qualifier("mfaClock") Clock clock) {
        this.mfa = mfa; this.notices = notices; this.clock = clock;
    }

    public Challenge begin(SessionUser user, long version, HttpSession session) {
        String nonce = UUID.randomUUID().toString();
        synchronized (session) { session.setAttribute(PENDING, new Pending(user, version, nonce, clock.instant().plusSeconds(300), 0)); }
        return new Challenge(true, nonce, 300);
    }

    public <Result> Result complete(HttpSession session, String challenge, String code, String address, java.util.function.Function<Verified, Result> establish) {
        if (session == null) throw expired();
        synchronized (session) {
            Pending pending = session.getAttribute(PENDING) instanceof Pending value ? value : null;
            if (pending == null || !pending.nonce().equals(challenge)) throw expired();
            if (!pending.expires().isAfter(clock.instant()) || pending.attempts() >= 5) { clear(session); throw expired(); }
            int attempts = pending.attempts() + 1;
            session.setAttribute(PENDING, new Pending(pending.user(), pending.version(), pending.nonce(), pending.expires(), attempts));
            try {
                mfa.verifyLogin(pending.user(), pending.version(), code, address);
                Result result = establish.apply(new Verified(pending.user(), pending.version()));
                clear(session);
                return result;
            } catch (BusinessException failure) {
                if (attempts >= 5 || failure.getCode() == 401 || failure.getCode() == 429) clear(session);
                if (failure.getCode() == 400) notices.failure(pending.user());
                if (attempts >= 5) throw new BusinessException(429, "二次认证尝试过多，请返回密码登录后重试");
                throw failure;
            }
        }
    }

    public void clear(HttpSession session) {
        if (session != null) synchronized (session) { session.removeAttribute(PENDING); }
    }
    private static BusinessException expired() { return new BusinessException(401, "二次认证请求已失效，请返回密码登录"); }
    public record Challenge(boolean mfaRequired, String challenge, int expiresIn) {}
    public record Verified(SessionUser user, long version) {}
    private record Pending(SessionUser user, long version, String nonce, Instant expires, int attempts) implements java.io.Serializable {}
}
