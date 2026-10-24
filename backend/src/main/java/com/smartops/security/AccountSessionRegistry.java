package com.smartops.security;

import com.smartops.exception.BusinessException;
import jakarta.servlet.http.HttpSession;
import org.springframework.context.event.EventListener;
import org.springframework.security.web.session.HttpSessionDestroyedEvent;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class AccountSessionRegistry {
    private final ConcurrentHashMap<String, Entry> sessions = new ConcurrentHashMap<>();

    public void register(HttpSession session, SessionUser user) {
        sessions.entrySet().removeIf(entry -> entry.getValue().session == session);
        sessions.put(UUID.randomUUID().toString(), new Entry(session, user, Instant.now().toString()));
    }

    public List<SessionView> list(Long userId, HttpSession current) {
        var result = new ArrayList<SessionView>();
        for (var entry : sessions.entrySet()) {
            Entry value = entry.getValue();
            try {
                long lastSeen = value.session.getLastAccessedTime();
                if (userId == null || userId.equals(value.user.id())) result.add(new SessionView(entry.getKey(), value.user.id(), value.user.username(), value.user.portal(), value.createdAt, Instant.ofEpochMilli(lastSeen).toString(), value.session == current));
            } catch (IllegalStateException expired) { sessions.remove(entry.getKey(), value); }
        }
        result.sort(Comparator.comparing(SessionView::createdAt).reversed());
        return result;
    }

    public void revoke(String id, Long owner) {
        requireActive(id, owner);
        Entry entry = sessions.get(id);
        if (entry == null) return;
        if (sessions.remove(id, entry)) invalidate(entry.session);
    }

    public void requireActive(String id, Long owner) {
        Entry entry = sessions.get(id);
        if (entry == null || (owner != null && !owner.equals(entry.user.id()))) throw new BusinessException(404, "会话不存在或已失效");
        try { entry.session.getLastAccessedTime(); }
        catch (IllegalStateException expired) {
            sessions.remove(id, entry);
            throw new BusinessException(404, "会话不存在或已失效");
        }
    }

    public void revokeIfPresent(String id, Long owner) {
        try { revoke(id, owner); }
        catch (BusinessException missing) { if (missing.getCode() != 404) throw missing; }
    }

    public void revokeUser(Long userId) {
        for (var entry : sessions.entrySet()) {
            if (userId.equals(entry.getValue().user.id()) && sessions.remove(entry.getKey(), entry.getValue())) invalidate(entry.getValue().session);
        }
    }

    public void revokeOtherSessions(Long userId, HttpSession current) {
        for (var entry : sessions.entrySet()) {
            if (userId.equals(entry.getValue().user.id()) && entry.getValue().session != current
                    && sessions.remove(entry.getKey(), entry.getValue())) invalidate(entry.getValue().session);
        }
    }

    public void forget(HttpSession session) { sessions.entrySet().removeIf(entry -> entry.getValue().session == session); }

    private void invalidate(HttpSession session) {
        try {
            session.setAttribute(AuthenticatedSessionHandshakeInterceptor.REVOKED, true);
            session.invalidate();
        } catch (IllegalStateException expired) { }
    }

    @EventListener public void destroyed(HttpSessionDestroyedEvent event) {
        sessions.entrySet().removeIf(entry -> entry.getValue().session == event.getSession());
    }

    private record Entry(HttpSession session, SessionUser user, String createdAt) {}
    public record SessionView(String id, Long userId, String username, String portal, String createdAt, String lastSeenAt, boolean current) {}
}
