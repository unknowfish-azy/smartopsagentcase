package com.smartops.operations;

import java.io.IOException;

public interface TunnelAccess {
    String startLocalForward(String name, String listenAddress, int listenPort, String targetHost, int targetPort) throws IOException;
    void stopLocalForward(String tunnelId) throws IOException;
}
