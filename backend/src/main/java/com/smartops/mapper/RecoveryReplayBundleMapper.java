package com.smartops.mapper;

import com.smartops.entity.RecoveryReplayBundleRecord;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/** 回放包表访问。回放包是冻结输入，读取时不改写、不重新生成 digest。 */
@Mapper
public interface RecoveryReplayBundleMapper {

    String COLUMNS = "id,contract_record_id,bundle_id,parent_bundle_id,is_historical_fact," +
            "bundle_digest,bundle_json,replay_result_json,created_at";

    @Insert("INSERT INTO recovery_replay_bundle_record(contract_record_id,bundle_id,parent_bundle_id," +
            "is_historical_fact,bundle_digest,bundle_json,replay_result_json) VALUES(#{contractRecordId}," +
            "#{bundleId},#{parentBundleId},#{historicalFact},#{bundleDigest},#{bundleJson},#{replayResultJson})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(RecoveryReplayBundleRecord record);

    @Select("SELECT " + COLUMNS + " FROM recovery_replay_bundle_record WHERE " +
            "contract_record_id=#{contractRecordId} AND bundle_id=#{bundleId}")
    RecoveryReplayBundleRecord findByBundleId(@Param("contractRecordId") Long contractRecordId,
                                              @Param("bundleId") String bundleId);

    @Select("SELECT " + COLUMNS + " FROM recovery_replay_bundle_record " +
            "WHERE contract_record_id=#{contractRecordId} ORDER BY created_at DESC, id DESC LIMIT 1")
    RecoveryReplayBundleRecord findLatest(@Param("contractRecordId") Long contractRecordId);

    @Select("SELECT " + COLUMNS + " FROM recovery_replay_bundle_record " +
            "WHERE contract_record_id=#{contractRecordId} ORDER BY created_at ASC, id ASC")
    List<RecoveryReplayBundleRecord> listByContract(@Param("contractRecordId") Long contractRecordId);
}
