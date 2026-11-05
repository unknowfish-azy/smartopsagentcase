package com.smartops.mapper;

import com.smartops.entity.ServerMetricEntity;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.boot.test.autoconfigure.MybatisTest;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@MybatisTest(properties = "spring.flyway.enabled=false")
class ServerMetricMapperTest {

    @Autowired
    private ServerMetricMapper metricMapper;

    @Test
    void selectLatestShouldReturnData() {

        ServerMetricEntity metric =
                metricMapper.selectLatestByServerId(1L);

        assertNotNull(metric);

        assertEquals(
                1L,
                metric.getServerId()
        );

        assertEquals(
                35.5,
                metric.getCpuUsage()
        );
    }

    @Test
    void selectLatestListShouldReturnData() {

        List<ServerMetricEntity> list =
                metricMapper.selectLatestListByServerId(1L);

        assertNotNull(list);
        assertFalse(list.isEmpty());
    }
}