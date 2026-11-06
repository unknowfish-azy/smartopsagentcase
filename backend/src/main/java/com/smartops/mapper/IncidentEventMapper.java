package com.smartops.mapper;

import com.smartops.entity.IncidentEvent;
import com.smartops.module.incident.IncidentEventKind;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface IncidentEventMapper {

    @Select("SELECT id,incident_id,at,actor_id,kind,detail FROM incident_event " +
            "WHERE incident_id=#{incidentId} ORDER BY id ASC")
    List<IncidentEvent> findByIncidentId(@Param("incidentId") Long incidentId);

    @Insert("INSERT INTO incident_event(incident_id,actor_id,kind,detail) " +
            "VALUES(#{incidentId},#{actorId},#{kind},#{detail})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(IncidentEvent event);

    /** 批量写入时间线。 */
    @Insert("<script>" +
            "INSERT INTO incident_event(incident_id,actor_id,kind,detail) VALUES " +
            "<foreach collection='events' item='e' separator=','>" +
            "(#{e.incidentId},#{e.actorId},#{e.kind},#{e.detail})" +
            "</foreach>" +
            "</script>")
    int batchInsert(@Param("events") List<IncidentEvent> events);

    @Select("SELECT COUNT(*) FROM incident_event WHERE incident_id=#{incidentId} AND kind=#{kind}")
    int countByKind(@Param("incidentId") Long incidentId, @Param("kind") IncidentEventKind kind);
}
