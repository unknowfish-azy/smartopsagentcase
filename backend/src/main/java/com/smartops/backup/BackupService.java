package com.smartops.backup;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;

import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * OPS-13：备份恢复集合、制品清单校验、异机副本、保留期与隔离恢复演练。
 *
 * <p>只接受可复核的事实：sha256 / 字节数 / 条目数来自备份制品本身；
 * RPO 与 RTO 由演练时间戳计算，不接受调用方自报；演练未验证时如实返回 UNVERIFIED/FAILED。</p>
 */
@Service
public class BackupService {

    /** 恢复集合必须覆盖的五类组件；缺任何一类都在状态里标 INCOMPLETE。 */
    public static final List<String> REQUIRED_COMPONENTS =
            List.of("DATABASE", "ATTACHMENTS", "KNOWLEDGE_MANIFEST", "AUDIT", "KEYS");

    private static final Pattern SHA256 = Pattern.compile("[0-9a-fA-F]{64}");
    private static final ObjectMapper JSON = new ObjectMapper();

    private final JdbcTemplate jdbc;

    public BackupService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /* ── 恢复集合 ─────────────────────────────────────────────────────── */

    public SetView createSet(long userId, String name, String environment, List<String> components,
                             Integer retentionDays, Boolean offsiteRequired) {
        if (!hasText(name)) throw new BusinessException(400, "BACKUP_SET_NAME_REQUIRED: 缺少恢复集合名称");
        if (!hasText(environment)) throw new BusinessException(400, "BACKUP_ENVIRONMENT_REQUIRED: 缺少环境");
        List<String> normalized = normalizeComponents(components);
        int retention = retentionDays == null ? 14 : retentionDays;
        if (retention < 1 || retention > 3650) {
            throw new BusinessException(400, "BACKUP_RETENTION_INVALID: 保留天数需在 1..3650");
        }
        boolean offsite = offsiteRequired == null || offsiteRequired;
        Integer exists = jdbc.query("SELECT id FROM backup_recovery_set WHERE user_id=? AND name=?",
                rs -> rs.next() ? rs.getInt(1) : null, userId, name.trim());
        if (exists != null) {
            throw new BusinessException(409, "BACKUP_SET_EXISTS: 同名恢复集合已存在");
        }
        jdbc.update("""
                INSERT INTO backup_recovery_set (user_id,name,environment,components,retention_days,offsite_required)
                VALUES (?,?,?,?,?,?)
                """, userId, name.trim(), environment.trim(), String.join(",", normalized),
                retention, offsite ? 1 : 0);
        long id = jdbc.queryForObject("SELECT id FROM backup_recovery_set WHERE user_id=? AND name=?",
                Long.class, userId, name.trim());
        return setView(requireSet(userId, id));
    }

    public List<SetView> listSets(long userId) {
        return jdbc.query("SELECT * FROM backup_recovery_set WHERE user_id=? ORDER BY id DESC",
                SET_MAPPER, userId).stream().map(this::setView).toList();
    }

    /* ── 制品清单 ─────────────────────────────────────────────────────── */

    /**
     * 导入备份脚本生成的 manifest：只登记元数据与摘要，拒绝越界组件与非法 hash。
     */
    public List<ArtifactView> ingestManifest(long userId, long setId, String manifestJson) {
        SetRow set = requireSet(userId, setId);
        if (!hasText(manifestJson)) {
            throw new BusinessException(400, "BACKUP_MANIFEST_EMPTY: 清单内容为空");
        }
        JsonNode root;
        try {
            root = JSON.readTree(manifestJson);
        } catch (Exception malformed) {
            throw new BusinessException(400, "BACKUP_MANIFEST_MALFORMED: 不是合法 JSON");
        }
        if (root == null || !root.isObject() || !"smartops-backup/v1".equals(text(root, "schema"))) {
            throw new BusinessException(400, "BACKUP_MANIFEST_SCHEMA_UNSUPPORTED: 需要 smartops-backup/v1");
        }
        String setName = text(root, "set");
        if (setName != null && !setName.equals(set.name())) {
            throw new BusinessException(400, "BACKUP_MANIFEST_SET_MISMATCH: 清单属于 " + setName);
        }
        Instant capturedAt = instant(text(root, "capturedAt"));
        if (capturedAt == null) {
            throw new BusinessException(400, "BACKUP_MANIFEST_CAPTURED_AT_REQUIRED: 缺少 capturedAt");
        }
        JsonNode artifacts = root.get("artifacts");
        if (artifacts == null || !artifacts.isArray() || artifacts.isEmpty()) {
            throw new BusinessException(400, "BACKUP_MANIFEST_ARTIFACTS_REQUIRED: 至少需要一个制品");
        }
        Set<String> setComponents = new LinkedHashSet<>(set.components());
        Set<String> seen = new LinkedHashSet<>();
        for (JsonNode artifact : artifacts) {
            String artifactId = text(artifact, "artifactId");
            String component = upper(text(artifact, "component"));
            String sha256 = text(artifact, "sha256");
            if (!hasText(artifactId)) {
                throw new BusinessException(400, "BACKUP_ARTIFACT_ID_REQUIRED: 制品缺少 artifactId");
            }
            if (!seen.add(artifactId)) {
                throw new BusinessException(400, "BACKUP_ARTIFACT_DUPLICATE: 制品 ID 重复 " + artifactId);
            }
            if (component == null || !REQUIRED_COMPONENTS.contains(component)) {
                throw new BusinessException(400, "BACKUP_COMPONENT_UNKNOWN: " + component);
            }
            if (!setComponents.contains(component)) {
                throw new BusinessException(400, "BACKUP_COMPONENT_NOT_IN_SET: 集合未包含 " + component);
            }
            if (sha256 == null || !SHA256.matcher(sha256).matches()) {
                throw new BusinessException(400, "BACKUP_SHA256_INVALID: " + artifactId);
            }
            long bytes = artifact.path("bytes").asLong(-1);
            long itemCount = artifact.path("itemCount").asLong(-1);
            if (bytes < 0 || itemCount < 0) {
                throw new BusinessException(400, "BACKUP_ARTIFACT_SIZE_INVALID: " + artifactId);
            }
            Instant artifactCapturedAt = instant(text(artifact, "capturedAt"));
            if (artifactCapturedAt == null) artifactCapturedAt = capturedAt;
            Instant retentionUntil = artifactCapturedAt.plus(Duration.ofDays(set.retentionDays()));
            jdbc.update("DELETE FROM backup_artifact_record WHERE set_id=? AND artifact_id=?", setId, artifactId);
            jdbc.update("""
                    INSERT INTO backup_artifact_record
                        (set_id,artifact_id,component,source_uri,sha256,bytes,item_count,captured_at,retention_until)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """, setId, artifactId.trim(), component, text(artifact, "sourceUri"),
                    sha256.toLowerCase(Locale.ROOT), bytes, itemCount,
                    Timestamp.from(artifactCapturedAt), Timestamp.from(retentionUntil));
        }
        return artifactsOf(setId);
    }

    /* ── 校验 / 异机副本 ─────────────────────────────────────────────── */

    public ArtifactView verifyArtifact(long userId, long setId, String artifactId, String actualSha256,
                                       Long actualItemCount) {
        requireSet(userId, setId);
        ArtifactRow artifact = requireArtifact(setId, artifactId);
        if (!hasText(actualSha256) || !SHA256.matcher(actualSha256.trim()).matches()) {
            throw new BusinessException(400, "BACKUP_HASH_INVALID: 需要 64 位十六进制 sha256");
        }
        String actual = actualSha256.trim().toLowerCase(Locale.ROOT);
        boolean hashMatch = actual.equals(artifact.sha256());
        boolean countMatch = actualItemCount == null || actualItemCount == artifact.itemCount();
        boolean verified = hashMatch && countMatch;
        String status = verified ? "VERIFIED" : "MISMATCH";
        String detail = verified
                ? "sha256 与条目数一致"
                : (hashMatch ? "条目数不一致：期望 " + artifact.itemCount() + "，实际 " + actualItemCount
                : "sha256 不一致：期望 " + artifact.sha256() + "，实际 " + actual);
        jdbc.update("""
                UPDATE backup_artifact_record
                   SET verification_status=?,verified_at=?,verification_detail=?
                 WHERE set_id=? AND artifact_id=?
                """, status, verified ? Timestamp.from(Instant.now()) : null,
                detail, setId, artifact.artifactId());
        return artifactView(requireArtifact(setId, artifactId));
    }

    public ArtifactView recordOffsite(long userId, long setId, String artifactId, String location, boolean verified) {
        requireSet(userId, setId);
        ArtifactRow artifact = requireArtifact(setId, artifactId);
        if (!hasText(location)) {
            throw new BusinessException(400, "BACKUP_OFFSITE_LOCATION_REQUIRED: 缺少异机副本位置");
        }
        jdbc.update("""
                UPDATE backup_artifact_record SET offsite_location=?,offsite_verified_at=?
                 WHERE set_id=? AND artifact_id=?
                """, location.trim(), verified ? Timestamp.from(Instant.now()) : null,
                setId, artifact.artifactId());
        return artifactView(requireArtifact(setId, artifactId));
    }

    /* ── 隔离恢复演练 ─────────────────────────────────────────────────── */

    /**
     * 记录一次隔离恢复演练：数量、hash、引用关系、关键查询四项都通过才记 VERIFIED。
     */
    public DrillView recordDrill(long userId, long setId, DrillRequest request) {
        SetRow set = requireSet(userId, setId);
        if (request == null) throw new BusinessException(400, "BACKUP_DRILL_REQUIRED: 缺少演练内容");
        if (!"ISOLATED_RESTORE".equals(upper(request.mode()))) {
            throw new BusinessException(400, "BACKUP_DRILL_MODE_UNSUPPORTED: 只接受 ISOLATED_RESTORE");
        }
        Instant startedAt = request.startedAt();
        Instant finishedAt = request.finishedAt();
        if (startedAt == null || finishedAt == null) {
            throw new BusinessException(400, "BACKUP_DRILL_TIME_REQUIRED: 缺少开始或结束时间");
        }
        if (!finishedAt.isAfter(startedAt)) {
            throw new BusinessException(400, "BACKUP_DRILL_TIME_INVALID: 结束时间必须晚于开始时间");
        }
        List<String> missing = missingComponents(set);
        List<ArtifactRow> artifacts = artifactRows(setId);
        List<String> missingArtifacts = set.components().stream()
                .filter(component -> artifacts.stream().noneMatch(artifact -> component.equals(artifact.component())))
                .toList();
        Instant baseline = artifacts.stream().map(ArtifactRow::capturedAt)
                .max(Instant::compareTo).orElse(null);
        Long rpo = baseline == null ? null : Math.max(0, Duration.between(baseline, startedAt).getSeconds());
        long rto = Duration.between(startedAt, finishedAt).getSeconds();

        String reference = upper(request.referenceCheck());
        String keyQuery = upper(request.keyQueryCheck());
        boolean checksPassed = request.restoredCount() == request.expectedCount()
                && request.restoredCount() > 0
                && request.hashVerified()
                && "PASS".equals(reference)
                && "PASS".equals(keyQuery);
        String result;
        String detail;
        if (artifacts.isEmpty() || !missing.isEmpty() || !missingArtifacts.isEmpty()) {
            result = "UNVERIFIED";
            detail = artifacts.isEmpty()
                    ? "恢复集合没有任何制品，不能判定可恢复"
                    : "恢复集合缺少组件制品：" + String.join(",", missing.isEmpty() ? missingArtifacts : missing);
        } else if (checksPassed) {
            result = "VERIFIED";
            detail = "数量/hash/引用关系/关键查询全部通过";
        } else {
            result = "FAILED";
            detail = "数量 " + request.restoredCount() + "/" + request.expectedCount()
                    + "，hash=" + request.hashVerified()
                    + "，引用=" + reference + "，关键查询=" + keyQuery;
        }
        jdbc.update("""
                INSERT INTO backup_drill_record
                    (set_id,mode,started_at,finished_at,baseline_captured_at,rpo_seconds,rto_seconds,
                     expected_count,restored_count,hash_verified,reference_check,key_query_check,result,detail_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, setId, "ISOLATED_RESTORE", Timestamp.from(startedAt), Timestamp.from(finishedAt),
                baseline == null ? null : Timestamp.from(baseline), rpo, rto,
                request.expectedCount(), request.restoredCount(), request.hashVerified() ? 1 : 0,
                reference, keyQuery, result, detail);
        long id = jdbc.queryForObject("SELECT MAX(id) FROM backup_drill_record WHERE set_id=?",
                Long.class, setId);
        return drillView(jdbc.queryForObject("SELECT * FROM backup_drill_record WHERE id=?",
                DRILL_MAPPER, id));
    }

    /* ── 状态 ─────────────────────────────────────────────────────────── */

    public StatusView status(long userId, long setId) {
        SetRow set = requireSet(userId, setId);
        List<ArtifactRow> artifacts = artifactRows(setId);
        List<String> missing = missingComponents(set);
        List<ArtifactRow> artifactComponents = artifacts;
        List<String> missingArtifacts = new ArrayList<>();
        for (String component : set.components()) {
            if (artifactComponents.stream().noneMatch(artifact -> component.equals(artifact.component()))) {
                missingArtifacts.add(component);
            }
        }
        List<String> unverified = artifacts.stream()
                .filter(artifact -> !"VERIFIED".equals(artifact.verificationStatus()))
                .map(ArtifactRow::artifactId).toList();
        List<String> unoffsite = set.offsiteRequired() ? artifacts.stream()
                .filter(artifact -> artifact.offsiteVerifiedAt() == null)
                .map(ArtifactRow::artifactId).toList() : List.of();
        Instant now = Instant.now();
        List<String> expired = artifacts.stream()
                .filter(artifact -> artifact.retentionUntil() != null && artifact.retentionUntil().isBefore(now))
                .map(ArtifactRow::artifactId).toList();
        DrillRow lastDrill = jdbc.query("SELECT * FROM backup_drill_record WHERE set_id=? ORDER BY id DESC LIMIT 1",
                rs -> rs.next() ? DRILL_MAPPER.mapRow(rs, 0) : null, setId);
        return new StatusView(setView(set), artifacts.stream().map(this::artifactView).toList(),
                missing, missingArtifacts, unverified, unoffsite, expired,
                lastDrill == null ? null : drillView(lastDrill));
    }

    /* ── 内部 ─────────────────────────────────────────────────────────── */

    private List<String> missingComponents(SetRow set) {
        List<String> missing = new ArrayList<>();
        for (String required : REQUIRED_COMPONENTS) {
            if (!set.components().contains(required)) missing.add(required);
        }
        return missing;
    }

    private List<ArtifactRow> artifactRows(long setId) {
        return jdbc.query("SELECT * FROM backup_artifact_record WHERE set_id=? ORDER BY component,artifact_id",
                ARTIFACT_MAPPER, setId);
    }

    private List<ArtifactView> artifactsOf(long setId) {
        return artifactRows(setId).stream().map(this::artifactView).toList();
    }

    private SetRow requireSet(long userId, long setId) {
        SetRow set = jdbc.query("SELECT * FROM backup_recovery_set WHERE id=?", rs ->
                rs.next() ? SET_MAPPER.mapRow(rs, 0) : null, setId);
        if (set == null || set.userId() != userId) {
            throw new BusinessException(404, "BACKUP_SET_NOT_FOUND: 恢复集合不存在");
        }
        return set;
    }

    private ArtifactRow requireArtifact(long setId, String artifactId) {
        if (!hasText(artifactId)) {
            throw new BusinessException(400, "BACKUP_ARTIFACT_ID_REQUIRED: 缺少制品 ID");
        }
        ArtifactRow artifact = jdbc.query("""
                SELECT * FROM backup_artifact_record WHERE set_id=? AND artifact_id=?
                """, rs -> rs.next() ? ARTIFACT_MAPPER.mapRow(rs, 0) : null, setId, artifactId.trim());
        if (artifact == null) {
            throw new BusinessException(404, "BACKUP_ARTIFACT_NOT_FOUND: 制品不存在 " + artifactId);
        }
        return artifact;
    }

    private SetView setView(SetRow set) {
        List<String> missing = missingComponents(set);
        return new SetView(set.id(), set.name(), set.environment(), set.components(), set.retentionDays(),
                set.offsiteRequired(), missing, missing.isEmpty(), set.createdAt());
    }

    private ArtifactView artifactView(ArtifactRow artifact) {
        boolean expired = artifact.retentionUntil() != null && artifact.retentionUntil().isBefore(Instant.now());
        return new ArtifactView(artifact.id(), artifact.artifactId(), artifact.component(), artifact.sourceUri(),
                artifact.sha256(), artifact.bytes(), artifact.itemCount(), artifact.capturedAt(),
                artifact.retentionUntil(), expired, artifact.offsiteLocation(), artifact.offsiteVerifiedAt(),
                artifact.verificationStatus(), artifact.verifiedAt(), artifact.verificationDetail());
    }

    private DrillView drillView(DrillRow drill) {
        return new DrillView(drill.id(), drill.mode(), drill.startedAt(), drill.finishedAt(),
                drill.baselineCapturedAt(), drill.rpoSeconds(), drill.rtoSeconds(), drill.expectedCount(),
                drill.restoredCount(), drill.hashVerified(), drill.referenceCheck(), drill.keyQueryCheck(),
                drill.result(), drill.detail());
    }

    private static List<String> normalizeComponents(List<String> components) {
        if (components == null || components.isEmpty()) {
            return new ArrayList<>(REQUIRED_COMPONENTS);
        }
        LinkedHashSet<String> normalized = new LinkedHashSet<>();
        for (String component : components) {
            String upper = upper(component);
            if (upper == null || !REQUIRED_COMPONENTS.contains(upper)) {
                throw new BusinessException(400, "BACKUP_COMPONENT_UNKNOWN: " + component);
            }
            normalized.add(upper);
        }
        return new ArrayList<>(normalized);
    }

    private static boolean hasText(String value) { return value != null && !value.isBlank(); }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        return value == null || value.isNull() ? null : value.asText();
    }

    private static String upper(String value) {
        return value == null || value.isBlank() ? null : value.trim().toUpperCase(Locale.ROOT);
    }

    private static Instant instant(String value) {
        if (!hasText(value)) return null;
        try {
            return Instant.parse(value.trim());
        } catch (Exception invalid) {
            throw new BusinessException(400, "BACKUP_TIME_INVALID: " + value);
        }
    }

    private static Instant instant(ResultSet rs, String column) throws java.sql.SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    private static Long nullableLong(ResultSet rs, String column) throws java.sql.SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }

    /* ── 行模型 ───────────────────────────────────────────────────────── */

    private record SetRow(long id, long userId, String name, String environment, List<String> components,
                          int retentionDays, boolean offsiteRequired, Instant createdAt) {}

    private record ArtifactRow(long id, long setId, String artifactId, String component, String sourceUri,
                               String sha256, long bytes, long itemCount, Instant capturedAt,
                               Instant retentionUntil, String offsiteLocation, Instant offsiteVerifiedAt,
                               String verificationStatus, Instant verifiedAt, String verificationDetail) {}

    private record DrillRow(long id, String mode, Instant startedAt, Instant finishedAt,
                            Instant baselineCapturedAt, Long rpoSeconds, Long rtoSeconds,
                            long expectedCount, long restoredCount, boolean hashVerified,
                            String referenceCheck, String keyQueryCheck, String result, String detail) {}

    private static final RowMapper<SetRow> SET_MAPPER = (rs, rowNum) -> new SetRow(
            rs.getLong("id"), rs.getLong("user_id"), rs.getString("name"), rs.getString("environment"),
            splitComponents(rs.getString("components")), rs.getInt("retention_days"),
            rs.getInt("offsite_required") != 0, instant(rs, "created_at"));

    private static final RowMapper<ArtifactRow> ARTIFACT_MAPPER = (rs, rowNum) -> new ArtifactRow(
            rs.getLong("id"), rs.getLong("set_id"), rs.getString("artifact_id"), rs.getString("component"),
            rs.getString("source_uri"), rs.getString("sha256"), rs.getLong("bytes"), rs.getLong("item_count"),
            instant(rs, "captured_at"), instant(rs, "retention_until"), rs.getString("offsite_location"),
            instant(rs, "offsite_verified_at"), rs.getString("verification_status"), instant(rs, "verified_at"),
            rs.getString("verification_detail"));

    private static final RowMapper<DrillRow> DRILL_MAPPER = (rs, rowNum) -> new DrillRow(
            rs.getLong("id"), rs.getString("mode"), instant(rs, "started_at"), instant(rs, "finished_at"),
            instant(rs, "baseline_captured_at"), nullableLong(rs, "rpo_seconds"), nullableLong(rs, "rto_seconds"),
            rs.getLong("expected_count"), rs.getLong("restored_count"), rs.getInt("hash_verified") != 0,
            rs.getString("reference_check"), rs.getString("key_query_check"), rs.getString("result"),
            rs.getString("detail_json"));

    private static List<String> splitComponents(String value) {
        if (value == null || value.isBlank()) return List.of();
        return List.of(value.split(","));
    }

    /* ── 公开视图 ─────────────────────────────────────────────────────── */

    public record SetView(long id, String name, String environment, List<String> components, int retentionDays,
                          boolean offsiteRequired, List<String> missingComponents, boolean complete,
                          Instant createdAt) {}

    public record ArtifactView(long id, String artifactId, String component, String sourceUri, String sha256,
                               long bytes, long itemCount, Instant capturedAt, Instant retentionUntil,
                               boolean retentionExpired, String offsiteLocation, Instant offsiteVerifiedAt,
                               String verificationStatus, Instant verifiedAt, String verificationDetail) {}

    public record DrillView(long id, String mode, Instant startedAt, Instant finishedAt,
                            Instant baselineCapturedAt, Long rpoSeconds, Long rtoSeconds,
                            long expectedCount, long restoredCount, boolean hashVerified,
                            String referenceCheck, String keyQueryCheck, String result, String detail) {}

    public record StatusView(SetView set, List<ArtifactView> artifacts, List<String> missingComponents,
                             List<String> missingArtifacts, List<String> unverifiedArtifacts,
                             List<String> unoffsiteArtifacts, List<String> expiredArtifacts,
                             DrillView lastDrill) {}

    public record DrillRequest(String mode, Instant startedAt, Instant finishedAt,
                               long expectedCount, long restoredCount, boolean hashVerified,
                               String referenceCheck, String keyQueryCheck) {}
}
