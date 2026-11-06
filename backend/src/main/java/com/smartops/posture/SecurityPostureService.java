package com.smartops.posture;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * OPS-15：安全与配置报告接入（Trivy / kube-bench / Falco）。
 *
 * <p>只接受可复核的事实：报告的工具有版本、范围、目标、起止时间与摘要；
 * 命中按 {@code sha256(tool|target|ruleId|location)} 去重，但保留观察次数与最近报告；
 * 修复必须由"同工具同目标且更新"的报告证明，例外必须写明到期时间。</p>
 */
@Service
public class SecurityPostureService {

    /** 当前支持的第三方工具；未知工具直接拒绝，避免把"来源不明的报告"当成事实。 */
    public static final Set<String> SUPPORTED_TOOLS = Set.of("TRIVY", "KUBE_BENCH", "FALCO");

    public static final List<String> SEVERITIES = List.of("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN");

    public static final List<String> STATUSES = List.of("OPEN", "REOPENED", "EXCEPTION", "EXPIRED", "FIXED");

    public static final String STATUS_OPEN = "OPEN";
    public static final String STATUS_REOPENED = "REOPENED";
    public static final String STATUS_EXCEPTION = "EXCEPTION";
    public static final String STATUS_EXPIRED = "EXPIRED";
    public static final String STATUS_FIXED = "FIXED";

    private static final Pattern SHA256 = Pattern.compile("[0-9a-fA-F]{64}");

    private final JdbcTemplate jdbc;

    public SecurityPostureService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /* ── 报告接入 ─────────────────────────────────────────────────────── */

    public ReportView ingestReport(long userId, ReportInput input) {
        if (input == null) throw new BusinessException(400, "SECURITY_REPORT_REQUIRED: 缺少报告内容");
        String reportRef = requireText(input.reportRef(), "SECURITY_REPORT_REF_REQUIRED: 缺少报告编号");
        String tool = normalizeTool(input.tool());
        if (!SUPPORTED_TOOLS.contains(tool)) {
            throw new BusinessException(400, "SECURITY_TOOL_UNSUPPORTED: 仅支持 TRIVY/KUBE_BENCH/FALCO");
        }
        String toolVersion = requireText(input.toolVersion(), "SECURITY_TOOL_VERSION_REQUIRED: 缺少工具版本");
        String scope = requireText(input.scope(), "SECURITY_SCOPE_REQUIRED: 缺少扫描范围");
        String target = requireText(input.target(), "SECURITY_TARGET_REQUIRED: 缺少扫描目标");
        Instant startedAt = requireInstant(input.startedAt(), "SECURITY_STARTED_AT_REQUIRED: 缺少扫描开始时间");
        Instant finishedAt = requireInstant(input.finishedAt(), "SECURITY_FINISHED_AT_REQUIRED: 缺少扫描结束时间");
        if (!finishedAt.isAfter(startedAt)) {
            throw new BusinessException(400, "SECURITY_REPORT_TIME_INVALID: 结束时间必须晚于开始时间");
        }

        Integer exists = jdbc.query("SELECT id FROM security_scan_report WHERE user_id=? AND report_ref=?",
                rs -> rs.next() ? rs.getInt(1) : null, userId, reportRef);
        if (exists != null) {
            throw new BusinessException(409, "SECURITY_REPORT_EXISTS: 报告编号已存在 " + reportRef);
        }

        Map<String, FindingInput> unique = new LinkedHashMap<>();
        for (FindingInput finding : input.findings() == null ? List.<FindingInput>of() : input.findings()) {
            if (finding == null) continue;
            String ruleId = requireText(finding.ruleId(), "SECURITY_RULE_ID_REQUIRED: 命中缺少 ruleId");
            String key = findingKey(tool, target, ruleId, trimToNull(finding.location()));
            unique.putIfAbsent(key, new FindingInput(ruleId, trimToNull(finding.title()), finding.severity(),
                    trimToNull(finding.location()), trimToNull(finding.imageDigest()), trimToNull(finding.assetId())));
        }
        int findingCount = unique.size();
        String contentSha = input.contentSha256() == null || input.contentSha256().isBlank()
                ? digest(tool + "|" + target + "|" + reportRef + "|" + startedAt + "|" + finishedAt + "|"
                + String.join(",", unique.keySet()))
                : requireSha256(input.contentSha256(), "SECURITY_CONTENT_SHA_INVALID: contentSha256 需为 64 位十六进制");

        jdbc.update("""
                INSERT INTO security_scan_report
                  (user_id,report_ref,tool,tool_version,scope,target,started_at,finished_at,source_ref,content_sha256,finding_count)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, userId, reportRef, tool, toolVersion, scope, target,
                Timestamp.from(startedAt), Timestamp.from(finishedAt), trimToNull(input.sourceRef()), contentSha, findingCount);
        long reportId = jdbc.queryForObject(
                "SELECT id FROM security_scan_report WHERE user_id=? AND report_ref=?", Long.class, userId, reportRef);

        int created = 0;
        int reopened = 0;
        int known = 0;
        List<FindingView> findings = new ArrayList<>();
        for (Map.Entry<String, FindingInput> entry : unique.entrySet()) {
            String key = entry.getKey();
            FindingInput observed = entry.getValue();
            String severity = normalizeSeverity(observed.severity());
            FindingRow current = findFinding(userId, key);
            if (current == null) {
                jdbc.update("""
                        INSERT INTO security_finding
                          (user_id,finding_key,tool,rule_id,title,severity,target,location,image_digest,asset_id,
                           status,first_seen_at,last_seen_at,seen_count,last_report_id,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, userId, key, tool, observed.ruleId(), observed.title(), severity, target,
                        observed.location(), observed.imageDigest(), observed.assetId(), STATUS_OPEN,
                        Timestamp.from(finishedAt), Timestamp.from(finishedAt), 1, reportId, Timestamp.from(Instant.now()));
                created++;
            } else {
                String status = current.status();
                boolean reopenedNow = false;
                if (STATUS_FIXED.equals(status) || STATUS_EXPIRED.equals(status)) {
                    status = STATUS_REOPENED;
                    reopenedNow = true;
                } else if (STATUS_EXCEPTION.equals(status)) {
                    Instant until = current.exceptionUntil();
                    if (until != null && !until.isAfter(finishedAt)) {
                        status = STATUS_REOPENED;
                        reopenedNow = true;
                    }
                }
                Instant lastSeen = finishedAt.isAfter(current.lastSeenAt()) ? finishedAt : current.lastSeenAt();
                Instant fixedAt = reopenedNow ? null : current.fixedAt();
                Instant verifiedAt = reopenedNow ? null : current.verifiedAt();
                Instant exceptionUntil = reopenedNow ? null : current.exceptionUntil();
                String exceptionReason = reopenedNow ? null : current.exceptionReason();
                jdbc.update("""
                        UPDATE security_finding SET severity=?,title=?,location=?,image_digest=?,asset_id=?,
                          status=?,last_seen_at=?,seen_count=seen_count+1,last_report_id=?,
                          exception_until=?,exception_reason=?,fixed_at=?,verified_at=?,updated_at=?
                        WHERE user_id=? AND finding_key=?
                        """, severity, observed.title() == null ? current.title() : observed.title(),
                        observed.location() == null ? current.location() : observed.location(),
                        observed.imageDigest() == null ? current.imageDigest() : observed.imageDigest(),
                        observed.assetId() == null ? current.assetId() : observed.assetId(),
                        status, Timestamp.from(lastSeen), reportId,
                        exceptionUntil == null ? null : Timestamp.from(exceptionUntil), exceptionReason,
                        fixedAt == null ? null : Timestamp.from(fixedAt),
                        verifiedAt == null ? null : Timestamp.from(verifiedAt),
                        Timestamp.from(Instant.now()), userId, key);
                if (reopenedNow) reopened++;
                else known++;
            }
            jdbc.update("INSERT INTO security_report_finding (report_id,finding_key) VALUES (?,?)",
                    reportId, key);
            findings.add(findingView(requireFinding(userId, key)));
        }
        return new ReportView(reportId, reportRef, tool, toolVersion, scope, target, startedAt, finishedAt,
                trimToNull(input.sourceRef()), contentSha, findingCount, created, reopened, known,
                List.copyOf(findings));
    }

    /* ── 修复复测 ─────────────────────────────────────────────────────── */

    public VerifyView verifyFix(long userId, long findingId, String reportRef) {
        FindingRow finding = requireFindingById(userId, findingId);
        if (STATUS_FIXED.equals(finding.status())) {
            throw new BusinessException(409, "SECURITY_FINDING_ALREADY_FIXED: 该命中已确认修复");
        }
        ReportRow report = requireReport(userId, requireText(reportRef, "SECURITY_VERIFY_REPORT_REQUIRED: 缺少复测报告编号"));
        if (!report.tool().equals(finding.tool()) || !report.target().equals(finding.target())) {
            throw new BusinessException(400,
                    "SECURITY_VERIFY_REPORT_MISMATCH: 复测报告必须与命中同工具同目标");
        }
        ReportRow lastReport = requireReportById(userId, finding.lastReportId());

        Long hits = jdbc.queryForObject(
                "SELECT COUNT(*) FROM security_report_finding WHERE report_id=? AND finding_key=?",
                Long.class, report.id(), finding.findingKey());
        boolean stillPresent = hits != null && hits > 0;
        boolean latest = report.id() == finding.lastReportId();

        if (stillPresent && !latest) {
            throw new BusinessException(400,
                    "SECURITY_VERIFY_REPORT_NOT_NEWER: 复测报告必须晚于最近一次命中的报告");
        }
        if (!stillPresent && !report.finishedAt().isAfter(lastReport.finishedAt())) {
            throw new BusinessException(400,
                    "SECURITY_VERIFY_REPORT_NOT_NEWER: 复测报告必须晚于最近一次命中的报告");
        }

        if (stillPresent) {
            return new VerifyView(findingView(finding), report.reportRef(), report.toolVersion(),
                    report.finishedAt(), true, evidence(report));
        }
        Instant now = Instant.now();
        jdbc.update("""
                UPDATE security_finding SET status=?,fixed_at=?,verified_at=?,exception_until=NULL,
                  exception_reason=NULL,updated_at=? WHERE user_id=? AND id=?
                """, STATUS_FIXED, Timestamp.from(report.finishedAt()), Timestamp.from(now),
                Timestamp.from(now), userId, findingId);
        return new VerifyView(findingView(requireFindingById(userId, findingId)), report.reportRef(),
                report.toolVersion(), report.finishedAt(), false, evidence(report));
    }

    /* ── 例外 ─────────────────────────────────────────────────────────── */

    public FindingView exception(long userId, long findingId, Instant until, String reason) {
        FindingRow finding = requireFindingById(userId, findingId);
        if (STATUS_FIXED.equals(finding.status())) {
            throw new BusinessException(409, "SECURITY_FINDING_ALREADY_FIXED: 已修复的命中无需例外");
        }
        Instant deadline = requireInstant(until, "SECURITY_EXCEPTION_UNTIL_REQUIRED: 缺少例外到期时间");
        if (!deadline.isAfter(Instant.now())) {
            throw new BusinessException(400, "SECURITY_EXCEPTION_UNTIL_INVALID: 例外到期时间必须晚于当前时间");
        }
        String reasonText = requireText(reason, "SECURITY_EXCEPTION_REASON_REQUIRED: 缺少例外理由");
        jdbc.update("""
                UPDATE security_finding SET status=?,exception_until=?,exception_reason=?,
                  fixed_at=NULL,verified_at=NULL,updated_at=? WHERE user_id=? AND id=?
                """, STATUS_EXCEPTION, Timestamp.from(deadline), reasonText,
                Timestamp.from(Instant.now()), userId, findingId);
        return findingView(requireFindingById(userId, findingId));
    }

    /* ── 态势汇总 ─────────────────────────────────────────────────────── */

    public SummaryView summary(long userId, String target) {
        expireOverdueExceptions(userId);
        String targetFilter = trimToNull(target);
        List<FindingRow> rows = jdbc.query("""
                SELECT * FROM security_finding WHERE user_id=? ORDER BY severity, id
                """, FINDING_MAPPER, userId).stream()
                .filter(row -> targetFilter == null || targetFilter.equals(row.target())).toList();

        Map<String, Integer> severityCounts = new LinkedHashMap<>();
        Map<String, Integer> statusCounts = new LinkedHashMap<>();
        Set<String> images = new LinkedHashSet<>();
        Set<String> assets = new LinkedHashSet<>();
        int observations = 0;
        int activeExceptions = 0;
        int expiredExceptions = 0;
        for (FindingRow row : rows) {
            severityCounts.merge(row.severity(), 1, Integer::sum);
            statusCounts.merge(row.status(), 1, Integer::sum);
            observations += row.seenCount();
            if (row.imageDigest() != null) images.add(row.imageDigest());
            if (row.assetId() != null) assets.add(row.assetId());
            if (STATUS_EXCEPTION.equals(row.status())) activeExceptions++;
            else if (STATUS_EXPIRED.equals(row.status())) expiredExceptions++;
        }

        List<SeverityCount> severities = SEVERITIES.stream()
                .filter(severityCounts::containsKey)
                .map(severity -> new SeverityCount(severity, severityCounts.get(severity))).toList();
        List<StatusCount> statuses = STATUSES.stream()
                .filter(statusCounts::containsKey)
                .map(status -> new StatusCount(status, statusCounts.get(status))).toList();

        String reportSql = targetFilter == null
                ? "SELECT * FROM security_scan_report WHERE user_id=? ORDER BY finished_at DESC, id DESC"
                : "SELECT * FROM security_scan_report WHERE user_id=? AND target=? ORDER BY finished_at DESC, id DESC";
        Object[] reportArgs = targetFilter == null ? new Object[]{userId} : new Object[]{userId, targetFilter};
        List<ReportSummary> reports = jdbc.query(reportSql, REPORT_MAPPER, reportArgs).stream()
                .limit(50)
                .map(report -> new ReportSummary(report.id(), report.reportRef(), report.tool(),
                        report.toolVersion(), report.scope(), report.target(), report.finishedAt(),
                        report.findingCount()))
                .toList();

        int duplicateObservations = Math.max(0, observations - rows.size());
        return new SummaryView(targetFilter, rows.size(), observations, duplicateObservations,
                severities, statuses, activeExceptions, expiredExceptions,
                List.copyOf(images), List.copyOf(assets), reports);
    }

    private void expireOverdueExceptions(long userId) {
        jdbc.update("""
                UPDATE security_finding SET status=?,updated_at=?
                WHERE user_id=? AND status=? AND exception_until IS NOT NULL AND exception_until<?
                """, STATUS_EXPIRED, Timestamp.from(Instant.now()), userId, STATUS_EXCEPTION,
                Timestamp.from(Instant.now()));
    }

    /* ── 内部支撑 ─────────────────────────────────────────────────────── */

    private FindingRow requireFinding(long userId, String findingKey) {
        List<FindingRow> rows = jdbc.query(
                "SELECT * FROM security_finding WHERE user_id=? AND finding_key=?",
                FINDING_MAPPER, userId, findingKey);
        if (rows.isEmpty()) throw new BusinessException(404, "SECURITY_FINDING_NOT_FOUND: 命中不存在");
        return rows.get(0);
    }

    private FindingRow findFinding(long userId, String findingKey) {
        List<FindingRow> rows = jdbc.query(
                "SELECT * FROM security_finding WHERE user_id=? AND finding_key=?",
                FINDING_MAPPER, userId, findingKey);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private FindingRow requireFindingById(long userId, long id) {
        List<FindingRow> rows = jdbc.query(
                "SELECT * FROM security_finding WHERE user_id=? AND id=?", FINDING_MAPPER, userId, id);
        if (rows.isEmpty()) throw new BusinessException(404, "SECURITY_FINDING_NOT_FOUND: 命中不存在");
        return rows.get(0);
    }

    private ReportRow requireReport(long userId, String reportRef) {
        List<ReportRow> rows = jdbc.query(
                "SELECT * FROM security_scan_report WHERE user_id=? AND report_ref=?",
                REPORT_MAPPER, userId, reportRef);
        if (rows.isEmpty()) throw new BusinessException(404, "SECURITY_REPORT_NOT_FOUND: 报告不存在 " + reportRef);
        return rows.get(0);
    }

    private ReportRow requireReportById(long userId, long id) {
        List<ReportRow> rows = jdbc.query(
                "SELECT * FROM security_scan_report WHERE user_id=? AND id=?", REPORT_MAPPER, userId, id);
        if (rows.isEmpty()) throw new BusinessException(404, "SECURITY_REPORT_NOT_FOUND: 命中引用的报告不存在");
        return rows.get(0);
    }

    private FindingView findingView(FindingRow row) {
        return new FindingView(row.id(), row.findingKey(), row.tool(), row.ruleId(), row.title(),
                row.severity(), row.target(), row.location(), row.imageDigest(), row.assetId(), row.status(),
                row.firstSeenAt(), row.lastSeenAt(), row.seenCount(), row.exceptionUntil(),
                row.exceptionReason(), row.fixedAt(), row.verifiedAt());
    }

    private static String evidence(ReportRow report) {
        return "report=" + report.reportRef() + ";tool=" + report.tool() + ";version=" + report.toolVersion()
                + ";scope=" + report.scope() + ";finishedAt=" + report.finishedAt();
    }

    private static String findingKey(String tool, String target, String ruleId, String location) {
        return digest(tool + "|" + target + "|" + ruleId + "|" + (location == null ? "" : location));
    }

    private static String digest(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder(bytes.length * 2);
            for (byte item : bytes) builder.append(String.format("%02x", item));
            return builder.toString();
        } catch (NoSuchAlgorithmException missing) {
            throw new IllegalStateException("SHA-256 不可用", missing);
        }
    }

    private static String normalizeTool(String value) {
        return requireText(value, "SECURITY_TOOL_REQUIRED: 缺少扫描工具").toUpperCase(Locale.ROOT);
    }

    /** 未知严重度一律记 UNKNOWN：不把无法识别的级别当成 HIGH 或 LOW。 */
    private static String normalizeSeverity(String value) {
        String normalized = trimToNull(value);
        if (normalized == null) return "UNKNOWN";
        String upper = normalized.toUpperCase(Locale.ROOT);
        return SEVERITIES.contains(upper) ? upper : "UNKNOWN";
    }

    private static String requireText(String value, String message) {
        if (value == null || value.isBlank()) throw new BusinessException(400, message);
        return value.trim();
    }

    private static Instant requireInstant(Instant value, String message) {
        if (value == null) throw new BusinessException(400, message);
        return value;
    }

    private static String requireSha256(String value, String message) {
        if (!SHA256.matcher(value.trim()).matches()) throw new BusinessException(400, message);
        return value.trim().toLowerCase(Locale.ROOT);
    }

    private static String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    /* ── 行模型与视图 ─────────────────────────────────────────────────── */

    private record ReportRow(long id, String reportRef, String tool, String toolVersion, String scope,
                             String target, Instant startedAt, Instant finishedAt, String sourceRef,
                             String contentSha256, int findingCount) {}

    private record FindingRow(long id, String findingKey, String tool, String ruleId, String title,
                              String severity, String target, String location, String imageDigest,
                              String assetId, String status, Instant firstSeenAt, Instant lastSeenAt,
                              int seenCount, long lastReportId, Instant exceptionUntil,
                              String exceptionReason, Instant fixedAt, Instant verifiedAt) {}

    private static final RowMapper<ReportRow> REPORT_MAPPER = (rs, rowNum) -> new ReportRow(
            rs.getLong("id"), rs.getString("report_ref"), rs.getString("tool"), rs.getString("tool_version"),
            rs.getString("scope"), rs.getString("target"), instant(rs, "started_at"),
            instant(rs, "finished_at"), rs.getString("source_ref"), rs.getString("content_sha256"),
            rs.getInt("finding_count"));

    private static final RowMapper<FindingRow> FINDING_MAPPER = (rs, rowNum) -> new FindingRow(
            rs.getLong("id"), rs.getString("finding_key"), rs.getString("tool"), rs.getString("rule_id"),
            rs.getString("title"), rs.getString("severity"), rs.getString("target"),
            rs.getString("location"), rs.getString("image_digest"), rs.getString("asset_id"),
            rs.getString("status"), instant(rs, "first_seen_at"), instant(rs, "last_seen_at"),
            rs.getInt("seen_count"), rs.getLong("last_report_id"), instant(rs, "exception_until"),
            rs.getString("exception_reason"), instant(rs, "fixed_at"), instant(rs, "verified_at"));

    public record FindingInput(String ruleId, String title, String severity, String location,
                               String imageDigest, String assetId) {}

    public record ReportInput(String reportRef, String tool, String toolVersion, String scope, String target,
                              Instant startedAt, Instant finishedAt, String sourceRef, String contentSha256,
                              List<FindingInput> findings) {}

    public record FindingView(long id, String findingKey, String tool, String ruleId, String title,
                              String severity, String target, String location, String imageDigest,
                              String assetId, String status, Instant firstSeenAt, Instant lastSeenAt,
                              int seenCount, Instant exceptionUntil, String exceptionReason,
                              Instant fixedAt, Instant verifiedAt) {}

    public record ReportView(long id, String reportRef, String tool, String toolVersion, String scope,
                             String target, Instant startedAt, Instant finishedAt, String sourceRef,
                             String contentSha256, int findingCount, int createdFindings,
                             int reopenedFindings, int knownFindings, List<FindingView> findings) {}

    public record VerifyView(FindingView finding, String reportRef, String toolVersion,
                             Instant reportFinishedAt, boolean stillPresent, String evidence) {}

    public record SeverityCount(String severity, int count) {}

    public record StatusCount(String status, int count) {}

    public record ReportSummary(long id, String reportRef, String tool, String toolVersion, String scope,
                                String target, Instant finishedAt, int findingCount) {}

    public record SummaryView(String target, int totalFindings, int observationCount, int duplicateObservations,
                              List<SeverityCount> severities, List<StatusCount> statuses,
                              int activeExceptions, int expiredExceptions,
                              List<String> images, List<String> assets, List<ReportSummary> reports) {}
}
