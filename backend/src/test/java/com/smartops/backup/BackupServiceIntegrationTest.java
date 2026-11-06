package com.smartops.backup;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-13：恢复集合完整性、清单校验、异机副本、保留期与隔离恢复演练的真实 RPO/RTO。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:backup_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class BackupServiceIntegrationTest {

    private static final long OWNER = 111L;
    private static final String SET = "prod-core";
    private static final String ALL = "DATABASE,ATTACHMENTS,KNOWLEDGE_MANIFEST,AUDIT,KEYS";

    @Autowired JdbcTemplate jdbc;
    @Autowired BackupService backups;
    @Autowired BackupController controller;

    @BeforeEach
    void clean() {
        jdbc.update("DELETE FROM backup_drill_record");
        jdbc.update("DELETE FROM backup_artifact_record");
        jdbc.update("DELETE FROM backup_recovery_set");
    }

    @Test
    @DisplayName("恢复集合缺组件时标 INCOMPLETE，覆盖五类才完整")
    void recoverySetMustCoverAllComponents() {
        BackupService.SetView partial = backups.createSet(OWNER, "partial", "prod",
                List.of("DATABASE", "ATTACHMENTS"), 14, true);
        assertThat(partial.complete()).isFalse();
        assertThat(partial.missingComponents()).containsExactly("KNOWLEDGE_MANIFEST", "AUDIT", "KEYS");

        BackupService.SetView complete = backups.createSet(OWNER, SET, "prod", null, 14, true);
        assertThat(complete.complete()).isTrue();
        assertThat(complete.components()).containsExactly(
                "DATABASE", "ATTACHMENTS", "KNOWLEDGE_MANIFEST", "AUDIT", "KEYS");
        assertThatThrownBy(() -> backups.createSet(OWNER, SET, "prod", null, 14, true))
                .as("同名集合不允许静默覆盖")
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_SET_EXISTS");
        assertThatThrownBy(() -> backups.createSet(OWNER, "bad", "prod", List.of("SECRETS"), 14, true))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_COMPONENT_UNKNOWN");
    }

    @Test
    @DisplayName("清单只接受合法 hash/组件，并按采集时间计算保留期")
    void manifestIsValidatedAndRetentionIsComputed() {
        backups.createSet(OWNER, SET, "prod", null, 14, true);
        long setId = set(OWNER, SET).id();
        Instant capturedAt = Instant.parse("2026-11-01T01:00:00Z");

        List<BackupService.ArtifactView> artifacts = backups.ingestManifest(OWNER, setId,
                manifest(capturedAt, artifact("db.sql.gz", "DATABASE", "a".repeat(64), 1024, 42)));

        assertThat(artifacts).singleElement().satisfies(artifact -> {
            assertThat(artifact.component()).isEqualTo("DATABASE");
            assertThat(artifact.sha256()).isEqualTo("a".repeat(64));
            assertThat(artifact.itemCount()).isEqualTo(42);
            assertThat(artifact.retentionUntil()).isEqualTo(capturedAt.plus(Duration.ofDays(14)));
            assertThat(artifact.verificationStatus()).isEqualTo("UNVERIFIED");
        });

        assertThatThrownBy(() -> backups.ingestManifest(OWNER, setId,
                manifest(capturedAt, artifact("bad.sql", "SECRETS", "b".repeat(64), 1, 1))))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_COMPONENT_UNKNOWN");
        assertThatThrownBy(() -> backups.ingestManifest(OWNER, setId,
                manifest(capturedAt, artifact("bad.sql", "DATABASE", "not-a-hash", 1, 1))))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_SHA256_INVALID");
        assertThatThrownBy(() -> backups.ingestManifest(OWNER, setId, "{\"schema\":\"other\"}"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_MANIFEST_SCHEMA_UNSUPPORTED");
    }

    @Test
    @DisplayName("制品校验区分一致与不一致，不一致不写 verified_at")
    void artifactVerificationIsHonest() {
        backups.createSet(OWNER, SET, "prod", null, 14, true);
        long setId = set(OWNER, SET).id();
        backups.ingestManifest(OWNER, setId, manifest(Instant.now(),
                artifact("db.sql.gz", "DATABASE", "a".repeat(64), 1024, 42)));

        BackupService.ArtifactView verified = backups.verifyArtifact(OWNER, setId, "db.sql.gz", "a".repeat(64), 42L);
        assertThat(verified.verificationStatus()).isEqualTo("VERIFIED");
        assertThat(verified.verifiedAt()).isNotNull();

        BackupService.ArtifactView mismatch = backups.verifyArtifact(OWNER, setId, "db.sql.gz", "b".repeat(64), 42L);
        assertThat(mismatch.verificationStatus()).isEqualTo("MISMATCH");
        assertThat(mismatch.verifiedAt()).isNull();
        assertThat(mismatch.verificationDetail()).contains("sha256 不一致");

        BackupService.ArtifactView countMismatch = backups.verifyArtifact(OWNER, setId, "db.sql.gz", "a".repeat(64), 41L);
        assertThat(countMismatch.verificationStatus()).isEqualTo("MISMATCH");
        assertThat(countMismatch.verificationDetail()).contains("条目数不一致");

        assertThatThrownBy(() -> backups.verifyArtifact(OWNER, setId, "db.sql.gz", "xyz", 42L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_HASH_INVALID");
    }

    @Test
    @DisplayName("异机副本未验证时保留记录但不标已验证；状态中可见缺口")
    void offsiteCopyMustBeExplicitlyVerified() {
        backups.createSet(OWNER, SET, "prod", null, 14, true);
        long setId = set(OWNER, SET).id();
        backups.ingestManifest(OWNER, setId, manifest(Instant.now(),
                artifact("db.sql.gz", "DATABASE", "a".repeat(64), 1024, 42)));

        BackupService.ArtifactView pending = backups.recordOffsite(OWNER, setId, "db.sql.gz",
                "s3://offsite/prod/db.sql.gz", false);
        assertThat(pending.offsiteLocation()).isEqualTo("s3://offsite/prod/db.sql.gz");
        assertThat(pending.offsiteVerifiedAt()).isNull();
        assertThat(backups.status(OWNER, setId).unoffsiteArtifacts()).containsExactly("db.sql.gz");

        BackupService.ArtifactView verifiedCopy = backups.recordOffsite(OWNER, setId, "db.sql.gz",
                "s3://offsite/prod/db.sql.gz", true);
        assertThat(verifiedCopy.offsiteVerifiedAt()).isNotNull();
        assertThat(backups.status(OWNER, setId).unoffsiteArtifacts()).isEmpty();
    }

    @Test
    @DisplayName("演练按真实时间戳计算 RPO/RTO，四项检查全过才 VERIFIED")
    void drillComputesRpoRtoFromRealTimestamps() {
        backups.createSet(OWNER, SET, "prod", null, 14, true);
        long setId = set(OWNER, SET).id();
        Instant capturedAt = Instant.parse("2026-11-06T01:00:00Z");
        backups.ingestManifest(OWNER, setId, manifest(capturedAt,
                artifact("db.sql.gz", "DATABASE", "a".repeat(64), 1024, 42),
                artifact("uploads.tar.gz", "ATTACHMENTS", "b".repeat(64), 2048, 7),
                artifact("knowledge.json", "KNOWLEDGE_MANIFEST", "c".repeat(64), 512, 1),
                artifact("audit.jsonl.gz", "AUDIT", "d".repeat(64), 256, 3),
                artifact("keys.tar.gz", "KEYS", "e".repeat(64), 128, 1)));

        Instant startedAt = capturedAt.plus(Duration.ofMinutes(10));
        Instant finishedAt = startedAt.plus(Duration.ofMinutes(5));
        BackupService.DrillView verified = backups.recordDrill(OWNER, setId, new BackupService.DrillRequest(
                "ISOLATED_RESTORE", startedAt, finishedAt, 54, 54, true, "PASS", "PASS"));
        assertThat(verified.result()).isEqualTo("VERIFIED");
        assertThat(verified.baselineCapturedAt()).isEqualTo(capturedAt);
        assertThat(verified.rpoSeconds()).isEqualTo(600);
        assertThat(verified.rtoSeconds()).isEqualTo(300);
        assertThat(backups.status(OWNER, setId).lastDrill().result()).isEqualTo("VERIFIED");

        BackupService.DrillView failed = backups.recordDrill(OWNER, setId, new BackupService.DrillRequest(
                "ISOLATED_RESTORE", startedAt, finishedAt, 54, 53, true, "PASS", "PASS"));
        assertThat(failed.result()).isEqualTo("FAILED");
        assertThat(failed.rpoSeconds()).isEqualTo(600);
        assertThat(failed.rtoSeconds()).isEqualTo(300);
    }

    @Test
    @DisplayName("制品缺失时演练只能 UNVERIFIED；非法模式与时间直接拒绝")
    void drillWithoutArtifactsIsNotVerified() {
        backups.createSet(OWNER, SET, "prod", null, 14, true);
        long setId = set(OWNER, SET).id();
        Instant capturedAt = Instant.parse("2026-11-06T01:00:00Z");
        backups.ingestManifest(OWNER, setId, manifest(capturedAt,
                artifact("db.sql.gz", "DATABASE", "a".repeat(64), 1024, 42)));

        BackupService.DrillView unverified = backups.recordDrill(OWNER, setId, new BackupService.DrillRequest(
                "ISOLATED_RESTORE", capturedAt.plusSeconds(60), capturedAt.plusSeconds(120),
                54, 54, true, "PASS", "PASS"));
        assertThat(unverified.result()).isEqualTo("UNVERIFIED");
        assertThat(unverified.detail()).contains("ATTACHMENTS", "KEYS");

        assertThatThrownBy(() -> backups.recordDrill(OWNER, setId, new BackupService.DrillRequest(
                "IN_PLACE", capturedAt, capturedAt.plusSeconds(60), 1, 1, true, "PASS", "PASS")))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_DRILL_MODE_UNSUPPORTED");
        assertThatThrownBy(() -> backups.recordDrill(OWNER, setId, new BackupService.DrillRequest(
                "ISOLATED_RESTORE", capturedAt.plusSeconds(60), capturedAt, 1, 1, true, "PASS", "PASS")))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("BACKUP_DRILL_TIME_INVALID");
    }

    @Test
    @DisplayName("状态报告保留期过期、未校验与缺失组件")
    void statusReportsExpiredUnverifiedAndMissing() {
        backups.createSet(OWNER, "partial", "prod", List.of("DATABASE"), 14, false);
        long setId = set(OWNER, "partial").id();
        Instant capturedAt = Instant.now().minus(Duration.ofDays(20));
        backups.ingestManifest(OWNER, setId, manifest(capturedAt,
                artifact("old.sql.gz", "DATABASE", "a".repeat(64), 1024, 42)));

        BackupService.StatusView status = backups.status(OWNER, setId);
        assertThat(status.expiredArtifacts()).containsExactly("old.sql.gz");
        assertThat(status.unverifiedArtifacts()).containsExactly("old.sql.gz");
        assertThat(status.missingComponents()).contains("ATTACHMENTS", "KNOWLEDGE_MANIFEST", "AUDIT", "KEYS");
        assertThat(status.missingArtifacts()).as("集合内的 DATABASE 已有制品").isEmpty();
        assertThat(status.unoffsiteArtifacts()).as("未要求异机副本时不列缺口").isEmpty();
        assertThat(status.lastDrill()).isNull();
        assertThat(controller.status(OWNER, setId).getData().missingComponents()).hasSize(4);
    }

    /* ── 夹具 ─────────────────────────────────────────────────────────── */

    private BackupService.SetView set(long userId, String name) {
        return backups.listSets(userId).stream().filter(view -> view.name().equals(name)).findFirst().orElseThrow();
    }

    private static String manifest(Instant capturedAt, String... artifacts) {
        return """
                {"schema":"smartops-backup/v1","capturedAt":"%s","artifacts":[%s]}
                """.formatted(capturedAt.toString(), String.join(",", artifacts));
    }

    private static String artifact(String artifactId, String component, String sha256, long bytes, long itemCount) {
        return """
                {"artifactId":"%s","component":"%s","sourceUri":"backup/%s","sha256":"%s","bytes":%d,"itemCount":%d}
                """.formatted(artifactId, component, artifactId, sha256, bytes, itemCount);
    }
}
