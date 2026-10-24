package com.smartops.service;

import com.smartops.dto.MetricCreateRequest;
import com.smartops.vo.ServerMetricVO;

import java.util.List;

public interface ServerMetricService {

    ServerMetricVO create(Long serverId, MetricCreateRequest request);

    ServerMetricVO latest(Long serverId);

    List<ServerMetricVO> latestList(Long serverId);
}