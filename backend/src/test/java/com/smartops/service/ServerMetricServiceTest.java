package com.smartops.service;

import com.smartops.dto.MetricCreateRequest;
import com.smartops.entity.ServerEntity;
import com.smartops.entity.ServerMetricEntity;
import com.smartops.mapper.ServerMapper;
import com.smartops.mapper.ServerMetricMapper;
import com.smartops.module.server.ServerStatus;
import com.smartops.service.impl.ServerMetricServiceImpl;
import com.smartops.vo.ServerMetricVO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ServerMetricServiceTest {

    @Mock
    private ServerMapper serverMapper;

    @Mock
    private ServerMetricMapper metricMapper;

    private ServerMetricService metricService;

    @BeforeEach
    void setUp() {

        metricService =
                new ServerMetricServiceImpl(
                        serverMapper,
                        metricMapper
                );
    }

    @Test
    void normalMetricShouldBeNormal() {

        ServerEntity server =
                ServerEntity.builder()
                        .id(1L)
                        .name("Server-01")
                        .host("127.0.0.1")
                        .port(22)
                        .status(ServerStatus.UNKNOWN)
                        .build();

        when(serverMapper.selectById(1L))
                .thenReturn(server);

        when(metricMapper.insert(
                any(ServerMetricEntity.class)
        )).thenAnswer(invocation -> {

            ServerMetricEntity metric =
                    invocation.getArgument(0);

            metric.setId(1L);

            return 1;
        });

        MetricCreateRequest request =
                new MetricCreateRequest();

        request.setCpuUsage(35.0);
        request.setMemoryUsage(50.0);
        request.setDiskUsage(60.0);

        ServerMetricVO result =
                metricService.create(1L, request);

        assertNotNull(result);

        assertEquals(
                35.0,
                result.getCpuUsage()
        );

        assertEquals(
                "NORMAL",
                result.getStatus().name()
        );

        verify(metricMapper)
                .insert(any(ServerMetricEntity.class));
    }

    @Test
    void highCpuShouldBeCritical() {

        ServerEntity server =
                ServerEntity.builder()
                        .id(1L)
                        .name("Server-01")
                        .host("127.0.0.1")
                        .port(22)
                        .status(ServerStatus.UNKNOWN)
                        .build();

        when(serverMapper.selectById(1L))
                .thenReturn(server);

        when(metricMapper.insert(
                any(ServerMetricEntity.class)
        )).thenAnswer(invocation -> {

            ServerMetricEntity metric =
                    invocation.getArgument(0);

            metric.setId(1L);

            return 1;
        });

        MetricCreateRequest request =
                new MetricCreateRequest();

        request.setCpuUsage(95.0);
        request.setMemoryUsage(50.0);
        request.setDiskUsage(60.0);

        ServerMetricVO result =
                metricService.create(1L, request);

        assertNotNull(result);

        assertEquals(
                "CRITICAL",
                result.getStatus().name()
        );
    }
}