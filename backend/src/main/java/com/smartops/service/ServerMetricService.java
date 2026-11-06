package com.smartops.service;

import com.smartops.dto.MetricCreateRequest;
import com.smartops.vo.ServerMetricVO;

import java.time.LocalDate;
import java.util.List;

public interface ServerMetricService {

    ServerMetricVO create(Long serverId, MetricCreateRequest request);

    ServerMetricVO latest(Long serverId);

    List<ServerMetricVO> latestList(Long serverId);

    /** PERF-05：对指定服务器在指定日期的指标做小时级 avg 聚合（downsampling）。 */
    List<ServerMetricVO> aggregateDaily(Long serverId, LocalDate day);

    /** PERF-05：硬删除 cutoff 之前的旧指标。 */
    int retainOnlyBefore(Long serverId, java.time.LocalDateTime cutoff);

    /** PERF-05：按配置的 retentionDays 计算 cutoff 并清理，返回删除行数。 */
    int retainDefaultFor(Long serverId);
}
