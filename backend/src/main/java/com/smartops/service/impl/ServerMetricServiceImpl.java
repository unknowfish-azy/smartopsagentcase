package com.smartops.service.impl;

import com.smartops.dto.MetricCreateRequest;
import com.smartops.entity.ServerEntity;
import com.smartops.entity.ServerMetricEntity;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.ServerMetricMapper;
import com.smartops.mapper.ServerMapper;
import com.smartops.module.server.MetricStatus;
import com.smartops.module.server.ServerStatus;
import com.smartops.service.ServerMetricService;
import com.smartops.vo.ServerMetricVO;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

@Service
@Transactional
public class ServerMetricServiceImpl implements ServerMetricService {

    private final ServerMapper serverMapper;
    private final ServerMetricMapper metricMapper;
    private final int maxPointsPerServer;
    private final int retentionDays;

    public ServerMetricServiceImpl(ServerMapper serverMapper,
                                   ServerMetricMapper metricMapper,
                                   @Value("${smartops.observability.metric.max-points-per-server:2000}") int maxPointsPerServer,
                                   @Value("${smartops.observability.metric.retention-days:90}") int retentionDays) {
        this.serverMapper = serverMapper;
        this.metricMapper = metricMapper;
        this.maxPointsPerServer = maxPointsPerServer;
        this.retentionDays = retentionDays;
    }

    @Override
    public ServerMetricVO create(Long serverId,
                                 MetricCreateRequest request) {

        ServerEntity server = serverMapper.selectById(serverId);
        if (server == null) {
            throw new BusinessException("服务器不存在");
        }

        MetricStatus status = calculateStatus(
                request.getCpuUsage(),
                request.getMemoryUsage(),
                request.getDiskUsage()
        );

        LocalDateTime now = LocalDateTime.now();

        ServerMetricEntity metric = ServerMetricEntity.builder()
                .serverId(serverId)
                .cpuUsage(request.getCpuUsage())
                .memoryUsage(request.getMemoryUsage())
                .diskUsage(request.getDiskUsage())
                .networkIn(request.getNetworkIn())
                .networkOut(request.getNetworkOut())
                .loadAverage(request.getLoadAverage())
                .status(status)
                .collectedAt(now)
                .build();

        server.setStatus(
                status == MetricStatus.NORMAL
                        ? ServerStatus.ONLINE
                        : ServerStatus.WARNING
        );
        server.setUpdatedAt(now);

        serverMapper.update(server);
        metricMapper.insert(metric);

        return toVO(metric);
    }

    @Override
    @Transactional(readOnly = true)
    public ServerMetricVO latest(Long serverId) {

        if (serverMapper.selectById(serverId) == null) {
            throw new BusinessException("服务器不存在");
        }

        ServerMetricEntity metric =
                metricMapper.selectLatestByServerId(serverId);

        if (metric == null) {
            throw new BusinessException("暂无监控数据");
        }

        return toVO(metric);
    }

    @Override
    @Transactional(readOnly = true)
    public List<ServerMetricVO> latestList(Long serverId) {

        if (serverMapper.selectById(serverId) == null) {
            throw new BusinessException("服务器不存在");
        }

        return metricMapper
                .selectLatestListByServerId(serverId, maxPointsPerServer)
                .stream()
                .map(this::toVO)
                .toList();
    }

    @Override
    @Transactional(readOnly = true)
    public List<ServerMetricVO> aggregateDaily(Long serverId, LocalDate day) {
        if (serverMapper.selectById(serverId) == null) {
            throw new BusinessException("服务器不存在");
        }
        return metricMapper.selectHourlyAggregate(serverId, day)
                .stream()
                .map(this::toVO)
                .toList();
    }

    @Override
    public int retainOnlyBefore(Long serverId, LocalDateTime cutoff) {
        if (serverMapper.selectById(serverId) == null) {
            throw new BusinessException("服务器不存在");
        }
        return metricMapper.deleteOlderThan(serverId, cutoff);
    }

    @Override
    public int retainDefaultFor(Long serverId) {
        LocalDateTime cutoff = LocalDateTime.now().minusDays(retentionDays);
        return retainOnlyBefore(serverId, cutoff);
    }

    private MetricStatus calculateStatus(Double cpu,
                                         Double memory,
                                         Double disk) {

        if (cpu >= 90 || memory >= 90 || disk >= 90) {
            return MetricStatus.CRITICAL;
        }

        if (cpu >= 80 || memory >= 80 || disk >= 80) {
            return MetricStatus.WARNING;
        }

        return MetricStatus.NORMAL;
    }

    private ServerMetricVO toVO(ServerMetricEntity entity) {

        return ServerMetricVO.builder()
                .id(entity.getId())
                .serverId(entity.getServerId())
                .cpuUsage(entity.getCpuUsage())
                .memoryUsage(entity.getMemoryUsage())
                .diskUsage(entity.getDiskUsage())
                .networkIn(entity.getNetworkIn())
                .networkOut(entity.getNetworkOut())
                .loadAverage(entity.getLoadAverage())
                .status(entity.getStatus())
                .collectedAt(entity.getCollectedAt())
                .build();
    }
}
