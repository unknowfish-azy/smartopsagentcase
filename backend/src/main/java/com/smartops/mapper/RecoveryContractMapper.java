package com.smartops.mapper;

import com.smartops.entity.RecoveryContractRecord;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/** 恢复契约主表访问。查询一律带 owner_user_id，避免客户端自述身份越权（platform-integration §2.2）。 */
@Mapper
public interface RecoveryContractMapper {

    String COLUMNS = "id,contract_id,contract_version,run_id,owner_user_id,idempotency_key,scope," +
            "target_id,target_kind,expected_revision,digest,contract_json,claim_json,expires_after_ms," +
            "valid_from,created_at";

    @Insert("INSERT INTO recovery_contract_record(contract_id,contract_version,run_id,owner_user_id," +
            "idempotency_key,scope,target_id,target_kind,expected_revision,digest,contract_json," +
            "claim_json,expires_after_ms,valid_from) VALUES(#{contractId},#{contractVersion},#{runId}," +
            "#{ownerUserId},#{idempotencyKey},#{scope},#{targetId},#{targetKind},#{expectedRevision}," +
            "#{digest},#{contractJson},#{claimJson},#{expiresAfterMs},#{validFrom})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(RecoveryContractRecord record);

    @Select("SELECT " + COLUMNS + " FROM recovery_contract_record WHERE id=#{id} AND owner_user_id=#{ownerUserId}")
    RecoveryContractRecord findByIdForOwner(@Param("id") Long id, @Param("ownerUserId") Long ownerUserId);

    @Select("SELECT " + COLUMNS + " FROM recovery_contract_record " +
            "WHERE owner_user_id=#{ownerUserId} AND idempotency_key=#{idempotencyKey}")
    RecoveryContractRecord findByIdempotencyKey(@Param("ownerUserId") Long ownerUserId,
                                                @Param("idempotencyKey") String idempotencyKey);

    /** 内部写入方（agent）按 run 归属校验时用：只返回归属主体，不暴露正文。 */
    @Select("SELECT owner_user_id FROM recovery_contract_record WHERE id=#{id}")
    Long findOwnerUserId(@Param("id") Long id);

    @Select("<script>" +
            "SELECT " + COLUMNS + " FROM recovery_contract_record " +
            "<where>" +
            "  owner_user_id=#{ownerUserId}" +
            "  <if test='runId != null'>AND run_id=#{runId}</if>" +
            "</where>" +
            " ORDER BY created_at DESC, id DESC" +
            " LIMIT #{limit} OFFSET #{offset}" +
            "</script>")
    List<RecoveryContractRecord> search(@Param("ownerUserId") Long ownerUserId,
                                        @Param("runId") Long runId,
                                        @Param("offset") int offset,
                                        @Param("limit") int limit);

    @Select("<script>" +
            "SELECT COUNT(*) FROM recovery_contract_record " +
            "<where>" +
            "  owner_user_id=#{ownerUserId}" +
            "  <if test='runId != null'>AND run_id=#{runId}</if>" +
            "</where>" +
            "</script>")
    int count(@Param("ownerUserId") Long ownerUserId, @Param("runId") Long runId);
}
