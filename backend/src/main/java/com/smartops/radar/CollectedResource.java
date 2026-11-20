package com.smartops.radar;

import java.time.Instant;

/**
 * 采集器产出的原始条目，未评分、未去重、未入库。
 *
 * <p>采集器不得自行写入数据库或补造字段：发布时间/截止时间拿不到就留空，
 * 由评分环节如实按“未知时间”降级处理。</p>
 */
public record CollectedResource(String externalId, String title, String summary, String url,
                                Instant publishedAt, Instant expiresAt) {
}
