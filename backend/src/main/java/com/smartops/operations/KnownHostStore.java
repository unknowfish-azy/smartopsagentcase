package com.smartops.operations;

import com.smartops.entity.OperationKnownHost;

import java.util.Optional;

public interface KnownHostStore {
    Optional<OperationKnownHost> find(Long sessionId, String host, int port);

    void save(OperationKnownHost knownHost);
}
