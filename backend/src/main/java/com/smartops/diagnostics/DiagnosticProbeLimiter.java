package com.smartops.diagnostics;

import com.smartops.exception.BusinessException;
import org.springframework.stereotype.Component;
import java.util.HashMap;
import java.util.Map;

@Component
public class DiagnosticProbeLimiter {
    public static final int PER_USER_LIMIT = 2;
    public static final int GLOBAL_LIMIT = 8;
    private final Map<Long, Integer> active = new HashMap<>();
    private int total;
    public synchronized Lease acquire(Long userId) {
        int count = active.getOrDefault(userId, 0);
        if (count >= PER_USER_LIMIT || total >= GLOBAL_LIMIT) throw new BusinessException(429, "检查任务繁忙，请稍后重试");
        active.put(userId, count + 1);
        total++;
        return new Lease(userId);
    }
    public final class Lease implements AutoCloseable {
        private final Long userId;
        private boolean released;
        private Lease(Long userId) { this.userId = userId; }
        @Override public void close() {
            synchronized (DiagnosticProbeLimiter.this) {
                if (released) return;
                released = true;
                total--;
                int remaining = active.get(userId) - 1;
                if (remaining == 0) active.remove(userId); else active.put(userId, remaining);
            }
        }
    }
}
