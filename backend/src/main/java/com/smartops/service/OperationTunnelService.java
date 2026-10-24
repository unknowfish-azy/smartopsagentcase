package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.operations.TunnelAccess;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.io.IOException;

@Service
@RequiredArgsConstructor
public class OperationTunnelService {
    private final OperationRuntimeRegistry registry;

    public String start(Long userId, String runtimeId, String name, String listenAddress, int listenPort, String targetHost, int targetPort) {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!(runtime instanceof TunnelAccess access)) throw new BusinessException(409, "TUNNEL_NOT_AVAILABLE");
        try { return access.startLocalForward(name, listenAddress, listenPort, targetHost, targetPort); }
        catch (IOException ex) { throw new BusinessException(502, "TUNNEL_START_FAILED: " + ex.getMessage()); }
    }

    public void stop(Long userId, String runtimeId, String tunnelId) {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!(runtime instanceof TunnelAccess access)) throw new BusinessException(409, "TUNNEL_NOT_AVAILABLE");
        try { access.stopLocalForward(tunnelId); }
        catch (IOException ex) { throw new BusinessException(502, "TUNNEL_STOP_FAILED: " + ex.getMessage()); }
    }
}
