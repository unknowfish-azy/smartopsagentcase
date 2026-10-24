package com.smartops.mapper;

import com.smartops.entity.ServerMetricEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface ServerMetricMapper {

    /**
     * 新增监控指标
     */
    int insert(ServerMetricEntity metric);

    /**
     * 查询服务器最新一条指标
     */
    ServerMetricEntity selectLatestByServerId(Long serverId);

    /**
     * 查询服务器最近100条指标
     */
    List<ServerMetricEntity> selectLatestListByServerId(Long serverId);

    /**
     * 查询指定时间范围内的监控指标
     */
    List<ServerMetricEntity> selectByTimeRange(
            @Param("serverId") Long serverId,
            @Param("startTime") java.time.LocalDateTime startTime,
            @Param("endTime") java.time.LocalDateTime endTime
    );

    /**
     * 删除某台服务器的全部监控数据
     */
    int deleteByServerId(Long serverId);
}