package com.smartops.posture;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-15：报告上下文保留、去重、修复复测、例外到期与态势汇总。
 */
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:security_posture_service;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
        "smartops.runbook.schedule.initial-delay-ms=86400000",
        "smartops.runbook.alert.initial-delay-ms=86400000",
        "smartops.sentinel.poll.initial-delay-ms=86400000",
        "smartops.sentinel.poll.interval-ms=86400000"
})
class SecurityPostureServiceIntegrationTest {

    private static final long OWNER = 131L;

    @Autowired JdbcTemplate jdbc;
    @Autowired SecurityPostureService posture;

    @BeforeEach
    void clean() {
        jdbc.update("DELETE FROM security_report_finding");
        jdbc.update("DELETE FROM security_finding");
        jdbc.update("DELETE FROM security_scan_report");
    }

    @Test
    @DisplayName("报告保留工具版本/范围/时间，命中按工具+目标+规则+位置去重，未知严重度记 UNKNOWN")
    void reportKeepsToolContextAndDeduplicatesFindings() {
        SecurityPostureService.ReportView first = ingest("trivy-1", "trivy", "0.50.1", "prod-cluster",
                "cluster-a", Instant.parse("2026-11-01T01:00:00Z"), List.of(
                        finding("CVE-2026-1", "HIGH", "web:1.2", "sha256:aaa", "asset-web"),
                        finding("CVE-2026-1", "HIGH", "web:1.2", "sha256:aaa", "asset-web"),
                        finding("CVE-2026-2", "weird", "api:1.0", null, "asset-api")));

        assertThat(first.tool()).isEqualTo("TRIVY");
        assertThat(first.toolVersion()).isEqualTo("0.50.1");
        assertThat(first.scope()).isEqualTo("prod-cluster");
        assertThat(first.target()).isEqualTo("cluster-a");
        assertThat(first.startedAt()).isEqualTo(Instant.parse("2026-11-01T00:00:00Z"));
        assertThat(first.finishedAt()).isEqualTo(Instant.parse("2026-11-01T01:00:00Z"));
        assertThat(first.findingCount()).isEqualTo(2);
        assertThat(first.createdFindings()).isEqualTo(2);
        assertThat(first.contentSha256()).matches("[0-9a-f]{64}");
        assertThat(first.findings()).extracting(SecurityPostureService.FindingView::severity)
                .containsExactlyInAnyOrder("HIGH", "UNKNOWN");
        assertThat(first.findings()).allSatisfy(view -> assertThat(view.status()).isEqualTo("OPEN"));

        SecurityPostureService.ReportView second = ingest("trivy-2", "TRIVY", "0.51.0", "prod-cluster",
                "cluster-a", Instant.parse("2026-11-02T01:00:00Z"),
                List.of(finding("CVE-2026-1", "CRITICAL", "web:1.2", "sha256:aaa", "asset-web")));

        assertThat(second.createdFindings()).isZero();
        assertThat(second.knownFindings()).isEqualTo(1);
        assertThat(second.findings()).singleElement().satisfies(view -> {
            assertThat(view.seenCount()).isEqualTo(2);
            assertThat(view.lastSeenAt()).isEqualTo(Instant.parse("2026-11-02T01:00:00Z"));
            assertThat(view.severity()).isEqualTo("CRITICAL");
            assertThat(view.status()).isEqualTo("OPEN");
        });
    }

    @Test
    @DisplayName("重复报告编号、未知工具与缺失上下文字段被拒绝，不写入任何记录")
    void invalidReportsAreRejected() {
        ingest("dup-1", "TRIVY", "0.50.1", "prod", "cluster-a", Instant.parse("2026-11-01T01:00:00Z"), List.of());

        assertThatThrownBy(() -> ingest("dup-1", "TRIVY", "0.50.1", "prod", "cluster-a",
                Instant.parse("2026-11-02T01:00:00Z"), List.of()))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_REPORT_EXISTS");
        assertThatThrownBy(() -> ingest("x-1", "NESSUS", "1.0", "prod", "cluster-a",
                Instant.parse("2026-11-01T01:00:00Z"), List.of()))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_TOOL_UNSUPPORTED");
        assertThatThrownBy(() -> posture.ingestReport(OWNER, new SecurityPostureService.ReportInput(
                "x-2", "TRIVY", " ", "prod", "cluster-a", Instant.parse("2026-11-01T00:00:00Z"),
                Instant.parse("2026-11-01T01:00:00Z"), null, null, List.of())))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_TOOL_VERSION_REQUIRED");
        assertThatThrownBy(() -> posture.ingestReport(OWNER, new SecurityPostureService.ReportInput(
                "x-3", "TRIVY", "1.0", "prod", "cluster-a", Instant.parse("2026-11-01T01:00:00Z"),
                Instant.parse("2026-11-01T00:00:00Z"), null, null, List.of())))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_REPORT_TIME_INVALID");
        assertThatThrownBy(() -> posture.ingestReport(OWNER, new SecurityPostureService.ReportInput(
                "x-4", "TRIVY", "1.0", "prod", "cluster-a", Instant.parse("2026-11-01T00:00:00Z"),
                Instant.parse("2026-11-01T01:00:00Z"), null, "not-a-sha", List.of())))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_CONTENT_SHA_INVALID");

        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM security_scan_report WHERE user_id=?",
                Long.class, OWNER)).isEqualTo(1);
    }

    @Test
    @DisplayName("修复复测只接受同工具同目标且更新的报告；旧报告与异构报告被拒绝")
    void fixVerificationRequiresNewerSameToolSameTargetReport() {
        SecurityPostureService.ReportView baseline = ingest("trivy-1", "TRIVY", "0.50.1", "prod",
                "cluster-a", Instant.parse("2026-11-01T01:00:00Z"), List.of(
                        finding("CVE-A", "HIGH", "web:1.2", null, null),
                        finding("CVE-B", "MEDIUM", "api:1.0", null, null)));
        long cveA = baseline.findings().stream()
                .filter(view -> view.ruleId().equals("CVE-A")).findFirst().orElseThrow().id();
        long cveB = baseline.findings().stream()
                .filter(view -> view.ruleId().equals("CVE-B")).findFirst().orElseThrow().id();

        ingest("trivy-fixed", "TRIVY", "0.52.0", "prod", "cluster-a",
                Instant.parse("2026-11-03T01:00:00Z"), List.of());

        SecurityPostureService.VerifyView verified = posture.verifyFix(OWNER, cveA, "trivy-fixed");
        assertThat(verified.stillPresent()).isFalse();
        assertThat(verified.reportRef()).isEqualTo("trivy-fixed");
        assertThat(verified.toolVersion()).isEqualTo("0.52.0");
        assertThat(verified.reportFinishedAt()).isEqualTo(Instant.parse("2026-11-03T01:00:00Z"));
        assertThat(verified.evidence()).contains("tool=TRIVY", "version=0.52.0", "scope=prod");
        assertThat(verified.finding().status()).isEqualTo("FIXED");
        assertThat(verified.finding().fixedAt()).isEqualTo(Instant.parse("2026-11-03T01:00:00Z"));
        assertThat(verified.finding().verifiedAt()).isNotNull();

        ingest("kube-1", "KUBE_BENCH", "0.8.0", "prod", "cluster-a",
                Instant.parse("2026-11-04T01:00:00Z"), List.of());
        assertThatThrownBy(() -> posture.verifyFix(OWNER, cveB, "kube-1"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_VERIFY_REPORT_MISMATCH");

        ingest("trivy-epoch", "TRIVY", "0.50.1", "prod", "cluster-a",
                Instant.parse("2026-10-30T01:00:00Z"), List.of());
        assertThatThrownBy(() -> posture.verifyFix(OWNER, cveB, "trivy-epoch"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_VERIFY_REPORT_NOT_NEWER");

        assertThatThrownBy(() -> posture.verifyFix(OWNER, cveA, "trivy-fixed"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_FINDING_ALREADY_FIXED");
    }

    @Test
    @DisplayName("已修复命中再次出现转 REOPENED；用最新报告复测仍存在时如实返回未修复")
    void reobservedFindingsReopen() {
        SecurityPostureService.ReportView first = ingest("trivy-1", "TRIVY", "0.50.1", "prod",
                "cluster-a", Instant.parse("2026-11-01T01:00:00Z"),
                List.of(finding("CVE-C", "HIGH", "web:1.2", null, null)));
        long findingId = first.findings().get(0).id();

        ingest("trivy-2", "TRIVY", "0.51.0", "prod", "cluster-a",
                Instant.parse("2026-11-02T01:00:00Z"), List.of());
        posture.verifyFix(OWNER, findingId, "trivy-2");

        SecurityPostureService.ReportView third = ingest("trivy-3", "TRIVY", "0.52.0", "prod",
                "cluster-a", Instant.parse("2026-11-03T01:00:00Z"),
                List.of(finding("CVE-C", "CRITICAL", "web:1.2", null, null)));
        assertThat(third.reopenedFindings()).isEqualTo(1);
        assertThat(third.findings()).singleElement().satisfies(view -> {
            assertThat(view.status()).isEqualTo("REOPENED");
            assertThat(view.seenCount()).isEqualTo(2);
            assertThat(view.fixedAt()).isNull();
            assertThat(view.verifiedAt()).isNull();
        });

        SecurityPostureService.VerifyView present = posture.verifyFix(OWNER, findingId, "trivy-3");
        assertThat(present.stillPresent()).isTrue();
        assertThat(present.finding().status()).isEqualTo("REOPENED");
    }

    @Test
    @DisplayName("例外必须有未来到期时间与理由，到期转 EXPIRED，再次命中转 REOPENED")
    void exceptionsRequireDeadlineAndReasonAndExpire() {
        SecurityPostureService.ReportView first = ingest("trivy-1", "TRIVY", "0.50.1", "prod",
                "cluster-a", Instant.parse("2026-11-01T01:00:00Z"),
                List.of(finding("CVE-D", "LOW", "host:1", null, null)));
        long findingId = first.findings().get(0).id();
        Instant now = Instant.now();

        assertThatThrownBy(() -> posture.exception(OWNER, findingId, now.minusSeconds(60), "upstream"))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_EXCEPTION_UNTIL_INVALID");
        assertThatThrownBy(() -> posture.exception(OWNER, findingId, now.plusSeconds(86400), "  "))
                .isInstanceOf(BusinessException.class).hasMessageContaining("SECURITY_EXCEPTION_REASON_REQUIRED");

        SecurityPostureService.FindingView excepted = posture.exception(OWNER, findingId,
                now.plusSeconds(86400), "等待上游基础镜像更新");
        assertThat(excepted.status()).isEqualTo("EXCEPTION");
        assertThat(excepted.exceptionReason()).isEqualTo("等待上游基础镜像更新");
        assertThat(excepted.exceptionUntil()).isNotNull();

        SecurityPostureService.SummaryView active = posture.summary(OWNER, null);
        assertThat(active.activeExceptions()).isEqualTo(1);
        assertThat(active.expiredExceptions()).isZero();

        // 模拟到期：把到期时间回拨到过去，汇总时必须自动转 EXPIRED，而不是继续静默。
        jdbc.update("UPDATE security_finding SET exception_until=? WHERE user_id=? AND id=?",
                Timestamp.from(now.minusSeconds(60)), OWNER, findingId);
        SecurityPostureService.SummaryView expired = posture.summary(OWNER, null);
        assertThat(expired.activeExceptions()).isZero();
        assertThat(expired.expiredExceptions()).isEqualTo(1);
        assertThat(posture.summary(OWNER, null).statuses()).containsExactly(
                new SecurityPostureService.StatusCount("EXPIRED", 1));

        SecurityPostureService.ReportView afterExpiry = ingest("trivy-2", "TRIVY", "0.51.0", "prod",
                "cluster-a", Instant.parse("2026-11-05T01:00:00Z"),
                List.of(finding("CVE-D", "LOW", "host:1", null, null)));
        assertThat(afterExpiry.findings()).singleElement().satisfies(view -> {
            assertThat(view.status()).isEqualTo("REOPENED");
            assertThat(view.exceptionUntil()).isNull();
            assertThat(view.exceptionReason()).isNull();
        });
    }

    @Test
    @DisplayName("态势汇总按严重度/状态统计，附带镜像、资产与去重后的观察次数")
    void summaryCountsSeverityStatusImagesAndAssets() {
        ingest("trivy-1", "TRIVY", "0.50.1", "prod", "cluster-a",
                Instant.parse("2026-11-01T01:00:00Z"),
                List.of(finding("CVE-1", "HIGH", "web:1.2", "sha256:aaa", "asset-web")));
        ingest("falco-1", "FALCO", "0.37.0", "nodes", "node-1",
                Instant.parse("2026-11-01T02:00:00Z"),
                List.of(finding("FALCO-1", "medium", "proc", null, "asset-node")));

        SecurityPostureService.SummaryView summary = posture.summary(OWNER, null);
        assertThat(summary.totalFindings()).isEqualTo(2);
        assertThat(summary.observationCount()).isEqualTo(2);
        assertThat(summary.duplicateObservations()).isZero();
        assertThat(summary.severities()).containsExactly(
                new SecurityPostureService.SeverityCount("HIGH", 1),
                new SecurityPostureService.SeverityCount("MEDIUM", 1));
        assertThat(summary.statuses()).containsExactly(new SecurityPostureService.StatusCount("OPEN", 2));
        assertThat(summary.images()).containsExactly("sha256:aaa");
        assertThat(summary.assets()).containsExactlyInAnyOrder("asset-web", "asset-node");
        assertThat(summary.reports()).extracting(SecurityPostureService.ReportSummary::toolVersion)
                .containsExactlyInAnyOrder("0.50.1", "0.37.0");

        SecurityPostureService.SummaryView scoped = posture.summary(OWNER, "cluster-a");
        assertThat(scoped.target()).isEqualTo("cluster-a");
        assertThat(scoped.totalFindings()).isEqualTo(1);
        assertThat(scoped.reports()).extracting(SecurityPostureService.ReportSummary::reportRef)
                .containsExactly("trivy-1");
    }

    private SecurityPostureService.ReportView ingest(String reportRef, String tool, String toolVersion,
                                                     String scope, String target, Instant finishedAt,
                                                     List<SecurityPostureService.FindingInput> findings) {
        return posture.ingestReport(OWNER, new SecurityPostureService.ReportInput(reportRef, tool, toolVersion,
                scope, target, finishedAt.minusSeconds(3600), finishedAt, "scanner://" + reportRef,
                null, findings));
    }

    private SecurityPostureService.FindingInput finding(String ruleId, String severity, String location,
                                                       String imageDigest, String assetId) {
        return new SecurityPostureService.FindingInput(ruleId, ruleId + " 命中", severity, location,
                imageDigest, assetId);
    }
}
