package com.smartops.diagnostics.kubernetes;

import jakarta.validation.constraints.NotBlank;

/**
 * Kubernetes 诊断范围。
 *
 * <p>context 必须显式给出，不提供“当前 context”默认值：多集群环境下悄悄跑到另一个
 * 集群的诊断结论比没有结论更危险。</p>
 */
public record KubernetesDiagnosisRequest(
        @NotBlank String context,
        @NotBlank String namespace,
        String workload,
        String pod,
        String container,
        int sinceMinutes) {

    private static final int DEFAULT_SINCE_MINUTES = 60;
    private static final int MIN_SINCE_MINUTES = 1;
    private static final int MAX_SINCE_MINUTES = 1440;

    public KubernetesDiagnosisRequest {
        context = trimToNull(context);
        namespace = trimToNull(namespace);
        workload = trimToNull(workload);
        pod = trimToNull(pod);
        container = trimToNull(container);
        sinceMinutes = sinceMinutes <= 0 ? DEFAULT_SINCE_MINUTES : sinceMinutes;
        sinceMinutes = Math.max(MIN_SINCE_MINUTES, Math.min(MAX_SINCE_MINUTES, sinceMinutes));
    }

    private static String trimToNull(String value) {
        if (value == null) return null;
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
