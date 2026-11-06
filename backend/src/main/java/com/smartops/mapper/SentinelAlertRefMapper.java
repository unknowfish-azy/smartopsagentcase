package com.smartops.mapper;

import com.smartops.entity.SentinelAlertRef;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

/**
 * 告警与事件中心之间的桥接查询。
 *
 * <p>只读写 sentinel_alert 的 ticket_id 与 sentinel_alert_event，
 * 不改动告警自身的状态机。</p>
 */
@Mapper
public interface SentinelAlertRefMapper {

    @Select("SELECT a.id,a.task_id,a.severity,a.status,a.title,a.metric,a.observed_value," +
            "a.threshold_value,a.fired_at,a.ticket_id,t.user_id AS owner_id,t.name AS task_name,t.runtime_id " +
            "FROM sentinel_alert a LEFT JOIN sentinel_task t ON t.id=a.task_id WHERE a.id=#{id}")
    SentinelAlertRef findById(@Param("id") Long id);

    /** 回填事件编号；已指向同一个事件时保持幂等。 */
    @Update("UPDATE sentinel_alert SET ticket_id=#{ticketId} WHERE id=#{alertId} AND (ticket_id IS NULL OR ticket_id=#{ticketId})")
    int linkTicket(@Param("alertId") Long alertId, @Param("ticketId") Long ticketId);

    @Insert("INSERT INTO sentinel_alert_event(alert_id,actor_id,kind,detail) " +
            "VALUES(#{alertId},#{actorId},'INCIDENT_LINKED',#{detail})")
    int recordIncidentLinked(@Param("alertId") Long alertId,
                             @Param("actorId") Long actorId,
                             @Param("detail") String detail);

    /** 尚未关单且还没有事件的活动告警，供自动桥接扫描。 */
    @Select("SELECT a.id FROM sentinel_alert a LEFT JOIN sentinel_task t ON t.id=a.task_id " +
            "WHERE a.ticket_id IS NULL AND a.status IN ('OPEN','NOTIFIED') " +
            "ORDER BY a.id ASC LIMIT #{limit}")
    List<Long> findUnlinkedActiveAlertIds(@Param("limit") int limit);
}
