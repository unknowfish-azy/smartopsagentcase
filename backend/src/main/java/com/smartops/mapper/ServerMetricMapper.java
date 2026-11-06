package com.smartops.mapper;

import com.smartops.entity.ServerMetricEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface ServerMetricMapper {

    int insert(ServerMetricEntity entity);

    ServerMetricEntity selectLatestByServerId(Long serverId);

    /** PERF-05：返回最近 N 条（点数预算由调用方决定）。 */
    List<ServerMetricEntity> selectLatestListByServerId(
            @Param("serverId") Long serverId,
            @Param("maxPoints") int maxPoints);

    /** PERF-05：按小时聚合指定日期的 avg 行（downsampling）。 */
    List<ServerMetricEntity> selectHourlyAggregate(
            @Param("serverId") Long serverId,
            @Param("day") LocalDate day);

    /** PERF-05：删除 cutoff 之前的旧指标，返回删除行数。 */
    int deleteOlderThan(
            @Param("serverId") Long serverId,
            @Param("cutoff") LocalDateTime cutoff);
}
