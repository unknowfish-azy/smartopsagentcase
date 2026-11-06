package com.smartops.diagnostics.host;

import jakarta.validation.constraints.NotBlank;

/**
 * 主机诊断范围。
 *
 * <p>sampleSeconds 是采样窗口（秒），夹在 1..5，默认 2；vmstat/jstat 的采样次数
 * 由它推导（2..4 次），避免在目标主机上做长时间采样。</p>
 */
public record HostDiagnosisRequest(@NotBlank String runtimeId, int sampleSeconds) {

    private static final int DEFAULT_SAMPLE_SECONDS = 2;
    private static final int MIN_SAMPLE_SECONDS = 1;
    private static final int MAX_SAMPLE_SECONDS = 5;

    public HostDiagnosisRequest {
        runtimeId = runtimeId == null ? null : runtimeId.trim();
        sampleSeconds = sampleSeconds <= 0 ? DEFAULT_SAMPLE_SECONDS : sampleSeconds;
        sampleSeconds = Math.max(MIN_SAMPLE_SECONDS, Math.min(MAX_SAMPLE_SECONDS, sampleSeconds));
    }
}
