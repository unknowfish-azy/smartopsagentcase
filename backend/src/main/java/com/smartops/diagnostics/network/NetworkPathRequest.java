package com.smartops.diagnostics.network;

import jakarta.validation.constraints.NotBlank;

/**
 * 网络链路诊断范围。
 *
 * <p>context 必须显式给出，不提供“当前 context”默认值：多集群环境下悄悄跑到另一个
 * 集群去诊断链路，得到的“链路正常”比没有结论更危险。</p>
 *
 * <p>timeoutSeconds 是整单总预算（含所有命令），夹在 10..180 秒；单条命令另有 15s 上限。</p>
 */
public record NetworkPathRequest(
        @NotBlank String context,
        @NotBlank String namespace,
        String host,
        int port,
        String service,
        String ingress,
        String workload,
        boolean tls,
        int timeoutSeconds) {

    private static final int DEFAULT_PORT = 443;
    private static final int DEFAULT_TIMEOUT_SECONDS = 60;
    private static final int MIN_TIMEOUT_SECONDS = 10;
    private static final int MAX_TIMEOUT_SECONDS = 180;

    public NetworkPathRequest {
        context = trimToNull(context);
        namespace = trimToNull(namespace);
        host = trimToNull(host);
        service = trimToNull(service);
        ingress = trimToNull(ingress);
        workload = trimToNull(workload);
        port = port <= 0 ? DEFAULT_PORT : port;
        timeoutSeconds = timeoutSeconds <= 0 ? DEFAULT_TIMEOUT_SECONDS : timeoutSeconds;
        timeoutSeconds = Math.max(MIN_TIMEOUT_SECONDS, Math.min(MAX_TIMEOUT_SECONDS, timeoutSeconds));
    }

    private static String trimToNull(String value) {
        if (value == null) return null;
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
