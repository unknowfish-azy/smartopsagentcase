package com.smartops.mapper;

import com.smartops.entity.RecoveryObservationRecord;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/** 证据观测表访问。观测按 sequence + observed_at 重建顺序，不依赖入库顺序（semantics §3.1）。 */
@Mapper
public interface RecoveryObservationMapper {

    String COLUMNS = "id,contract_record_id,observation_id,run_id,verification_round,collector_id," +
            "probe_id,source_group,observed_at,binding_revision,observed_revision,sequence,elapsed_ms," +
            "payload_json,error_text,artifact_digest,created_at";

    @Insert("INSERT INTO recovery_observation_record(contract_record_id,observation_id,run_id," +
            "verification_round,collector_id,probe_id,source_group,observed_at,binding_revision," +
            "observed_revision,sequence,elapsed_ms,payload_json,error_text,artifact_digest) " +
            "VALUES(#{contractRecordId},#{observationId},#{runId},#{verificationRound},#{collectorId}," +
            "#{probeId},#{sourceGroup},#{observedAt},#{bindingRevision},#{observedRevision},#{sequence}," +
            "#{elapsedMs},#{payloadJson},#{errorText},#{artifactDigest})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(RecoveryObservationRecord record);

    @Select("SELECT " + COLUMNS + " FROM recovery_observation_record " +
            "WHERE contract_record_id=#{contractRecordId} ORDER BY sequence ASC, observed_at ASC, id ASC")
    List<RecoveryObservationRecord> findByContract(@Param("contractRecordId") Long contractRecordId);
}
