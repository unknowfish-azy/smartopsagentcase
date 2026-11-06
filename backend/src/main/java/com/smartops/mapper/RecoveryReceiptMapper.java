package com.smartops.mapper;

import com.smartops.entity.RecoveryReceiptRecord;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/** 核验回执表访问。只存已发生的核验结果，不在这里推导或补签回执。 */
@Mapper
public interface RecoveryReceiptMapper {

    String COLUMNS = "id,contract_record_id,receipt_id,run_id,verification_round,verdict,receipt_state," +
            "issued_at,valid_until,evidence_snapshot_digest,policy_version,receipt_json," +
            "obligation_results_json,probe_decision_json,invalidation_events_json,created_at";

    @Insert("INSERT INTO recovery_receipt_record(contract_record_id,receipt_id,run_id,verification_round," +
            "verdict,receipt_state,issued_at,valid_until,evidence_snapshot_digest,policy_version," +
            "receipt_json,obligation_results_json,probe_decision_json,invalidation_events_json) " +
            "VALUES(#{contractRecordId},#{receiptId},#{runId},#{verificationRound},#{verdict},#{receiptState}," +
            "#{issuedAt},#{validUntil},#{evidenceSnapshotDigest},#{policyVersion},#{receiptJson}," +
            "#{obligationResultsJson},#{probeDecisionJson},#{invalidationEventsJson})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(RecoveryReceiptRecord record);

    @Select("SELECT " + COLUMNS + " FROM recovery_receipt_record " +
            "WHERE contract_record_id=#{contractRecordId} ORDER BY created_at DESC, id DESC LIMIT 1")
    RecoveryReceiptRecord findLatest(@Param("contractRecordId") Long contractRecordId);

    @Select("SELECT " + COLUMNS + " FROM recovery_receipt_record " +
            "WHERE contract_record_id=#{contractRecordId} AND receipt_id=#{receiptId}")
    RecoveryReceiptRecord findByReceiptId(@Param("contractRecordId") Long contractRecordId,
                                          @Param("receiptId") String receiptId);

    @Select("SELECT " + COLUMNS + " FROM recovery_receipt_record WHERE id=#{id}")
    RecoveryReceiptRecord findById(@Param("id") Long id);

    @Select("SELECT " + COLUMNS + " FROM recovery_receipt_record " +
            "WHERE contract_record_id=#{contractRecordId} ORDER BY created_at ASC, id ASC")
    List<RecoveryReceiptRecord> listByContract(@Param("contractRecordId") Long contractRecordId);
}
