package com.smartops.operations;

import com.smartops.entity.OperationSession;

public interface ConnectionAdapter {
    ConnectionResult connect(Long userId, OperationSession session, String secret, HostKeyDecision decision);
}
