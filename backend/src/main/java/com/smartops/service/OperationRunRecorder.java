package com.smartops.service;

import com.smartops.operations.OperationRuntime;

import java.time.Instant;

public interface OperationRunRecorder {
    RunHandle start(String traceId, Long userId, OperationRuntime runtime, String toolId, Instant startedAt);

    void recordCommand(RunHandle run, int sequence, String command, int exitCode,
                       String stdout, String stderr, Instant startedAt, Instant endedAt);

    void finish(RunHandle run, String status, Instant endedAt);

    record RunHandle(Long id, String traceId) {}
}
