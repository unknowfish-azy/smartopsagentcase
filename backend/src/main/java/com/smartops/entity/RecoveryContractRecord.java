package com.smartops.entity;

import lombok.Data;

/**
 * 恢复契约记录（recovery-contract/v1 的 {@code RecoveryContract} 落库）。
 *
 * <p>正文以 canonical JSON 原样保存在 {@code contractJson}，冗余列只用于查询与唯一约束。
 * 契约不授予执行权限：{@code runId} 只引用既有运行记录，不替代 Run 模型。</p>
 */
@Data
public class RecoveryContractRecord {

    private Long id;
    private String contractId;
    private String contractVersion;
    private Long runId;
    private Long ownerUserId;
    private String idempotencyKey;
    private String scope;
    private String targetId;
    private String targetKind;
    private String expectedRevision;
    private String digest;
    private String contractJson;
    private String claimJson;
    private Long expiresAfterMs;
    /** UTC ISO-8601，与 semantics §4.1 一致。 */
    private String validFrom;
    private java.time.LocalDateTime createdAt;
}
