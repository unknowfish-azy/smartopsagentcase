package com.smartops.service;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.entity.OperationCredential;
import com.smartops.entity.OperationSession;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.OperationCredentialMapper;
import com.smartops.mapper.OperationSessionMapper;
import com.smartops.operations.*;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class OperationConnectionService {
    private final OperationSessionMapper sessionMapper;
    private final OperationCredentialMapper credentialMapper;
    private final AesGcmCryptoService cryptoService;
    private final SshConnectionAdapter adapter;
    private final OperationConnectionCoordinator coordinator;
    private final SshTargetPolicy targetPolicy;

    public ConnectionResult connect(Long userId, Long sessionId, HostKeyDecision decision) {
        HostKeyDecision effective = decision == null ? HostKeyDecision.NONE : decision;
        return coordinator.establish(userId, sessionId, () -> connectOnce(userId, sessionId, effective));
    }

    private ConnectionResult connectOnce(Long userId, Long sessionId, HostKeyDecision decision) {
        OperationSession session = sessionMapper.findById(sessionId, userId);
        if (session == null) throw new BusinessException(404, "SESSION_NOT_FOUND");
        String secret = null;
        if (session.getCredentialId() != null) {
            OperationCredential credential = credentialMapper.findById(session.getCredentialId(), userId);
            if (credential == null) throw new BusinessException(404, "CREDENTIAL_NOT_FOUND");
            secret = cryptoService.decrypt(credential.getSecretCiphertext());
        }
        OperationSession jumpSession = session.getJumpSessionId() == null ? null : sessionMapper.findById(session.getJumpSessionId(), userId);
        if (session.getJumpSessionId() != null && jumpSession == null) throw new BusinessException(404, "JUMP_SESSION_NOT_FOUND");
        // 连接期二次收口：会话可能是策略生效前创建的，或库中被直接改写
        targetPolicy.requireAllowedTarget(session.getHost(), session.getPort());
        targetPolicy.requireAllowedIdentity(session.getIdentityPath());
        return adapter.connect(userId, session, secret, decision, jumpSession);
    }

    public void close(Long userId, String runtimeId, OperationRuntimeRegistry registry) {
        registry.removeOwned(runtimeId, userId).close();
    }
}
