package com.smartops.operations;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Instant;

/** 定期回收已关闭或空闲超时的 SSH 运行通道，避免进程内连接和索引无限累积。 */
@Component
public class OperationRuntimeJanitor {
    private final OperationRuntimeRegistry registry;
    private final long idleTtlMillis;

    public OperationRuntimeJanitor(OperationRuntimeRegistry registry,
                                   @Value("${smartops.operations.ssh.idle-ttl-ms:900000}") long idleTtlMillis) {
        this.registry = registry;
        this.idleTtlMillis = Math.max(1L, idleTtlMillis);
    }

    @Scheduled(fixedDelayString = "${smartops.operations.ssh.sweep-interval-ms:60000}",
            initialDelayString = "${smartops.operations.ssh.sweep-initial-delay-ms:30000}")
    public void sweep() {
        sweepOnce(Instant.now());
    }

    public int sweepOnce(Instant now) {
        return registry.sweep(now, idleTtlMillis);
    }
}
