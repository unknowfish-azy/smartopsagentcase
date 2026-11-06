package com.smartops.entity;

import lombok.Data;

/**
 * 核验回执记录（{@code VerificationReceipt} 落库）。
 *
 * <p>回执正文原样存 {@code receiptJson}；{@code verdict}/{@code receiptState} 冗余列用于过滤。
 * 服务层强制：非 {@code VERIFIED} 时 {@code receiptState=NOT_ISSUED} 且时间字段为 null。</p>
 */
@Data
public class RecoveryReceiptRecord {

    private Long id;
    private Long contractRecordId;
    private String receiptId;
    private String runId;
    private Integer verificationRound;
    private String verdict;
    private String receiptState;
    private String issuedAt;
    private String validUntil;
    private String evidenceSnapshotDigest;
    private String policyVersion;
    private String receiptJson;
    private String obligationResultsJson;
    private String probeDecisionJson;
    private String invalidationEventsJson;
    private java.time.LocalDateTime createdAt;
}
