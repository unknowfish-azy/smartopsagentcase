package com.smartops.operations;

import com.smartops.exception.BusinessException;
import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.function.Supplier;

/**
 * 同用户同会话的连接建立单飞：并发请求只允许一个真正拨号，其余等待并复用同一结果。
 *
 * <p>单飞范围是当前进程；多副本部署时各副本仍可能各自建立一条连接，需由上层接入统一会话存储后再收敛。</p>
 */
@Component
public class OperationConnectionCoordinator {
    private final OperationRuntimeRegistry registry;
    private final ConcurrentHashMap<String, CompletableFuture<ConnectionResult>> inFlight = new ConcurrentHashMap<>();

    public OperationConnectionCoordinator(OperationRuntimeRegistry registry) {
        this.registry = registry;
    }

    public ConnectionResult establish(Long userId, Long sessionId, Supplier<ConnectionResult> connector) {
        if (userId == null || sessionId == null) return connector.get();
        Optional<String> existing = registry.findBySession(userId, sessionId);
        if (existing.isPresent()) return ConnectionResult.reused(existing.get());

        String key = userId + ":" + sessionId;
        CompletableFuture<ConnectionResult> mine = new CompletableFuture<>();
        CompletableFuture<ConnectionResult> leader = inFlight.putIfAbsent(key, mine);
        if (leader != null) {
            try {
                return leader.get();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new BusinessException(503, "CONNECT_WAIT_INTERRUPTED");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                if (cause instanceof RuntimeException runtime) throw runtime;
                throw new BusinessException(500, "CONNECT_FAILED");
            }
        }
        try {
            ConnectionResult result = connector.get();
            mine.complete(result);
            return result;
        } catch (RuntimeException ex) {
            mine.completeExceptionally(ex);
            throw ex;
        } finally {
            inFlight.remove(key, mine);
        }
    }
}
