package com.smartops.security;

import com.smartops.exception.BusinessException;

import java.util.HashMap;
import java.util.Map;

final class AccountAttemptLimiter {
    private final Map<String, Window> windows = new HashMap<>();

    synchronized void consume(String key, int limit, long seconds) {
        long now = System.currentTimeMillis();
        windows.entrySet().removeIf(entry -> entry.getValue().until <= now);
        Window current = windows.get(key);
        if ((current != null && current.count >= limit) || (current == null && windows.size() >= 10000)) {
            throw new BusinessException(429, "操作过于频繁，请稍后重试");
        }
        windows.put(key, new Window(current == null ? 1 : current.count + 1, current == null ? now + seconds * 1000 : current.until));
    }

    synchronized void clear(String key) { windows.remove(key); }

    private record Window(int count, long until) {}
}
