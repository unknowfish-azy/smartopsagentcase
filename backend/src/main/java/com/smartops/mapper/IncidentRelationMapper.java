package com.smartops.mapper;

import com.smartops.entity.IncidentRelation;
import com.smartops.module.incident.IncidentRelationType;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface IncidentRelationMapper {

    @Select("SELECT id,incident_id,relation_type,ref_id,ref_type,created_at FROM incident_relation " +
            "WHERE incident_id=#{incidentId} ORDER BY id ASC")
    List<IncidentRelation> findByIncidentId(@Param("incidentId") Long incidentId);

    @Select("SELECT id,incident_id,relation_type,ref_id,ref_type,created_at FROM incident_relation " +
            "WHERE relation_type=#{relationType} AND ref_id=#{refId}")
    List<IncidentRelation> findByRef(@Param("relationType") IncidentRelationType relationType,
                                     @Param("refId") Long refId);

    @Insert("INSERT IGNORE INTO incident_relation(incident_id,relation_type,ref_id,ref_type) " +
            "VALUES(#{incidentId},#{relationType},#{refId},#{refType})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(IncidentRelation relation);

    @Delete("DELETE FROM incident_relation WHERE id=#{id} AND incident_id=#{incidentId}")
    int deleteById(@Param("id") Long id, @Param("incidentId") Long incidentId);
}
