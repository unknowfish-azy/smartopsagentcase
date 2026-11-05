package com.smartops.cloud;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * 云账号 / 同步记录 / CMDB 资源的持久化（OPS-02、OPS-03）。
 *
 * 资源写入以 resource_uid 唯一索引为准：先查再写，冲突时回退为 UPDATE，
 * 同一资源重复同步不会重复建档。
 */
@Repository
public class CloudAssetRepository {

    private final JdbcTemplate jdbc;

    public CloudAssetRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // ===================== 云账号 =====================

    public long insertAccount(CloudAccount account) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cloud_account
                        (provider, account_id, display_name, region, endpoint, project_id, team_id,
                         owner_user_id, credential_ref, credential_scope, enabled, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, new String[]{"id"});
            statement.setString(1, account.provider().wireName());
            statement.setString(2, account.accountId());
            statement.setString(3, account.displayName());
            statement.setString(4, account.region());
            statement.setString(5, account.endpoint());
            statement.setString(6, account.projectId());
            if (account.teamId() == null) {
                statement.setNull(7, java.sql.Types.BIGINT);
            } else {
                statement.setLong(7, account.teamId());
            }
            statement.setLong(8, account.ownerUserId());
            statement.setString(9, account.credentialRef());
            statement.setString(10, account.credentialScope());
            statement.setBoolean(11, account.enabled());
            LocalDateTime now = account.createdAt() == null ? LocalDateTime.now() : account.createdAt();
            statement.setTimestamp(12, java.sql.Timestamp.valueOf(now));
            statement.setTimestamp(13, java.sql.Timestamp.valueOf(now));
            return statement;
        }, keys);
        Number id = keys.getKey();
        return id == null ? 0 : id.longValue();
    }

    public Optional<CloudAccount> findAccount(long id) {
        List<CloudAccount> rows = jdbc.query(
                "SELECT * FROM cloud_account WHERE id=?", accountMapper(), id);
        return rows.stream().findFirst();
    }

    public Optional<CloudAccount> findByProviderIdentity(CloudProvider provider, String accountId, String region) {
        List<CloudAccount> rows = jdbc.query(
                "SELECT * FROM cloud_account WHERE provider=? AND account_id=? AND region=?",
                accountMapper(), provider.wireName(), accountId, region);
        return rows.stream().findFirst();
    }

    public List<CloudAccount> listAccountsForUser(long userId) {
        return jdbc.query("""
                SELECT * FROM cloud_account a
                WHERE a.owner_user_id=?
                   OR a.team_id IN (SELECT team_id FROM team_member WHERE user_id=?)
                ORDER BY a.id DESC
                """, accountMapper(), userId, userId);
    }

    public void updateSyncState(long accountId, LocalDateTime at, String status) {
        jdbc.update("UPDATE cloud_account SET last_sync_at=?, last_sync_status=?, updated_at=? WHERE id=?",
                java.sql.Timestamp.valueOf(at), status, java.sql.Timestamp.valueOf(at), accountId);
    }

    // ===================== 同步记录 =====================

    public long insertSyncRun(SyncRunRecord run) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("""
                    INSERT INTO cloud_sync_run
                        (account_id, actor_user_id, status, started_at, ended_at, pages, discovered,
                         created_count, updated_count, marked_missing, permission_denied,
                         error_code, error_message)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, new String[]{"id"});
            statement.setLong(1, run.accountId());
            if (run.actorUserId() == null) {
                statement.setNull(2, java.sql.Types.BIGINT);
            } else {
                statement.setLong(2, run.actorUserId());
            }
            statement.setString(3, run.status());
            statement.setTimestamp(4, java.sql.Timestamp.valueOf(run.startedAt()));
            if (run.endedAt() == null) {
                statement.setNull(5, java.sql.Types.TIMESTAMP);
            } else {
                statement.setTimestamp(5, java.sql.Timestamp.valueOf(run.endedAt()));
            }
            statement.setInt(6, run.pages());
            statement.setInt(7, run.discovered());
            statement.setInt(8, run.created());
            statement.setInt(9, run.updated());
            statement.setInt(10, run.markedMissing());
            statement.setBoolean(11, run.permissionDenied());
            statement.setString(12, run.errorCode());
            statement.setString(13, run.errorMessage());
            return statement;
        }, keys);
        Number id = keys.getKey();
        return id == null ? 0 : id.longValue();
    }

    public List<SyncRunRecord> listSyncRuns(long accountId, int limit) {
        return jdbc.query("""
                SELECT * FROM cloud_sync_run WHERE account_id=? ORDER BY id DESC LIMIT ?
                """, (result, row) -> new SyncRunRecord(
                result.getLong("id"),
                result.getLong("account_id"),
                result.getObject("actor_user_id", Long.class),
                result.getString("status"),
                toTime(result, "started_at"),
                toTime(result, "ended_at"),
                result.getInt("pages"),
                result.getInt("discovered"),
                result.getInt("created_count"),
                result.getInt("updated_count"),
                result.getInt("marked_missing"),
                result.getBoolean("permission_denied"),
                result.getString("error_code"),
                result.getString("error_message")
        ), accountId, limit);
    }

    public void updateSyncRun(SyncRunRecord run) {
        jdbc.update("""
                UPDATE cloud_sync_run
                SET status=?, ended_at=?, pages=?, discovered=?, created_count=?, updated_count=?,
                    marked_missing=?, permission_denied=?, error_code=?, error_message=?
                WHERE id=?
                """,
                run.status(), timestamp(run.endedAt()), run.pages(), run.discovered(), run.created(),
                run.updated(), run.markedMissing(), run.permissionDenied(), run.errorCode(), run.errorMessage(),
                run.id());
    }

    // ===================== 资源 =====================

    public Optional<Long> findAssetIdByUid(String resourceUid) {
        List<Long> rows = jdbc.queryForList(
                "SELECT id FROM asset_resource WHERE resource_uid=?", Long.class, resourceUid);
        return rows.stream().findFirst();
    }

    public void insertAsset(AssetWrite write) {
        jdbc.update("""
                INSERT INTO asset_resource
                    (resource_uid, provider, provider_account_id, region, resource_type, provider_resource_id,
                     name, status, status_reason, environment, business, owner, source, source_account_id,
                     last_sync_run_id, collected_at, first_seen_at, last_seen_at, tags_json, metadata_json,
                     created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                write.resourceUid(), write.provider(), write.providerAccountId(), write.region(),
                write.resourceType(), write.providerResourceId(), write.name(), "ACTIVE", null,
                write.environment(), write.business(), write.owner(), "CLOUD_SYNC", write.sourceAccountId(),
                write.lastSyncRunId(), timestamp(write.collectedAt()), timestamp(write.collectedAt()),
                timestamp(write.collectedAt()), write.tagsJson(), write.metadataJson(),
                timestamp(write.collectedAt()), timestamp(write.collectedAt()));
        appendChange(new ChangeWrite(write.resourceUid(), "DISCOVERED", "status", null, "ACTIVE",
                null, "云同步首次发现：" + write.name()));
    }

    public void updateAsset(AssetWrite write) {
        AssetSnapshot before = snapshot(write.resourceUid()).orElse(null);
        jdbc.update("""
                UPDATE asset_resource
                SET name=?, status='ACTIVE', status_reason=NULL, environment=?, business=?, owner=?,
                    last_sync_run_id=?, collected_at=?, last_seen_at=?, tags_json=?, metadata_json=?, updated_at=?
                WHERE resource_uid=?
                """,
                write.name(), write.environment(), write.business(), write.owner(), write.lastSyncRunId(),
                timestamp(write.collectedAt()), timestamp(write.collectedAt()),
                write.tagsJson(), write.metadataJson(), timestamp(write.collectedAt()), write.resourceUid());
        if (before == null) {
            return;
        }
        // 记录"同步看到的实际变化"，而不是每次同步都写一条
        recordIfChanged(write.resourceUid(), "status", before.status(), "ACTIVE");
        recordIfChanged(write.resourceUid(), "name", before.name(), write.name());
        recordIfChanged(write.resourceUid(), "environment", before.environment(), write.environment());
        recordIfChanged(write.resourceUid(), "business", before.business(), write.business());
        recordIfChanged(write.resourceUid(), "owner", before.owner(), write.owner());
    }

    /**
     * 只有"全量分页成功取完"的同步才调用本方法：
     * 本次同步未命中的 ACTIVE 资源转为 MISSING；DELETED 不覆盖。
     * 用 last_sync_run_id 精确记账，避免同步开始时间与资源采集时间同秒导致的误判。
     */
    public int markMissing(long accountId, long syncRunId) {
        List<String> affected = jdbc.queryForList("""
                SELECT resource_uid FROM asset_resource
                WHERE source_account_id=? AND status='ACTIVE'
                  AND (last_sync_run_id IS NULL OR last_sync_run_id <> ?)
                """, String.class, accountId, syncRunId);
        int marked = jdbc.update("""
                UPDATE asset_resource
                SET status='MISSING', status_reason=?, updated_at=?
                WHERE source_account_id=? AND status='ACTIVE'
                  AND (last_sync_run_id IS NULL OR last_sync_run_id <> ?)
                """,
                "最近一次成功全量同步（run " + syncRunId + "）未返回该资源",
                timestamp(LocalDateTime.now()), accountId, syncRunId);
        for (String uid : affected) {
            appendChange(new ChangeWrite(uid, "STATUS_CHANGED", "status", "ACTIVE", "MISSING",
                    null, "全量同步未返回该资源（run " + syncRunId + "）"));
        }
        return marked;
    }

    public boolean updateAssetStatus(String resourceUid, String status, String reason) {
        return updateAssetStatus(resourceUid, status, reason, null);
    }

    public boolean updateAssetStatus(String resourceUid, String status, String reason, String actor) {
        Optional<AssetSnapshot> before = snapshot(resourceUid);
        int updated = jdbc.update("""
                UPDATE asset_resource SET status=?, status_reason=?, updated_at=? WHERE resource_uid=?
                """, status, reason, timestamp(LocalDateTime.now()), resourceUid);
        if (updated > 0 && before.isPresent() && !status.equals(before.get().status())) {
            appendChange(new ChangeWrite(resourceUid, "STATUS_CHANGED", "status",
                    before.get().status(), status, actor, reason));
        }
        return updated > 0;
    }

    /** 人工确认：补充确认人与说明，不覆盖采集事实。 */
    public boolean confirmAsset(String resourceUid, String status, String actor, String note) {
        return jdbc.update("""
                UPDATE asset_resource
                SET status=?, status_reason=?, confirmed_at=?, confirmed_by=?, confirmation_note=?, updated_at=?
                WHERE resource_uid=?
                """, status, note, timestamp(LocalDateTime.now()), actor, note,
                timestamp(LocalDateTime.now()), resourceUid) > 0;
    }

    /** 人工确认时补齐归属信息：只覆盖显式给出的字段。 */
    public void updateAttribution(String resourceUid, String environment, String business, String owner) {
        jdbc.update("""
                UPDATE asset_resource
                SET environment=COALESCE(?, environment), business=COALESCE(?, business),
                    owner=COALESCE(?, owner), updated_at=?
                WHERE resource_uid=?
                """, environment, business, owner, timestamp(LocalDateTime.now()), resourceUid);
    }

    // ===================== 变更历史 =====================

    public void appendChange(ChangeWrite write) {
        jdbc.update("""
                INSERT INTO asset_change_event
                    (resource_uid, change_type, field_name, old_value, new_value, actor, note, changed_at)
                VALUES (?,?,?,?,?,?,?,?)
                """, write.resourceUid(), write.changeType(), write.fieldName(), write.oldValue(),
                write.newValue(), write.actor(), write.note(), timestamp(LocalDateTime.now()));
    }

    public List<ChangeRow> listChanges(String resourceUid, int limit) {
        return jdbc.query("""
                SELECT id, resource_uid, change_type, field_name, old_value, new_value, actor, note, changed_at
                FROM asset_change_event WHERE resource_uid=? ORDER BY changed_at DESC, id DESC LIMIT ?
                """, changeMapper(), resourceUid, Math.min(Math.max(1, limit), 200));
    }

    private void recordIfChanged(String resourceUid, String field, String before, String after) {
        if (before == null ? after == null : before.equals(after)) {
            return;
        }
        appendChange(new ChangeWrite(resourceUid, "UPDATED", field, before, after, null, "云同步更新"));
    }

    private Optional<AssetSnapshot> snapshot(String resourceUid) {
        List<AssetSnapshot> rows = jdbc.query("""
                SELECT resource_uid, name, status, environment, business, owner FROM asset_resource
                WHERE resource_uid=?
                """, (rs, rowNum) -> new AssetSnapshot(rs.getString("resource_uid"), rs.getString("name"),
                rs.getString("status"), rs.getString("environment"), rs.getString("business"),
                rs.getString("owner")), resourceUid);
        return rows.stream().findFirst();
    }

    private RowMapper<ChangeRow> changeMapper() {
        return (rs, rowNum) -> new ChangeRow(
                rs.getLong("id"), rs.getString("resource_uid"), rs.getString("change_type"),
                rs.getString("field_name"), rs.getString("old_value"), rs.getString("new_value"),
                rs.getString("actor"), rs.getString("note"), toTime(rs, "changed_at"));
    }

    public record ChangeWrite(
            String resourceUid,
            String changeType,
            String fieldName,
            String oldValue,
            String newValue,
            String actor,
            String note
    ) {}

    public record ChangeRow(
            long id,
            String resourceUid,
            String changeType,
            String fieldName,
            String oldValue,
            String newValue,
            String actor,
            String note,
            LocalDateTime changedAt
    ) {}

    private record AssetSnapshot(
            String resourceUid,
            String name,
            String status,
            String environment,
            String business,
            String owner
    ) {}

    /** 手工登记资产：没有云账号，可见范围由登记人/所属团队决定。 */
    public void insertManualAsset(ManualAssetWrite write) {
        LocalDateTime now = LocalDateTime.now();
        jdbc.update("""
                INSERT INTO asset_resource
                    (resource_uid, provider, provider_account_id, region, resource_type, provider_resource_id,
                     name, status, status_reason, environment, business, owner, source, source_account_id,
                     last_sync_run_id, collected_at, first_seen_at, last_seen_at, tags_json, metadata_json,
                     owner_user_id, team_id, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                write.resourceUid(), "manual", "manual", write.region(), write.resourceType(),
                write.providerResourceId(), write.name(), "ACTIVE", null, write.environment(), write.business(),
                write.owner(), "MANUAL", null, null, timestamp(now), timestamp(now), timestamp(now),
                write.tagsJson(), write.metadataJson(), write.ownerUserId(), write.teamId(),
                timestamp(now), timestamp(now));
    }

    public Optional<AssetRow> findAssetByUid(String resourceUid) {
        List<AssetRow> rows = jdbc.query(
                "SELECT * FROM asset_resource WHERE resource_uid=?", assetMapper(), resourceUid);
        return rows.stream().findFirst();
    }

    public List<AssetRow> queryAssets(AssetQuery query) {
        List<Object> args = new ArrayList<>();
        String sql = scopedAssetSelect(args, query) + " ORDER BY r.last_seen_at DESC, r.id DESC LIMIT ? OFFSET ?";
        args.add(query.size());
        args.add((query.page() - 1) * query.size());
        return jdbc.query(sql, assetMapper(), args.toArray());
    }

    public long countAssets(AssetQuery query) {
        List<Object> args = new ArrayList<>();
        String sql = "SELECT COUNT(1) FROM asset_resource r LEFT JOIN cloud_account a ON a.id=r.source_account_id"
                + scopedAssetWhere(args, query);
        Long count = jdbc.queryForObject(sql, Long.class, args.toArray());
        return count == null ? 0 : count;
    }

    public List<AssetRow> assetsByBusiness(long userId, String business, String environment, LocalDateTime staleBefore) {
        AssetQuery query = new AssetQuery(business, environment, null, null, null, 1, 1000)
                .withUser(userId, staleBefore);
        List<Object> args = new ArrayList<>();
        String sql = scopedAssetSelect(args, query) + " ORDER BY r.resource_type, r.name LIMIT 1000";
        return jdbc.query(sql, assetMapper(), args.toArray());
    }

    private String scopedAssetSelect(List<Object> args, AssetQuery query) {
        return "SELECT r.* FROM asset_resource r LEFT JOIN cloud_account a ON a.id=r.source_account_id"
                + scopedAssetWhere(args, query);
    }

    /**
     * 可见范围：云资产按云账号归属，手工资产按登记人/归属团队。
     * 手工资产的 source_account_id 为空，因此必须是 LEFT JOIN。
     */
    private String scopedAssetWhere(List<Object> args, AssetQuery query) {
        StringBuilder where = new StringBuilder("""
                 WHERE (a.owner_user_id=? OR a.team_id IN (SELECT team_id FROM team_member WHERE user_id=?)
                        OR r.owner_user_id=? OR r.team_id IN (SELECT team_id FROM team_member WHERE user_id=?))
                """);
        args.add(query.userId());
        args.add(query.userId());
        args.add(query.userId());
        args.add(query.userId());
        if (query.business() != null && !query.business().isBlank()) {
            where.append(" AND r.business=?");
            args.add(query.business());
        }
        if (query.environment() != null && !query.environment().isBlank()) {
            where.append(" AND r.environment=?");
            args.add(query.environment());
        }
        if (query.resourceType() != null && !query.resourceType().isBlank()) {
            where.append(" AND r.resource_type=?");
            args.add(query.resourceType());
        }
        if ("STALE".equals(query.status())) {
            where.append(" AND r.status='ACTIVE' AND r.collected_at < ?");
            args.add(timestamp(query.staleBefore()));
        } else if ("ACTIVE".equals(query.status())) {
            where.append(" AND r.status='ACTIVE' AND r.collected_at >= ?");
            args.add(timestamp(query.staleBefore()));
        } else if (query.status() != null && !query.status().isBlank()) {
            where.append(" AND r.status=?");
            args.add(query.status());
        }
        if (query.keyword() != null && !query.keyword().isBlank()) {
            where.append(" AND (r.name LIKE ? OR r.provider_resource_id LIKE ?)");
            String like = "%" + query.keyword().trim() + "%";
            args.add(like);
            args.add(like);
        }
        return where.toString();
    }

    // ===================== 关系 =====================

    public void upsertRelation(String fromUid, String toUid, String relationType, String source, String evidence) {
        LocalDateTime now = LocalDateTime.now();
        int updated = jdbc.update("""
                UPDATE asset_relation SET source=?, evidence=?, updated_at=?
                WHERE from_uid=? AND to_uid=? AND relation_type=?
                """, source, evidence, timestamp(now), fromUid, toUid, relationType);
        boolean created = false;
        if (updated == 0) {
            jdbc.update("""
                    INSERT INTO asset_relation (from_uid, to_uid, relation_type, source, evidence, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?)
                    """, fromUid, toUid, relationType, source, evidence, timestamp(now), timestamp(now));
            created = true;
        }
        if (created) {
            appendChange(new ChangeWrite(fromUid, "RELATION_DECLARED", relationType, null, toUid,
                    null, evidence));
        }
    }

    public List<RelationRow> relationsAmong(List<String> uids) {
        if (uids.isEmpty()) {
            return List.of();
        }
        String placeholders = String.join(",", java.util.Collections.nCopies(uids.size(), "?"));
        List<Object> args = new ArrayList<>(uids);
        args.addAll(uids);
        return jdbc.query("SELECT * FROM asset_relation WHERE from_uid IN (" + placeholders + ")"
                        + " OR to_uid IN (" + placeholders + ") ORDER BY relation_type, id",
                (result, row) -> new RelationRow(
                        result.getLong("id"),
                        result.getString("from_uid"),
                        result.getString("to_uid"),
                        result.getString("relation_type"),
                        result.getString("source"),
                        result.getString("evidence"),
                        toTime(result, "updated_at")),
                args.toArray());
    }

    public List<CloudAccount> incompleteAccounts(long userId, String business) {
        List<Object> args = new ArrayList<>();
        args.add(userId);
        args.add(userId);
        String businessFilter = "";
        if (business != null && !business.isBlank()) {
            businessFilter = " AND EXISTS (SELECT 1 FROM asset_resource r WHERE r.source_account_id=a.id AND r.business=?)";
            args.add(business);
        }
        return jdbc.query("""
                SELECT * FROM cloud_account a
                WHERE (a.owner_user_id=? OR a.team_id IN (SELECT team_id FROM team_member WHERE user_id=?))
                  AND (a.last_sync_status IS NULL OR a.last_sync_status <> 'SUCCEEDED')
                """ + businessFilter + " ORDER BY a.id DESC",
                accountMapper(), args.toArray());
    }

    // ===================== 映射 =====================

    private RowMapper<CloudAccount> accountMapper() {
        return (result, row) -> new CloudAccount(
                result.getLong("id"),
                CloudProvider.fromWireName(result.getString("provider")),
                result.getString("account_id"),
                result.getString("display_name"),
                result.getString("region"),
                result.getString("endpoint"),
                result.getString("project_id"),
                result.getObject("team_id", Long.class),
                result.getLong("owner_user_id"),
                result.getString("credential_ref"),
                result.getString("credential_scope"),
                result.getBoolean("enabled"),
                toTime(result, "last_sync_at"),
                result.getString("last_sync_status"),
                toTime(result, "created_at"));
    }

    private RowMapper<AssetRow> assetMapper() {
        return (result, row) -> new AssetRow(
                result.getLong("id"),
                result.getString("resource_uid"),
                result.getString("provider"),
                result.getString("provider_account_id"),
                result.getString("region"),
                result.getString("resource_type"),
                result.getString("provider_resource_id"),
                result.getString("name"),
                result.getString("status"),
                result.getString("status_reason"),
                result.getString("environment"),
                result.getString("business"),
                result.getString("owner"),
                result.getString("source"),
                nullableLong(result, "source_account_id"),
                toTime(result, "collected_at"),
                toTime(result, "first_seen_at"),
                toTime(result, "last_seen_at"),
                result.getString("tags_json"),
                result.getString("metadata_json"),
                nullableLong(result, "owner_user_id"),
                nullableLong(result, "team_id"));
    }

    private static Long nullableLong(ResultSet result, String column) throws SQLException {
        long value = result.getLong(column);
        return result.wasNull() ? null : value;
    }

    private static LocalDateTime toTime(ResultSet result, String column) throws SQLException {
        java.sql.Timestamp value = result.getTimestamp(column);
        return value == null ? null : value.toLocalDateTime();
    }

    private static java.sql.Timestamp timestamp(LocalDateTime value) {
        return value == null ? null : java.sql.Timestamp.valueOf(value);
    }

    // ===================== 行记录 =====================

    public record SyncRunRecord(
            long id,
            long accountId,
            Long actorUserId,
            String status,
            LocalDateTime startedAt,
            LocalDateTime endedAt,
            int pages,
            int discovered,
            int created,
            int updated,
            int markedMissing,
            boolean permissionDenied,
            String errorCode,
            String errorMessage
    ) {}

    public record AssetWrite(
            String resourceUid,
            String provider,
            String providerAccountId,
            String region,
            String resourceType,
            String providerResourceId,
            String name,
            String environment,
            String business,
            String owner,
            long sourceAccountId,
            long lastSyncRunId,
            LocalDateTime collectedAt,
            String tagsJson,
            String metadataJson
    ) {}

    public record ManualAssetWrite(
            String resourceUid,
            String region,
            String resourceType,
            String providerResourceId,
            String name,
            String environment,
            String business,
            String owner,
            String tagsJson,
            String metadataJson,
            long ownerUserId,
            Long teamId
    ) {}

    public record AssetRow(
            long id,
            String resourceUid,
            String provider,
            String providerAccountId,
            String region,
            String resourceType,
            String providerResourceId,
            String name,
            String status,
            String statusReason,
            String environment,
            String business,
            String owner,
            String source,
            Long sourceAccountId,
            LocalDateTime collectedAt,
            LocalDateTime firstSeenAt,
            LocalDateTime lastSeenAt,
            String tagsJson,
            String metadataJson,
            Long ownerUserId,
            Long teamId
    ) {}

    public record RelationRow(
            long id,
            String fromUid,
            String toUid,
            String relationType,
            String source,
            String evidence,
            LocalDateTime updatedAt
    ) {}

    public record AssetQuery(
            String business,
            String environment,
            String resourceType,
            String status,
            String keyword,
            long userId,
            int page,
            int size,
            LocalDateTime staleBefore
    ) {
        public AssetQuery(String business, String environment, String resourceType, String status,
                          String keyword, int page, int size) {
            this(business, environment, resourceType, status, keyword, 0, page, size, LocalDateTime.now());
        }

        AssetQuery withUser(long userId, LocalDateTime staleBefore) {
            return new AssetQuery(business, environment, resourceType, status, keyword, userId, page, size, staleBefore);
        }
    }
}
