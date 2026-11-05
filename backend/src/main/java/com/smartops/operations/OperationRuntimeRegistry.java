package com.smartops.operations;

import com.smartops.exception.BusinessException;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class OperationRuntimeRegistry {
    private final Map<String, OperationRuntime> runtimes = new ConcurrentHashMap<>();

    public String register(OperationRuntime runtime) {
        String id = UUID.randomUUID().toString();
        runtimes.put(id, runtime);
        return id;
    }

    public OperationRuntime requireOwned(String runtimeId, Long userId) {
        OperationRuntime runtime = runtimes.get(runtimeId);
        if (runtime == null || !userId.equals(runtime.userId())) {
            throw new BusinessException(404, "RUNTIME_NOT_FOUND");
        }
        return runtime;
    }

    public OperationRuntime removeOwned(String runtimeId, Long userId) {
        OperationRuntime runtime = requireOwned(runtimeId, userId);
        runtimes.remove(runtimeId, runtime);
        return runtime;
    }

    /**
     * 找出该用户在此连接上仍然存活的运行通道。
     *
     * <p>用于「重绑运行连接」：同一连接重复绑定时应复用已有通道，
     * 否则每绑一次就多挂一条 SSH 连接，且旧通道没人回收。</p>
     */
    public java.util.Optional<String> findBySession(Long userId, Long sessionId) {
        if (userId == null || sessionId == null) return java.util.Optional.empty();
        return runtimes.entrySet().stream()
                .filter(entry -> entry.getValue().isOpen()
                        && userId.equals(entry.getValue().userId())
                        && sessionId.equals(entry.getValue().sessionId()))
                .map(Map.Entry::getKey)
                .findFirst();
    }

    public int size() { return runtimes.size(); }
}
