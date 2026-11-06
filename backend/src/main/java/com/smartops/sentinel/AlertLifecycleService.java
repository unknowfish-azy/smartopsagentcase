package com.smartops.sentinel;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 告警生命周期：分组、自动恢复、静默窗口、转派升级、通知死信。
 *
 * <p>这里只在既有告警表上做增量，不改动 {@link SentinelService} 的处置与审批链路。
 * 关键取舍：</p>
 * <ul>
 *   <li>恢复判定只依赖已落库的采样，不依赖轮询时的内存状态 —— 进程重启也不会漏掉恢复；</li>
 *   <li>静默只阻止"新告警"和"通知"，不会篡改已有告警的状态；</li>
 *   <li>升级只调整级别并留痕，不触发执行。</li>
 * </ul>
 */
@Service
public class AlertLifecycleService {

    private static final Logger log = LoggerFactory.getLogger(AlertLifecycleService.class);

    /** 允许自动恢复的来源状态：执行中的 Remediating 视为仍在处置，不自动改写。 */
    private static final Set<String> RECOVERABLE_STATUSES = Set.of("OPEN", "NOTIFIED");

    private static final List<String> SEVERITY_ORDER = List.of("P3", "P2", "P1", "P0");

    private static final Set<String> SILENCE_SCOPES = Set.of("GLOBAL", "TASK");

    private final JdbcTemplate jdbc;
    private final SentinelNotifier notifier;
    private final AlertmanagerSilenceClient silenceClient;

    public AlertLifecycleService(JdbcTemplate jdbc, SentinelNotifier notifier,
                                 AlertmanagerSilenceClient silenceClient) {
        this.jdbc = jdbc;
        this.notifier = notifier;
        this.silenceClient = silenceClient;
    }

    /* ── 自动恢复：故障消失后进入待关闭 ───────────────────────────────── */

    /**
     * 指标恢复后把告警推进到 {@code RESOLVED}（待关闭）。
     *
     * <p>判定条件：任务在告警触发之后已有采样，且**最新一条采样不再异常**。
     * 只认"最新采样"，避免一次抖动就提前关单。</p>
     *
     * @return 本次自动转为待关闭的数量
     */
    @Transactional
    public int resolveRecoveredAlerts(int limit) {
        List<Map<String, Object>> rows = jdbc.queryForList("""
                SELECT a.id, a.task_id, a.metric FROM sentinel_alert a
                 WHERE a.status IN ('OPEN','NOTIFIED')
                   AND EXISTS (SELECT 1 FROM sentinel_metric_sample s
                                WHERE s.task_id=a.task_id AND s.sampled_at >= a.fired_at AND s.abnormal=FALSE
                                  AND NOT EXISTS (SELECT 1 FROM sentinel_metric_sample s2
                                                   WHERE s2.task_id=a.task_id AND s2.sampled_at >= a.fired_at
                                                     AND s2.sampled_at > s.sampled_at))
                 ORDER BY a.id ASC LIMIT ?
                """, Math.max(1, Math.min(200, limit)));

        int resolved = 0;
        for (Map<String, Object> row : rows) {
            long alertId = ((Number) row.get("id")).longValue();
            String metric = (String) row.get("metric");
            jdbc.update("""
                    UPDATE sentinel_alert
                       SET status='RESOLVED', resolved_at=CURRENT_TIMESTAMP, recovered_at=CURRENT_TIMESTAMP
                     WHERE id=? AND status IN ('OPEN','NOTIFIED')
                    """, alertId);
            recordEvent(alertId, null, "RECOVERED",
                    "指标已恢复正常，自动进入待关闭" + (metric == null ? "" : "（" + metric + "）"));
            resolved++;
        }
        if (resolved > 0) {
            log.info("alert lifecycle auto-resolved {} alert(s)", resolved);
        }
        return resolved;
    }

    /* ── 分组 ─────────────────────────────────────────────────────────── */

    /**
     * 按 group_key 聚合告警：同一故障的多条告警归成一组，
     * 看的顺序是"还有几条没关"，而不是按时间倒序被新告警淹没。
     */
    public List<GroupView> groups(SessionUser actor, int limit) {
        long userId = userId(actor);
        return jdbc.query("""
                SELECT COALESCE(a.group_key, CONCAT('task:', a.task_id)) AS group_key,
                       MAX(a.title) AS sample_title,
                       COUNT(1) AS total,
                       SUM(CASE WHEN a.status IN ('OPEN','NOTIFIED','PENDING_APPROVAL','REMEDIATING') THEN 1 ELSE 0 END) AS active,
                       SUM(CASE WHEN a.status='CLOSED' THEN 1 ELSE 0 END) AS closed,
                       MIN(a.severity) AS max_severity,
                       MAX(a.fired_at) AS last_fired_at
                  FROM sentinel_alert a
                  LEFT JOIN sentinel_task t ON t.id=a.task_id
                  LEFT JOIN sentinel_alert_rule r ON r.id=a.rule_id
                 WHERE t.user_id=? OR r.user_id=?
                 GROUP BY COALESCE(a.group_key, CONCAT('task:', a.task_id))
                 ORDER BY active DESC, last_fired_at DESC LIMIT ?
                """, (row, ignored) -> new GroupView(
                row.getString("group_key"), row.getString("sample_title"), row.getLong("total"),
                row.getLong("active"), row.getLong("closed"), row.getString("max_severity"),
                instant(row, "last_fired_at")), userId, userId, Math.max(1, Math.min(200, limit)));
    }

    /* ── 静默 / 维护窗口 ───────────────────────────────────────────────── */

    public List<SilenceView> listSilences(SessionUser actor) {
        long userId = userId(actor);
        return jdbc.query("""
                SELECT id, scope_type, scope_id, reason, starts_at, ends_at, created_by, status,
                       approved_by, external_status, external_error
                  FROM sentinel_silence
                 WHERE created_by=?
                 ORDER BY ends_at DESC LIMIT 100
                """, (row, ignored) -> view(row), userId);
    }

    /**
     * 建立静默窗口。
     *
     * <p>TASK 范围必须是自己名下的哨兵任务；GLOBAL 影响面大，只允许全局静默自己可见范围之外的告警时使用，
     * 因此同样限定有效期上限，避免"永久静默"变成事故放大器。</p>
     */
    @Transactional
    public SilenceView createSilence(SessionUser actor, SilenceRequest request) {
        long userId = userId(actor);
        String scope = request.scopeType() == null ? "" : request.scopeType().trim().toUpperCase();
        if (!SILENCE_SCOPES.contains(scope)) {
            throw new BusinessException(400, "静默范围只支持 GLOBAL / TASK");
        }
        LocalDateTime start = request.startsAt() == null ? LocalDateTime.now() : request.startsAt();
        LocalDateTime end = request.endsAt();
        if (end == null || end.isBefore(start)) {
            throw new BusinessException(400, "静默结束时间必须晚于开始时间");
        }
        if (end.isAfter(start.plusDays(7))) {
            throw new BusinessException(400, "静默窗口最长 7 天");
        }
        if (request.reason() == null || request.reason().isBlank()) {
            throw new BusinessException(400, "静默必须填写原因");
        }
        if ("TASK".equals(scope)) {
            if (request.scopeId() == null) {
                throw new BusinessException(400, "任务级静默必须指定任务");
            }
            Integer owned = jdbc.queryForObject("SELECT COUNT(*) FROM sentinel_task WHERE id=? AND user_id=?",
                    Integer.class, request.scopeId(), userId);
            if (owned == null || owned == 0) {
                throw new BusinessException(404, "哨兵任务不存在或无权限访问");
            }
        }

        // GLOBAL 超过 24 小时的非管理员申请需要审批：影响面大、时长长，不能一人说了算。
        boolean requiresApproval = "GLOBAL".equals(scope)
                && java.time.Duration.between(start, end).toHours() > 24
                && !"admin".equalsIgnoreCase(actor == null ? "" : String.valueOf(actor.role()));
        String status = requiresApproval ? "PENDING_APPROVAL" : "ACTIVE";

        // SEC-09：直接取本次插入主键，避免同用户并发创建静默时 MAX(id) 取到别人的记录。
        var keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("""
                    INSERT INTO sentinel_silence (scope_type, scope_id, reason, starts_at, ends_at, created_by, status)
                    VALUES (?,?,?,?,?,?,?)
                    """, new String[]{"id"});
            statement.setObject(1, scope);
            statement.setObject(2, request.scopeId());
            statement.setObject(3, request.reason().trim());
            statement.setObject(4, java.sql.Timestamp.valueOf(start));
            statement.setObject(5, java.sql.Timestamp.valueOf(end));
            statement.setObject(6, userId);
            statement.setObject(7, status);
            return statement;
        }, keys);
        long id = keys.getKey().longValue();
        if (!requiresApproval) {
            jdbc.update("UPDATE sentinel_silence SET approved_by=?, approved_at=? WHERE id=?",
                    userId, java.sql.Timestamp.valueOf(LocalDateTime.now()), id);
            syncExternalSilence(id, scope, request.scopeId(), start, end, request.reason().trim(), userId);
        }
        return silence(id, userId);
    }

    /**
     * 审批一条待生效的全局静默。
     *
     * <p>只有管理员可以审批；审批通过后才真正抑制告警，并尝试同步到外部平台。
     * 外部同步失败会如实记为 {@code FAILED}，不会因为"本地已生效"就宣称外部已静默。</p>
     */
    @Transactional
    public SilenceView approveSilence(SessionUser actor, long silenceId) {
        if (actor == null || !"admin".equalsIgnoreCase(String.valueOf(actor.role()))) {
            throw new BusinessException(403, "全局静默审批需要管理员权限");
        }
        SilenceRow row = requireSilence(silenceId);
        if (!"PENDING_APPROVAL".equals(row.status())) {
            throw new BusinessException(409, "该静默不在待审批状态");
        }
        LocalDateTime start = LocalDateTime.now();
        LocalDateTime end = row.endsAt();
        jdbc.update("UPDATE sentinel_silence SET status='ACTIVE', approved_by=?, approved_at=? WHERE id=? AND status='PENDING_APPROVAL'",
                actor.id(), java.sql.Timestamp.valueOf(start), silenceId);
        syncExternalSilence(silenceId, row.scopeType(), row.scopeId(),
                row.startsAt().isBefore(start) ? start : row.startsAt(), end, row.reason(), row.createdBy());
        return silence(silenceId, row.createdBy());
    }

    /**
     * 撤销静默。
     *
     * <p>先撤销外部静默：外部失败时本地记录保留并抛错，避免出现
     * "接口说撤销成功、外部平台还在静默"的假象。</p>
     */
    @Transactional
    public void cancelSilence(SessionUser actor, long silenceId) {
        long userId = userId(actor);
        SilenceRow row = requireSilence(silenceId);
        if (row.createdBy() != userId) {
            throw new BusinessException(404, "静默窗口不存在或无权限访问");
        }
        if (row.externalId() != null && !row.externalId().isBlank()) {
            try {
                silenceClient.expire(row.externalId());
            } catch (Exception e) {
                throw new BusinessException(502, "SILENCE_EXTERNAL_REVOKE_FAILED: "
                        + SentinelService.truncate(e.getMessage(), 200));
            }
        }
        int removed = jdbc.update("DELETE FROM sentinel_silence WHERE id=? AND created_by=?", silenceId, userId);
        if (removed == 0) {
            throw new BusinessException(404, "静默窗口不存在或无权限访问");
        }
    }

    /** 尝试写入外部平台；未配置或失败都只记录真实状态，不影响本地静默生效。 */
    private void syncExternalSilence(long id, String scope, Long scopeId, LocalDateTime startsAt,
                                     LocalDateTime endsAt, String reason, Long createdBy) {
        String externalId = null;
        String status;
        String error = null;
        if (!silenceClient.configured()) {
            status = "NOT_CONFIGURED";
        } else {
            try {
                externalId = silenceClient.create(scope, scopeId,
                        startsAt.atZone(java.time.ZoneId.systemDefault()).toInstant(),
                        endsAt.atZone(java.time.ZoneId.systemDefault()).toInstant(),
                        reason, String.valueOf(createdBy));
                status = "SYNCED";
            } catch (Exception e) {
                status = "FAILED";
                error = SentinelService.truncate(e.getMessage(), 500);
            }
        }
        jdbc.update("UPDATE sentinel_silence SET external_id=?, external_status=?, external_error=? WHERE id=?",
                externalId, status, error, id);
    }

    private SilenceRow requireSilence(long silenceId) {
        List<SilenceRow> rows = jdbc.query("""
                SELECT id, scope_type, scope_id, reason, starts_at, ends_at, created_by, status, external_id
                  FROM sentinel_silence WHERE id=?
                """, (rs, row) -> new SilenceRow(rs.getLong("id"), rs.getString("scope_type"),
                rs.getObject("scope_id", Long.class), rs.getString("reason"),
                rs.getTimestamp("starts_at").toLocalDateTime(),
                rs.getTimestamp("ends_at").toLocalDateTime(),
                rs.getObject("created_by", Long.class), rs.getString("status"), rs.getString("external_id")),
                silenceId);
        if (rows.isEmpty()) {
            throw new BusinessException(404, "静默窗口不存在或无权限访问");
        }
        return rows.get(0);
    }

    private SilenceView silence(long silenceId, Long createdBy) {
        List<SilenceView> rows = jdbc.query("""
                SELECT id, scope_type, scope_id, reason, starts_at, ends_at, created_by, status,
                       approved_by, external_status, external_error
                  FROM sentinel_silence WHERE id=? AND created_by=?
                """, (row, ignored) -> view(row), silenceId, createdBy);
        if (rows.isEmpty()) {
            throw new BusinessException(404, "静默窗口不存在或无权限访问");
        }
        return rows.get(0);
    }

    private static SilenceView view(ResultSet row) throws SQLException {
        LocalDateTime start = row.getTimestamp("starts_at").toLocalDateTime();
        LocalDateTime end = row.getTimestamp("ends_at").toLocalDateTime();
        String status = row.getString("status");
        LocalDateTime now = LocalDateTime.now();
        boolean active = "ACTIVE".equalsIgnoreCase(status)
                && !now.isBefore(start) && !now.isAfter(end);
        return new SilenceView(row.getLong("id"), row.getString("scope_type"),
                row.getObject("scope_id", Long.class), row.getString("reason"),
                instant(row, "starts_at"), instant(row, "ends_at"),
                row.getObject("created_by", Long.class), status,
                row.getObject("approved_by", Long.class), row.getString("external_status"),
                row.getString("external_error"), active);
    }

    private record SilenceRow(long id, String scopeType, Long scopeId, String reason,
                              LocalDateTime startsAt, LocalDateTime endsAt,
                              Long createdBy, String status, String externalId) {}

    /* ── 转派 / 升级 ─────────────────────────────────────────────────── */

    /** 转派给其他用户；被转派人必须存在且启用，避免转到死账号。 */
    @Transactional
    public void transfer(SessionUser actor, long alertId, long assigneeId, String note) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        Integer exists = jdbc.queryForObject("SELECT COUNT(*) FROM app_user WHERE id=? AND enabled=TRUE",
                Integer.class, assigneeId);
        if (exists == null || exists == 0) {
            throw new BusinessException(400, "被转派用户不存在或已停用");
        }
        jdbc.update("UPDATE sentinel_alert SET assignee_id=? WHERE id=?", assigneeId, alertId);
        recordEvent(alertId, userId, "TRANSFERRED", "转派给用户 " + assigneeId
                + (note == null || note.isBlank() ? "" : "：" + SentinelService.truncate(note, 300)));
    }

    /** 升级：只允许往上调级别，不允许借升级降级。 */
    @Transactional
    public String escalate(SessionUser actor, long alertId, String targetSeverity, String note) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);
        String current = jdbc.queryForObject("SELECT severity FROM sentinel_alert WHERE id=?",
                String.class, alertId);
        String target = targetSeverity == null ? "" : targetSeverity.trim().toUpperCase();
        int from = SEVERITY_ORDER.indexOf(current);
        int to = SEVERITY_ORDER.indexOf(target);
        if (to < 0) {
            throw new BusinessException(400, "目标级别只支持 P0-P3");
        }
        if (to <= from) {
            throw new BusinessException(400, "升级只能提高级别");
        }
        jdbc.update("UPDATE sentinel_alert SET severity=? WHERE id=?", target, alertId);
        recordEvent(alertId, userId, "ESCALATED", current + " -> " + target
                + (note == null || note.isBlank() ? "" : "：" + SentinelService.truncate(note, 300)));
        return target;
    }

    /* ── 通知死信 ─────────────────────────────────────────────────────── */

    /**
     * 把重试耗尽仍失败的投递标为死信。
     *
     * <p>死信不删除记录：通知失败本身就是故障信号，静默丢弃等于隐瞒。</p>
     */
    @Transactional
    public int sweepDeadLetters(int maxAttempts) {
        int limit = Math.max(1, maxAttempts);
        int marked = jdbc.update("""
                UPDATE sentinel_notification
                   SET dead_lettered=TRUE
                 WHERE status='failed' AND dead_lettered=FALSE AND attempts>=?
                """, limit);
        if (marked > 0) {
            log.warn("alert lifecycle dead-lettered {} notification(s)", marked);
        }
        return marked;
    }

    /** 对某条告警按既有投递记录重发一次（保留渠道与目标，不做重新配置）。 */
    @Transactional
    public Map<String, String> retryNotification(SessionUser actor, long alertId) {
        long userId = userId(actor);
        requireAlertVisible(alertId, userId);

        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT channel, target FROM sentinel_notification WHERE alert_id=? AND status='failed'", alertId);
        if (rows.isEmpty()) {
            throw new BusinessException(400, "该告警没有失败的投递记录");
        }
        StringBuilder channels = new StringBuilder();
        String webhookUrl = null;
        String emailTo = null;
        for (Map<String, Object> row : rows) {
            String channel = String.valueOf(row.get("channel"));
            if (channels.length() > 0) channels.append(',');
            channels.append(channel);
            if ("WEBHOOK".equalsIgnoreCase(channel)) {
                webhookUrl = (String) row.get("target");
            } else if ("EMAIL".equalsIgnoreCase(channel)) {
                emailTo = (String) row.get("target");
            }
        }
        String title = jdbc.queryForObject("SELECT title FROM sentinel_alert WHERE id=?", String.class, alertId);
        return notifier.deliver(alertId, userId, channels.toString(), webhookUrl, emailTo,
                title == null ? "告警重发" : title, null);
    }

    /* ── 内部 ─────────────────────────────────────────────────────────── */

    private void recordEvent(long alertId, Long actorId, String kind, String detail) {
        jdbc.update("INSERT INTO sentinel_alert_event(alert_id,actor_id,kind,detail) VALUES(?,?,?,?)",
                alertId, actorId, kind, SentinelService.truncate(detail, 800));
    }

    private void requireAlertVisible(long alertId, long userId) {
        Integer count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM sentinel_alert a
                  LEFT JOIN sentinel_task t ON t.id=a.task_id
                  LEFT JOIN sentinel_alert_rule r ON r.id=a.rule_id
                 WHERE a.id=? AND (t.user_id=? OR r.user_id=?)
                """, Integer.class, alertId, userId, userId);
        if (count == null || count == 0) {
            throw new BusinessException(404, "告警不存在或无权限访问");
        }
    }

    private static long userId(SessionUser actor) {
        if (actor == null) {
            throw new BusinessException(401, "未登录");
        }
        return actor.id();
    }

    private static String instant(ResultSet row, String column) throws SQLException {
        var value = row.getTimestamp(column);
        return value == null ? null : value.toInstant().toString();
    }

    /* ── 对外记录 ─────────────────────────────────────────────────────── */

    public record SilenceRequest(String scopeType, Long scopeId, String reason,
                                 LocalDateTime startsAt, LocalDateTime endsAt) {}

    public record SilenceView(long id, String scopeType, Long scopeId, String reason,
                              String startsAt, String endsAt, Long createdBy, String status,
                              Long approvedBy, String externalStatus, String externalError, boolean active) {}

    public record GroupView(String groupKey, String sampleTitle, long total, long active,
                            long closed, String maxSeverity, String lastFiredAt) {}
}
