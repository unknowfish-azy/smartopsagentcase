package com.smartops.operations;

import com.smartops.exception.BusinessException;
import org.springframework.stereotype.Service;

import java.util.EnumMap;
import java.util.Map;

@Service
public class OperationsCapabilityService {

    public Map<OperationsProtocol, ProtocolCapability> list() {
        Map<OperationsProtocol, ProtocolCapability> capabilities =
                new EnumMap<>(OperationsProtocol.class);

        for (OperationsProtocol protocol : OperationsProtocol.values()) {
            String status = protocol == OperationsProtocol.SSH
                    || protocol == OperationsProtocol.SFTP
                    ? "SUPPORTED"
                    : "REQUIRES_NATIVE_BRIDGE";

            String reason = "SUPPORTED".equals(status)
                    ? "Available through the local Operations Bridge"
                    : "Requires a native protocol bridge in a later release";

            capabilities.put(protocol,
                    new ProtocolCapability(protocol, status, reason));
        }

        return Map.copyOf(capabilities);
    }

    public ProtocolCapability requireSupported(
            OperationsProtocol protocol) {

        ProtocolCapability capability = list().get(protocol);

        if (capability == null || !"SUPPORTED".equals(capability.status())) {
            throw new BusinessException(409,
                    "REQUIRES_NATIVE_BRIDGE: " + protocol);
        }

        return capability;
    }
}
