package com.smartops.service;

import com.smartops.entity.OperationSession;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.OperationSessionMapper;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class OperationAgentContextService {
    private final OperationSessionMapper sessionMapper;
    private final OperationRuntimeRegistry registry;
    private final OperatorMemoryService memoryService;

    public Context get(Long userId, String runtimeId) {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        OperationSession session = sessionMapper.findById(runtime.sessionId(), userId);
        if (session == null) throw new BusinessException(404, "SESSION_NOT_FOUND");
        return new Context(runtimeId, session.getName(), session.getHost(), session.getPort(), session.getProtocol(),
                "READ_ONLY", List.of("EXPLAIN_COMMAND", "ANALYZE_OUTPUT", "SEARCH_KNOWLEDGE", "SAVE_TO_MEMORY"),
                "EXECUTE_REQUIRES_EXPLICIT_APPROVAL", memoryService.list(userId));
    }

    public record Context(String runtimeId, String session, String host, Integer port, String protocol,
                          String mode, List<String> allowedActions, String executionBoundary,
                          List<OperatorMemoryService.Memory> memories) {}
}
