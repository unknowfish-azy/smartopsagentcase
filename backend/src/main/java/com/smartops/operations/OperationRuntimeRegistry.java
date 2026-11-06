package com.smartops.operations;

import com.smartops.exception.BusinessException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

@Component
public class OperationRuntimeRegistry {
    private static final int DEFAULT_MAX_PER_USER = 20;
    private static final int DEFAULT_MAX_PER_SESSION = 4;

    private final Map<String, Entry> runtimes = new ConcurrentHashMap<>();
    private final Map<String, String> bySession = new ConcurrentHashMap<>();
    private final int maxPerUser;
    private final int maxPerSession;

    public OperationRuntimeRegistry() {
        this(DEFAULT_MAX_PER_USER, DEFAULT_MAX_PER_SESSION);
    }

    @Autowired
    public OperationRuntimeRegistry(
            @Value("${smartops.operations.ssh.max-per-user:20}") int maxPerUser,
            @Value("${smartops.operations.ssh.max-per-session:4}") int maxPerSession) {
        this.maxPerUser = Math.max(1, maxPerUser);
        this.maxPerSession = Math.max(1, maxPerSession);
    }

    public String register(OperationRuntime runtime) {
        if (runtime == null) throw new BusinessException(400, "RUNTIME_REQUIRED");
        if (runtime.userId() != null) {
            long userCount = runtimes.values().stream()
                    .filter(entry -> runtime.userId().equals(entry.runtime.userId()))
                    .count();
            if (userCount >= maxPerUser) {
                throw new BusinessException(429, "RUNTIME_QUOTA_EXCEEDED");
            }
        }
        String sessionKey = key(runtime.userId(), runtime.sessionId());
        if (sessionKey != null) {
            long sessionCount = runtimes.values().stream()
                    .filter(entry -> sessionKey.equals(key(entry.runtime.userId(), entry.runtime.sessionId())))
                    .count();
            if (sessionCount >= maxPerSession) {
                throw new BusinessException(429, "RUNTIME_SESSION_LIMIT_EXCEEDED");
            }
        }
        String id = UUID.randomUUID().toString();
        runtimes.put(id, new Entry(runtime));
        if (sessionKey != null) bySession.put(sessionKey, id);
        return id;
    }

    public OperationRuntime requireOwned(String runtimeId, Long userId) {
        Entry entry = runtimes.get(runtimeId);
        if (entry == null || !userId.equals(entry.runtime.userId())) {
            throw new BusinessException(404, "RUNTIME_NOT_FOUND");
        }
        entry.touch();
        return entry.runtime;
    }

    public OperationRuntime removeOwned(String runtimeId, Long userId) {
        OperationRuntime runtime = requireOwned(runtimeId, userId);
        Entry entry = runtimes.get(runtimeId);
        if (entry != null) removeEntry(runtimeId, entry);
        return runtime;
    }

    /**
     * 找出该用户在此连接上仍然存活的运行通道。
     *
     * <p>按 userId+sessionId 建立索引，重绑运行连接时 O(1) 复用已有通道，
     * 避免每绑一次就多挂一条 SSH 连接，且旧通道没人回收。</p>
     */
    public Optional<String> findBySession(Long userId, Long sessionId) {
        String sessionKey = key(userId, sessionId);
        if (sessionKey == null) return Optional.empty();
        String runtimeId = bySession.get(sessionKey);
        if (runtimeId == null) return Optional.empty();
        Entry entry = runtimes.get(runtimeId);
        if (entry == null || !entry.runtime.isOpen()) {
            bySession.remove(sessionKey, runtimeId);
            if (entry != null) removeEntry(runtimeId, entry);
            return Optional.empty();
        }
        entry.touch();
        return Optional.of(runtimeId);
    }

    /**
     * 回收已关闭和空闲超时的运行通道；返回本次清理数量。
     */
    public int sweep(Instant now, long idleTtlMillis) {
        long cutoff = now.minusMillis(Math.max(1L, idleTtlMillis)).toEpochMilli();
        int removed = 0;
        for (Map.Entry<String, Entry> item : runtimes.entrySet()) {
            Entry entry = item.getValue();
            boolean open;
            try {
                open = entry.runtime.isOpen();
            } catch (RuntimeException ex) {
                open = false;
            }
            if (!open || entry.lastAccessMillis() < cutoff) {
                if (removeEntry(item.getKey(), entry)) removed++;
            }
        }
        return removed;
    }

    public int size() { return runtimes.size(); }

    private boolean removeEntry(String runtimeId, Entry entry) {
        boolean removed = runtimes.remove(runtimeId, entry);
        if (removed) {
            String sessionKey = key(entry.runtime.userId(), entry.runtime.sessionId());
            if (sessionKey != null) bySession.remove(sessionKey, runtimeId);
            try {
                entry.runtime.close();
            } catch (RuntimeException ignored) {
                // 清理路径不因单个通道关闭异常而中断其他回收。
            }
        }
        return removed;
    }

    private static String key(Long userId, Long sessionId) {
        if (userId == null || sessionId == null) return null;
        return userId + ":" + sessionId;
    }

    private static final class Entry {
        private final OperationRuntime runtime;
        private final AtomicLong lastAccessMillis;

        private Entry(OperationRuntime runtime) {
            this.runtime = runtime;
            this.lastAccessMillis = new AtomicLong(System.currentTimeMillis());
        }

        private void touch() {
            lastAccessMillis.set(System.currentTimeMillis());
        }

        private long lastAccessMillis() {
            return lastAccessMillis.get();
        }
    }
}
