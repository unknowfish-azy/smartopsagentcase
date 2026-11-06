package com.smartops.entity;

import lombok.Data;

/**
 * 回放包记录（{@code ReplayBundle} 落库）。
 *
 * <p>变形包必须带 {@code parentBundleId} 且 {@code isHistoricalFact=false}，
 * 不得伪装成历史事实（semantics §2 / §7）。</p>
 */
@Data
public class RecoveryReplayBundleRecord {

    private Long id;
    private Long contractRecordId;
    private String bundleId;
    private String parentBundleId;
    private Boolean historicalFact;
    private String bundleDigest;
    private String bundleJson;
    private String replayResultJson;
    private java.time.LocalDateTime createdAt;
}
