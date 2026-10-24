package com.smartops.service;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.dto.operations.CreateOperationSessionRequest;
import com.smartops.dto.operations.OperationSessionResponse;
import com.smartops.entity.OperationCredential;
import com.smartops.entity.OperationSession;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.OperationCredentialMapper;
import com.smartops.mapper.OperationSessionMapper;
import com.smartops.operations.OperationsCapabilityService;
import com.smartops.operations.OperationsProtocol;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class OperationSessionService {
    private final OperationSessionMapper sessionMapper;
    private final OperationCredentialMapper credentialMapper;
    private final AesGcmCryptoService cryptoService;
    private final OperationsCapabilityService capabilityService;

    @Transactional
    public OperationSessionResponse create(Long userId, CreateOperationSessionRequest request) {
        OperationsProtocol protocol;
        try { protocol = OperationsProtocol.valueOf(request.getProtocol().trim().toUpperCase()); }
        catch (IllegalArgumentException ex) { throw new BusinessException(400, "UNSUPPORTED_PROTOCOL"); }
        capabilityService.requireSupported(protocol);

        OperationCredential credential = null;
        if (request.getPassword() != null && !request.getPassword().isBlank()) {
            credential = new OperationCredential();
            credential.setUserId(userId);
            credential.setName(request.getName().trim() + " credential");
            credential.setType("PASSWORD");
            credential.setSecretCiphertext(cryptoService.encrypt(request.getPassword()));
            credentialMapper.insert(credential);
        }

        OperationSession session = new OperationSession();
        session.setUserId(userId); session.setName(request.getName().trim()); session.setProtocol(protocol.name());
        session.setHost(request.getHost().trim()); session.setPort(request.getPort() == null ? 22 : request.getPort());
        session.setUsername(request.getUsername().trim()); session.setCredentialId(credential == null ? null : credential.getId());
        session.setIdentityPath(request.getIdentityPath()); session.setGroupId(request.getGroupId()); session.setJumpSessionId(request.getJumpSessionId());
        session.setTagsJson(request.getTagsJson()); session.setDescription(request.getDescription()); session.setAccent(request.getAccent());
        session.setFavorite(Boolean.TRUE.equals(request.getFavorite())); session.setStatus("IDLE");
        sessionMapper.insert(session);
        return OperationSessionResponse.from(session, credential == null ? null : "****");
    }

    public List<OperationSessionResponse> list(Long userId) {
        return sessionMapper.findAll(userId).stream().map(item -> OperationSessionResponse.from(item, item.getCredentialId() == null ? null : "****")).toList();
    }

    @Transactional
    public void delete(Long userId, Long id) {
        if (sessionMapper.delete(id, userId) == 0) throw new BusinessException(404, "SESSION_NOT_FOUND");
    }
}
