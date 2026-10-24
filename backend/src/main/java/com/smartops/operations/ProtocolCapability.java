package com.smartops.operations;

public record ProtocolCapability(
        OperationsProtocol protocol,
        String status,
        String reason
) {
}
