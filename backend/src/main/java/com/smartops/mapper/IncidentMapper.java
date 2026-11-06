package com.smartops.mapper;

import com.smartops.entity.Incident;
import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentStatus;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface IncidentMapper {

    @Select("SELECT id,title,description,status,severity,priority,source,category,tags," +
            "reporter_id,assignee_id,related_asset_id,related_asset_type,related_service," +
            "sla_target_minutes,sla_deadline,acknowledged_at,mitigated_at,resolved_at,closed_at," +
            "root_cause,resolution,postmortem,created_at,updated_at " +
            "FROM incident WHERE id=#{id}")
    Incident findById(@Param("id") Long id);

    @Insert("INSERT INTO incident(title,description,status,severity,priority,source,category,tags," +
            "reporter_id,assignee_id,related_asset_id,related_asset_type,related_service," +
            "sla_target_minutes,sla_deadline,root_cause,resolution,postmortem) " +
            "VALUES(#{title},#{description},#{status},#{severity},#{priority},#{source},#{category},#{tags}," +
            "#{reporterId},#{assigneeId},#{relatedAssetId},#{relatedAssetType},#{relatedService}," +
            "#{slaTargetMinutes},#{slaDeadline},#{rootCause},#{resolution},#{postmortem})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(Incident incident);

    @Update("UPDATE incident SET title=#{title},description=#{description},severity=#{severity}," +
            "priority=#{priority},category=#{category},tags=#{tags}," +
            "related_asset_id=#{relatedAssetId},related_asset_type=#{relatedAssetType},related_service=#{relatedService}," +
            "sla_target_minutes=#{slaTargetMinutes},sla_deadline=#{slaDeadline},updated_at=CURRENT_TIMESTAMP " +
            "WHERE id=#{id}")
    int update(Incident incident);

    /** 更新状态，同时写入对应时间戳。 */
    @Update("UPDATE incident SET status=#{status}," +
            "acknowledged_at=CASE WHEN #{status}='ACK' THEN COALESCE(acknowledged_at,CURRENT_TIMESTAMP) ELSE acknowledged_at END," +
            "mitigated_at=CASE WHEN #{status}='MITIGATING' THEN COALESCE(mitigated_at,CURRENT_TIMESTAMP) ELSE mitigated_at END," +
            "resolved_at=CASE WHEN #{status}='RESOLVED' THEN COALESCE(resolved_at,CURRENT_TIMESTAMP) ELSE resolved_at END," +
            "closed_at=CASE WHEN #{status}='CLOSED' THEN COALESCE(closed_at,CURRENT_TIMESTAMP) ELSE closed_at END," +
            "root_cause=COALESCE(#{rootCause},root_cause)," +
            "resolution=COALESCE(#{resolution},resolution)," +
            "postmortem=COALESCE(#{postmortem},postmortem)," +
            "updated_at=CURRENT_TIMESTAMP " +
            "WHERE id=#{id}")
    int updateStatus(@Param("id") Long id,
                     @Param("status") IncidentStatus status,
                     @Param("rootCause") String rootCause,
                     @Param("resolution") String resolution,
                     @Param("postmortem") String postmortem);

    @Update("UPDATE incident SET assignee_id=#{assigneeId},updated_at=CURRENT_TIMESTAMP WHERE id=#{id}")
    int assign(@Param("id") Long id, @Param("assigneeId") Long assigneeId);

    @Select("<script>" +
            "SELECT id,title,description,status,severity,priority,source,category,tags," +
            "reporter_id,assignee_id,related_asset_id,related_asset_type,related_service," +
            "sla_target_minutes,sla_deadline,acknowledged_at,mitigated_at,resolved_at,closed_at," +
            "root_cause,resolution,postmortem,created_at,updated_at FROM incident " +
            "<where>" +
            "  <if test='status != null'>AND status=#{status}</if>" +
            "  <if test='severity != null'>AND severity=#{severity}</if>" +
            "  <if test='assigneeId != null'>AND assignee_id=#{assigneeId}</if>" +
            "  <if test='reporterId != null'>AND reporter_id=#{reporterId}</if>" +
            "</where>" +
            " ORDER BY created_at DESC" +
            " <if test='limit != null'>LIMIT #{limit}</if>" +
            "</script>")
    List<Incident> search(@Param("status") IncidentStatus status,
                          @Param("severity") IncidentSeverity severity,
                          @Param("assigneeId") Long assigneeId,
                          @Param("reporterId") Long reporterId,
                          @Param("limit") Integer limit);

    @Select("SELECT COUNT(*) FROM incident WHERE status=#{status}")
    int countByStatus(@Param("status") IncidentStatus status);

    /** SLA 即将超时或已超时且未关闭的事件。 */
    @Select("SELECT id,title,status,severity,sla_deadline FROM incident " +
            "WHERE status NOT IN ('CLOSED') AND sla_deadline IS NOT NULL AND sla_deadline < #{now} " +
            "ORDER BY sla_deadline ASC LIMIT #{limit}")
    List<Incident> findSlaBreached(@Param("now") LocalDateTime now, @Param("limit") int limit);
}
