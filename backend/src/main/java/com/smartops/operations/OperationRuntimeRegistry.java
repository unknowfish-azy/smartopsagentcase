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

    public int size() { return runtimes.size(); }
}
