package com.smartops.dto.operations;

import com.smartops.entity.OperationSession;

import java.time.LocalDateTime;

public record OperationSessionResponse(
        Long id, String name, String protocol, String host, Integer port,
        String username, String credential, String identityPath,
        Long groupId, Long jumpSessionId, String tagsJson, String description,
        String accent, Boolean favorite, String status, LocalDateTime lastConnectedAt
) {
    public static OperationSessionResponse from(OperationSession session, String credential) {
        return new OperationSessionResponse(session.getId(), session.getName(), session.getProtocol(), session.getHost(), session.getPort(), session.getUsername(), credential, session.getIdentityPath(), session.getGroupId(), session.getJumpSessionId(), session.getTagsJson(), session.getDescription(), session.getAccent(), session.getFavorite(), session.getStatus(), session.getLastConnectedAt());
    }
}
