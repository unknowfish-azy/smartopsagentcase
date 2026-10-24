package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRedactor;
import com.smartops.operations.OperationRiskPolicy;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.security.SecureRandom;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
@RequiredArgsConstructor
public class MultiExecService {
    private final OperationRuntimeRegistry registry;
    private final OperationRiskPolicy riskPolicy = new OperationRiskPolicy();
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Preview> previews = new ConcurrentHashMap<>();

    public Preview preview(Long userId, String command, List<String> runtimeIds, boolean productionTarget) {
        if (command == null || command.isBlank()) throw new BusinessException(400, "COMMAND_REQUIRED");
        if (runtimeIds == null || runtimeIds.isEmpty()) throw new BusinessException(400, "TARGETS_REQUIRED");
        List<String> immutableTargets = List.copyOf(runtimeIds);
        immutableTargets.forEach(id -> registry.requireOwned(id, userId));
        OperationRiskPolicy.Assessment assessment = riskPolicy.assess(command, immutableTargets.size() > 1, productionTarget);
        String id = UUID.randomUUID().toString();
        String nonce = nonce();
        Preview preview = new Preview(id, immutableTargets, OperationRedactor.redact(command), assessment.risk().name(), assessment.requiredApprovals(), nonce);
        previews.put(id, preview);
        return preview;
    }

    public ExecutionResult execute(Long userId, String previewId, String confirmationNonce, String secondConfirmationNonce) {
        Preview preview = previews.get(previewId);
        if (preview == null) throw new BusinessException(404, "PREVIEW_NOT_FOUND");
        if (!preview.confirmationNonce().equals(confirmationNonce)) throw new BusinessException(409, "CONFIRMATION_REQUIRED");
        if (preview.requiredApprovals() > 1 && !preview.confirmationNonce().equals(secondConfirmationNonce)) {
            throw new BusinessException(409, "SECOND_CONFIRMATION_REQUIRED");
        }
        List<TargetResult> results = preview.targetRuntimeIds().stream().map(runtimeId -> {
            try {
                OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
                runtime.write(preview.redactedCommand() + "\n");
                return new TargetResult(runtimeId, "SENT", null);
            } catch (IOException | RuntimeException ex) {
                return new TargetResult(runtimeId, "FAILED", OperationRedactor.redact(ex.getMessage()));
            }
        }).toList();
        previews.remove(previewId);
        return new ExecutionResult(preview.id(), results);
    }

    private String nonce() {
        byte[] bytes = new byte[18];
        random.nextBytes(bytes);
        return java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public record Preview(String id, List<String> targetRuntimeIds, String redactedCommand, String risk,
                          int requiredApprovals, String confirmationNonce) {}
    public record TargetResult(String runtimeId, String status, String error) {}
    public record ExecutionResult(String previewId, List<TargetResult> results) {}
}
