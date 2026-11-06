package com.smartops.entity;

import lombok.Data;

/**
 * 证据观测记录（{@code EvidenceObservation} 落库）。
 *
 * <p>重复的 {@code observationId} 由唯一约束拒绝，避免同一 ID 重复填补采样槽
 * （semantics §3.1）。观测只存事实，不带任何恢复结论。</p>
 */
@Data
public class RecoveryObservationRecord {

    private Long id;
    private Long contractRecordId;
    private String observationId;
    private String runId;
    private Integer verificationRound;
    private String collectorId;
    private String probeId;
    private String sourceGroup;
    /** UTC ISO-8601；字符串序即时间序。 */
    private String observedAt;
    private String bindingRevision;
    private String observedRevision;
    private Integer sequence;
    private Integer elapsedMs;
    private String payloadJson;
    private String errorText;
    private String artifactDigest;
    private java.time.LocalDateTime createdAt;
}
