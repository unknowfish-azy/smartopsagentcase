package com.smartops.service.modelconfig;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

/**
 * 模型网关控制面：配置版本、差异对比、发布闸门、灰度与审批。
 *
 * <p>工作区（group/route/connection 表）照常编辑，但不再直接影响线上路由；
 * 只有被发布的版本才会进入 {@link ModelConfigRegistry} 的内存快照。</p>
 *
 * <p>历史版本不可变：回滚是"以旧版本内容新建一个版本再发布"，
 * 不会改写历史记录，审计链始终完整。</p>
 */
@Slf4j
@Service
public class ModelConfigVersionService {

    private static final String STATUS_DRAFT = "DRAFT";
    private static final String STATUS_PENDING = "PENDING_APPROVAL";
    private static final String STATUS_REJECTED = "REJECTED";
    private static final String STATUS_ACTIVE = "ACTIVE";
    private static final String STATUS_SUPERSEDED = "SUPERSEDED";

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final ModelConfigGate gate;
    private final ModelConfigRegistry registry;
    private final ModelControlPlaneProperties properties;
    private final com.smartops.service.TeamNotificationService notifications;

    public ModelConfigVersionService(JdbcTemplate jdbc, ObjectMapper mapper,
                                     ModelConfigGate gate, ModelConfigRegistry registry,
                                     ModelControlPlaneProperties properties,
                                     com.smartops.service.TeamNotificationService notifications) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.gate = gate;
        this.registry = registry;
        this.properties = properties;
        this.notifications = notifications;
    }

    private record VersionRow(
            long id,
            int versionNo,
            String status,
            String summary,
            String snapshotJson,
            String diffJson,
            String gateReportJson,
            String contentHash,
            int rolloutPercent,
            Integer requestedPercent,
            String rejectionComment,
            Long createdBy,
            Long activatedBy,
            Instant createdAt,
            Instant activatedAt
    ) {}

    /* ── 查询 ─────────────────────────────────────────────── */

    public List<Map<String, Object>> list(int limit) {
        int size = Math.max(1, Math.min(limit, 200));
        return jdbc.query(
                "SELECT id,version_no,status,summary,content_hash,rollout_percent,requested_percent,"
                        + "created_by,activated_by,created_at,activated_at "
                        + "FROM model_gateway_config_version ORDER BY version_no DESC LIMIT " + size,
                (rs, n) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("id", rs.getLong("id"));
                    row.put("version", rs.getInt("version_no"));
                    row.put("status", rs.getString("status"));
                    row.put("summary", rs.getString("summary"));
                    row.put("contentHash", rs.getString("content_hash"));
                    row.put("rolloutPercent", rs.getInt("rollout_percent"));
                    row.put("requestedPercent", rs.getObject("requested_percent"));
                    row.put("createdBy", rs.getObject("created_by"));
                    row.put("activatedBy", rs.getObject("activated_by"));
                    row.put("createdAt", instant(rs.getTimestamp("created_at")));
                    row.put("activatedAt", instant(rs.getTimestamp("activated_at")));
                    return row;
                });
    }

    public Map<String, Object> get(long id) {
        VersionRow row = loadRow(id);
        if (row == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", row.id());
        out.put("version", row.versionNo());
        out.put("status", row.status());
        out.put("summary", row.summary());
        out.put("contentHash", row.contentHash());
        out.put("rolloutPercent", row.rolloutPercent());
        out.put("requestedPercent", row.requestedPercent());
        out.put("rejectionComment", row.rejectionComment());
        out.put("requiredApprovals", properties.getRequiredApprovals());
        out.put("approvers", properties.getApprovers());
        out.put("createdBy", row.createdBy());
        out.put("activatedBy", row.activatedBy());
        out.put("createdAt", instant(Timestamp.from(row.createdAt())));
        out.put("activatedAt", row.activatedAt() == null ? null : row.activatedAt().toString());
        out.put("snapshot", readJson(row.snapshotJson()));
        out.put("diff", readJson(row.diffJson()));
        out.put("gate", readJson(row.gateReportJson()));
        out.put("approvals", approvals(row.id()));
        return out;
    }

    /** 当前生效版本摘要，供普通用户与健康检查查看。 */
    public Map<String, Object> currentEffective() {
        VersionRow stable = stableRow();
        VersionRow gray = canaryRow();
        Map<String, Object> out = new LinkedHashMap<>();
        if (stable == null && gray == null) {
            out.put("version", 0);
            out.put("status", "UNPUBLISHED");
            out.put("summary", "尚未发布任何配置版本");
            out.put("requiredApprovals", properties.getRequiredApprovals());
            out.put("approvers", properties.getApprovers());
            return out;
        }
        VersionRow primary = stable != null ? stable : gray;
        out.put("version", primary.versionNo());
        out.put("status", stable != null ? STATUS_ACTIVE : "CANARY_ONLY");
        out.put("summary", primary.summary());
        out.put("activatedBy", primary.activatedBy());
        out.put("activatedAt", primary.activatedAt() == null ? null : primary.activatedAt().toString());
        out.put("canaryVersion", gray == null ? null : gray.versionNo());
        out.put("canaryPercent", gray == null ? null : gray.rolloutPercent());
        out.put("requiredApprovals", properties.getRequiredApprovals());
        out.put("approvers", properties.getApprovers());
        return out;
    }

    /* ── 灰度健康对比 ─────────────────────────────────────── */

    /**
     * 按配置版本聚合窗口内的真实调用，比较灰度与全量的成功率/延迟，给出转全量建议。
     *
     * <p>只依据已落库的调用元数据，不做预测；样本不足时明确返回 INSUFFICIENT_DATA。</p>
     */
    public Map<String, Object> compare(long id, int minutes) {
        VersionRow target = loadRow(id);
        if (target == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        int window = Math.max(5, Math.min(1440, minutes));
        Timestamp since = Timestamp.from(Instant.now().minusSeconds(window * 60L));
        List<Metric> metrics = jdbc.query(
                "SELECT config_version,COUNT(*) calls,"
                        + "SUM(CASE WHEN status IN ('SUCCESS','CACHE_HIT') THEN 1 ELSE 0 END) ok,"
                        + "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) failed,"
                        + "AVG(duration_ms) avg_ms,MAX(duration_ms) max_ms "
                        + "FROM model_gateway_invocation WHERE created_at>=? AND config_version IS NOT NULL "
                        + "GROUP BY config_version",
                (rs, n) -> new Metric(rs.getInt("config_version"), rs.getLong("calls"), rs.getLong("ok"),
                        rs.getLong("failed"), rs.getDouble("avg_ms"), rs.getLong("max_ms")), since);

        Metric canary = metricFor(metrics, target.versionNo());
        VersionRow stable = stableRow();
        Metric baseline = stable == null || stable.versionNo() == target.versionNo()
                ? null : metricFor(metrics, stable.versionNo());

        List<String> reasons = new ArrayList<>();
        String verdict;
        if (stable == null || stable.versionNo() == target.versionNo()) {
            verdict = "NOT_CANARY";
            reasons.add("目标版本不是灰度版本，没有可对比的全量版本");
        } else if (canary == null || canary.calls() < MIN_SAMPLES) {
            verdict = "INSUFFICIENT_DATA";
            reasons.add("灰度样本不足：" + window + " 分钟内 " + (canary == null ? 0 : canary.calls())
                    + " 次调用，至少需要 " + MIN_SAMPLES + " 次");
        } else if (baseline == null || baseline.calls() < MIN_SAMPLES) {
            verdict = "INSUFFICIENT_DATA";
            reasons.add("全量样本不足：v" + stable.versionNo() + " 在窗口内仅 "
                    + (baseline == null ? 0 : baseline.calls()) + " 次调用，至少需要 " + MIN_SAMPLES + " 次");
        } else {
            double canaryRate = rate(canary);
            double baselineRate = rate(baseline);
            if (canaryRate + 5 < baselineRate) {
                verdict = "ROLLBACK";
                reasons.add("灰度成功率 " + canaryRate + "% 低于全量 " + baselineRate + "% 超过 5 个百分点");
            } else if (canaryRate < 80) {
                verdict = "ROLLBACK";
                reasons.add("灰度成功率 " + canaryRate + "% 低于 80% 底线");
            } else if (baseline.avgLatency() > 0 && canary.avgLatency() > baseline.avgLatency() * 1.5) {
                verdict = "HOLD";
                reasons.add("灰度平均延迟 " + round(canary.avgLatency()) + " ms 超过全量 "
                        + round(baseline.avgLatency()) + " ms 的 1.5 倍");
            } else {
                verdict = "PROMOTE";
                reasons.add("灰度成功率 " + canaryRate + "% 与全量 " + baselineRate + "% 持平或更好，可评估转全量");
            }
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("versionId", target.id());
        out.put("version", target.versionNo());
        out.put("status", target.status());
        out.put("rolloutPercent", target.rolloutPercent());
        out.put("stableVersion", stable == null ? null : stable.versionNo());
        out.put("windowMinutes", window);
        out.put("canary", metricView(canary));
        out.put("stable", metricView(baseline));
        out.put("verdict", verdict);
        out.put("reasons", reasons);
        return out;
    }

    private static final int MIN_SAMPLES = 20;

    private record Metric(int version, long calls, long success, long failed, double avgLatency, long maxLatency) {
    }

    private Metric metricFor(List<Metric> metrics, int version) {
        return metrics.stream().filter(item -> item.version() == version).findFirst().orElse(null);
    }

    private Map<String, Object> metricView(Metric metric) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("calls", metric == null ? 0L : metric.calls());
        out.put("successCalls", metric == null ? 0L : metric.success());
        out.put("failedCalls", metric == null ? 0L : metric.failed());
        out.put("successRate", metric == null ? 0.0 : rate(metric));
        out.put("avgLatencyMs", metric == null ? 0L : round(metric.avgLatency()));
        out.put("maxLatencyMs", metric == null ? 0L : metric.maxLatency());
        return out;
    }

    private double rate(Metric metric) {
        return metric.calls() == 0 ? 0.0 : round(metric.success() * 100.0 / metric.calls());
    }

    private double round(double value) {
        return Math.round(value * 10.0) / 10.0;
    }

    /* ── 草稿 ─────────────────────────────────────────────── */

    /** 以当前工作区内容生成待发布草稿，并计算相对生效版本的差异。 */
    @Transactional
    public synchronized Map<String, Object> createDraft(long actorUserId, String summary) {
        String text = summary == null ? "" : summary.trim();
        if (text.length() > 500) {
            throw new BusinessException(400, "变更说明不能超过 500 字");
        }
        ModelConfigSnapshot draft = snapshotFromWorkingCopy(nextVersionNo());
        ModelConfigSnapshot active = activeSnapshot();
        String contentHash = contentHash(draft);
        if (active != null && contentHash.equals(contentHash(active))) {
            throw new BusinessException(409, "工作区与当前生效版本一致，没有可发布的变更");
        }
        Map<String, Object> diff = diff(active == null ? emptySnapshot() : active, draft);
        ModelConfigGate.Report precheck = gate.evaluate(draft);
        long id = nextId();
        jdbc.update(
                "INSERT INTO model_gateway_config_version"
                        + "(id,version_no,status,summary,snapshot_json,diff_json,gate_report_json,content_hash,created_by) "
                        + "VALUES(?,?,?,?,?,?,?,?,?)",
                id, draft.version(), STATUS_DRAFT, text.isBlank() ? "未填写变更说明" : text,
                write(draft), write(diff), write(precheck), contentHash, actorUserId);
        log.info("模型网关配置草稿已创建：v{}，创建人 {}，变更 {} 项",
                draft.version(), actorUserId, diff.get("count"));
        return get(id);
    }

    /* ── 发布 / 灰度 / 审批 / 回滚 ────────────────────────── */

    /** 全量发布（无审批要求时使用）。 */
    @Transactional
    public synchronized Map<String, Object> activate(long id, long actorUserId) {
        return activate(id, actorUserId, 100);
    }

    /** 按比例发布：percent<100 时保留现有全量版本，新版本只接 percent% 流量。 */
    @Transactional
    public synchronized Map<String, Object> activate(long id, long actorUserId, int percent) {
        VersionRow row = loadRow(id);
        if (row == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        if (!STATUS_DRAFT.equals(row.status())) {
            throw new BusinessException(409, "只有草稿版本可以直接发布");
        }
        if (properties.getRequiredApprovals() > 0) {
            throw new BusinessException(409,
                    "该配置需要 " + properties.getRequiredApprovals() + " 级审批，请先提交审批");
        }
        return doActivate(row, actorUserId, percent);
    }

    /** 提交审批，可同时申请灰度比例。 */
    @Transactional
    public synchronized Map<String, Object> submit(long id, long actorUserId, int percent) {
        VersionRow row = loadRow(id);
        if (row == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        if (!STATUS_DRAFT.equals(row.status())) {
            throw new BusinessException(409, "只有草稿版本可以提交审批");
        }
        if (properties.getRequiredApprovals() <= 0) {
            throw new BusinessException(409, "当前部署未开启审批，可直接发布");
        }
        if (percent < 1 || percent > 100) {
            throw new BusinessException(400, "灰度比例必须在 1-100 之间");
        }
        if (percent < 100 && stableRow() == null) {
            throw new BusinessException(409, "灰度发布需要已有全量生效版本");
        }
        ModelConfigGate.Report report = gate.evaluate(parseSnapshot(row.snapshotJson()));
        if (!report.passed()) {
            jdbc.update("UPDATE model_gateway_config_version SET gate_report_json=? WHERE id=?",
                    write(report), id);
            throw new BusinessException(409, "配置校验未通过：" + String.join("；", report.errors()));
        }
        jdbc.update(
                "UPDATE model_gateway_config_version SET status=?,requested_percent=?,submitted_by=?,"
                        + "submitted_at=CURRENT_TIMESTAMP,gate_report_json=?,rejection_comment=NULL WHERE id=?",
                STATUS_PENDING, percent, actorUserId, write(report), id);
        log.info("模型网关配置已提交审批：v{}，申请人 {}，申请灰度 {}%", row.versionNo(), actorUserId, percent);
        String message = "模型配置 v" + row.versionNo() + " 待审批（申请灰度 " + percent + "%）：" + row.summary();
        afterCommit(() -> notifyApprovers(actorUserId, id, message));
        return get(id);
    }

    /** 审批通过；达到配置的审批级数后自动发布（按申请的比例）。 */
    @Transactional
    public synchronized Map<String, Object> approve(long id, long approverId, String comment) {
        VersionRow row = loadRow(id);
        if (row == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        if (!STATUS_PENDING.equals(row.status())) {
            throw new BusinessException(409, "只有待审批版本可以审批");
        }
        if (Objects.equals(row.createdBy(), approverId)) {
            throw new BusinessException(409, "不能审批自己创建的配置版本");
        }
        requireApprover(approverId);
        insertApproval(id, approverId, "APPROVE", comment);
        int required = Math.max(1, properties.getRequiredApprovals());
        Integer approved = jdbc.queryForObject(
                "SELECT COUNT(DISTINCT approver_id) FROM model_gateway_config_approval "
                        + "WHERE version_id=? AND action='APPROVE'", Integer.class, id);
        int count = approved == null ? 0 : approved;
        if (count < required) {
            log.info("模型网关配置审批进度：v{} {}/{}", row.versionNo(), count, required);
            return get(id);
        }
        jdbc.update("UPDATE model_gateway_config_version SET approved_at=CURRENT_TIMESTAMP WHERE id=?", id);
        int percent = row.requestedPercent() == null ? 100 : row.requestedPercent();
        log.info("模型网关配置审批完成：v{}，开始发布 {}%", row.versionNo(), percent);
        String message = "模型配置 v" + row.versionNo() + " 已通过审批并" + (percent < 100 ? "按 " + percent + "% 灰度" : "全量") + "生效";
        afterCommit(() -> notifyUser(row.createdBy(), id, message));
        return doActivate(row, approverId, percent);
    }

    @Transactional
    public synchronized Map<String, Object> reject(long id, long approverId, String comment) {
        VersionRow row = loadRow(id);
        if (row == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        if (!STATUS_PENDING.equals(row.status())) {
            throw new BusinessException(409, "只有待审批版本可以驳回");
        }
        if (Objects.equals(row.createdBy(), approverId)) {
            throw new BusinessException(409, "不能审批自己创建的配置版本");
        }
        requireApprover(approverId);
        insertApproval(id, approverId, "REJECT", comment);
        jdbc.update("UPDATE model_gateway_config_version SET status=?,rejection_comment=? WHERE id=?",
                STATUS_REJECTED, trim(comment), id);
        log.info("模型网关配置被驳回：v{}，驳回人 {}", row.versionNo(), approverId);
        String reason = trim(comment);
        String message = "模型配置 v" + row.versionNo() + " 被驳回" + (reason == null ? "" : "：" + reason);
        afterCommit(() -> notifyUser(row.createdBy(), id, message));
        return get(id);
    }

    /** 灰度转全量：把灰度版本提到 100%，原全量版本退役。 */
    @Transactional
    public synchronized Map<String, Object> promote(long id, long actorUserId) {
        VersionRow row = loadRow(id);
        if (row == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        if (!STATUS_ACTIVE.equals(row.status()) || row.rolloutPercent() >= 100) {
            throw new BusinessException(409, "只有灰度中的版本可以转全量");
        }
        jdbc.update("UPDATE model_gateway_config_version SET status=? "
                        + "WHERE status=? AND rollout_percent>=100",
                STATUS_SUPERSEDED, STATUS_ACTIVE);
        jdbc.update("UPDATE model_gateway_config_version SET rollout_percent=100,activated_by=?,"
                + "activated_at=CURRENT_TIMESTAMP WHERE id=?", actorUserId, id);
        refreshAfterCommit();
        log.info("模型网关灰度版本已转全量：v{}，操作人 {}", row.versionNo(), actorUserId);
        return get(id);
    }

    /**
     * 回滚：以历史内容新建版本并全量发布。
     *
     * <p>回滚是故障处置动作，不受审批级数限制，但同样经过闸门校验，
     * 并完整记录操作人与被回滚的目标版本。</p>
     */
    @Transactional
    public synchronized Map<String, Object> rollback(long id, long actorUserId, String reason) {
        VersionRow source = loadRow(id);
        if (source == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        if (STATUS_ACTIVE.equals(source.status())) {
            throw new BusinessException(409, "该版本已是当前生效版本");
        }
        ModelConfigSnapshot sourceSnapshot = parseSnapshot(source.snapshotJson());
        int version = nextVersionNo();
        ModelConfigSnapshot rollback = new ModelConfigSnapshot(
                version, Instant.now().toString(), sourceSnapshot.groups(), sourceSnapshot.connections());
        ModelConfigSnapshot active = activeSnapshot();
        Map<String, Object> diff = diff(active == null ? emptySnapshot() : active, rollback);
        ModelConfigGate.Report report = gate.evaluate(rollback);
        String text = reason == null || reason.isBlank()
                ? "回滚至 v" + source.versionNo()
                : "回滚至 v" + source.versionNo() + "：" + reason.trim();
        long newId = nextId();
        jdbc.update(
                "INSERT INTO model_gateway_config_version"
                        + "(id,version_no,status,summary,snapshot_json,diff_json,gate_report_json,content_hash,created_by) "
                        + "VALUES(?,?,?,?,?,?,?,?,?)",
                newId, version, STATUS_DRAFT, text.length() > 500 ? text.substring(0, 500) : text,
                write(rollback), write(diff), write(report), contentHash(rollback), actorUserId);
        return doActivate(loadRow(newId), actorUserId, 100);
    }

    @Transactional
    public synchronized void delete(long id) {
        VersionRow row = loadRow(id);
        if (row == null) {
            throw new BusinessException(404, "配置版本不存在");
        }
        if (!STATUS_DRAFT.equals(row.status()) && !STATUS_REJECTED.equals(row.status())) {
            throw new BusinessException(409, "只能删除草稿或已驳回的版本");
        }
        jdbc.update("DELETE FROM model_gateway_config_approval WHERE version_id=?", id);
        jdbc.update("DELETE FROM model_gateway_config_version WHERE id=?", id);
    }

    /* ── 发布执行 ─────────────────────────────────────────── */

    private Map<String, Object> doActivate(VersionRow row, long actorUserId, int percent) {
        if (percent < 1 || percent > 100) {
            throw new BusinessException(400, "灰度比例必须在 1-100 之间");
        }
        ModelConfigSnapshot snapshot = parseSnapshot(row.snapshotJson());
        ModelConfigGate.Report report = gate.evaluate(snapshot);
        if (!report.passed()) {
            jdbc.update("UPDATE model_gateway_config_version SET gate_report_json=? WHERE id=?",
                    write(report), row.id());
            throw new BusinessException(409, "配置校验未通过：" + String.join("；", report.errors()));
        }
        VersionRow baseline = activeRow();
        if (baseline != null && baseline.contentHash().equals(row.contentHash())) {
            throw new BusinessException(409, "该版本内容与当前生效版本一致，无需重复发布");
        }
        if (percent < 100 && stableRow() == null) {
            throw new BusinessException(409, "灰度发布需要已有全量生效版本");
        }
        if (percent >= 100) {
            jdbc.update("UPDATE model_gateway_config_version SET status=? WHERE status=?",
                    STATUS_SUPERSEDED, STATUS_ACTIVE);
        } else {
            jdbc.update("UPDATE model_gateway_config_version SET status=? "
                            + "WHERE status=? AND rollout_percent<100",
                    STATUS_SUPERSEDED, STATUS_ACTIVE);
        }
        jdbc.update(
                "UPDATE model_gateway_config_version SET status=?,rollout_percent=?,requested_percent=?,"
                        + "activated_by=?,activated_at=CURRENT_TIMESTAMP,gate_report_json=? WHERE id=?",
                STATUS_ACTIVE, percent, percent, actorUserId, write(report), row.id());
        refreshAfterCommit();
        log.info("模型网关配置已发布：v{}，灰度 {}%，操作人 {}", row.versionNo(), percent, actorUserId);
        return get(row.id());
    }

    private void insertApproval(long versionId, long approverId, String action, String comment) {
        try {
            jdbc.update("INSERT INTO model_gateway_config_approval"
                            + "(id,version_id,approver_id,action,comment) VALUES(?,?,?,?,?)",
                    nextId(), versionId, approverId, action, trim(comment));
        } catch (DuplicateKeyException ex) {
            throw new BusinessException(409, "你已经审批过该版本");
        }
    }

    private List<Map<String, Object>> approvals(long versionId) {
        return jdbc.query(
                "SELECT approver_id,action,comment,created_at FROM model_gateway_config_approval "
                        + "WHERE version_id=? ORDER BY id",
                (rs, n) -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("approverId", rs.getObject("approver_id"));
                    item.put("action", rs.getString("action"));
                    item.put("comment", rs.getString("comment"));
                    item.put("createdAt", instant(rs.getTimestamp("created_at")));
                    return item;
                }, versionId);
    }

    /* ── 工作区快照 ───────────────────────────────────────── */

    private ModelConfigSnapshot snapshotFromWorkingCopy(int version) {
        Map<Long, List<ModelConfigSnapshot.Route>> routesByGroup = new HashMap<>();
        jdbc.query(
                "SELECT id,group_id,connection_id,priority,weight,enabled FROM model_gateway_route ORDER BY id",
                (rs, n) -> {
                    routesByGroup.computeIfAbsent(rs.getLong("group_id"), k -> new ArrayList<>())
                            .add(new ModelConfigSnapshot.Route(
                                    rs.getLong("id"), rs.getLong("connection_id"),
                                    rs.getInt("priority"), rs.getInt("weight"), rs.getBoolean("enabled")));
                    return null;
                });

        List<ModelConfigSnapshot.Group> groups = jdbc.query(
                "SELECT id,slug,name,owner_user_id,scope,enabled,route_mode,default_capability,"
                        + "request_limit_24h,token_limit_24h FROM model_gateway_group ORDER BY id",
                (rs, n) -> new ModelConfigSnapshot.Group(
                        rs.getLong("id"),
                        rs.getString("slug"),
                        rs.getString("name"),
                        longOrNull(rs.getObject("owner_user_id")),
                        rs.getString("scope"),
                        rs.getBoolean("enabled"),
                        rs.getString("route_mode"),
                        rs.getString("default_capability"),
                        longOrNull(rs.getObject("request_limit_24h")),
                        longOrNull(rs.getObject("token_limit_24h")),
                        List.copyOf(routesByGroup.getOrDefault(rs.getLong("id"), List.of()))
                ));

        List<ModelConfigSnapshot.Connection> connections = jdbc.query(
                "SELECT id,user_id,name,model_name,capabilities,enabled FROM model_connections ORDER BY id",
                (rs, n) -> new ModelConfigSnapshot.Connection(
                        rs.getLong("id"),
                        longOrNull(rs.getObject("user_id")),
                        rs.getString("name"),
                        rs.getString("model_name"),
                        parseCapabilities(rs.getString("capabilities")),
                        rs.getBoolean("enabled")
                ));

        return new ModelConfigSnapshot(version, Instant.now().toString(), groups, connections);
    }

    /* ── 差异计算 ─────────────────────────────────────────── */

    private Map<String, Object> diff(ModelConfigSnapshot base, ModelConfigSnapshot target) {
        List<Map<String, Object>> changes = new ArrayList<>();
        Map<String, ModelConfigSnapshot.Group> baseGroups = indexGroups(base);
        Map<String, ModelConfigSnapshot.Group> targetGroups = indexGroups(target);

        Set<String> slugs = new TreeSet<>();
        slugs.addAll(baseGroups.keySet());
        slugs.addAll(targetGroups.keySet());
        for (String slug : slugs) {
            ModelConfigSnapshot.Group before = baseGroups.get(slug);
            ModelConfigSnapshot.Group after = targetGroups.get(slug);
            if (before == null) {
                changes.add(Map.of("type", "GROUP_ADDED", "key", slug));
                continue;
            }
            if (after == null) {
                changes.add(Map.of("type", "GROUP_REMOVED", "key", slug));
                continue;
            }
            List<String> fields = new ArrayList<>();
            addIfChanged(fields, "name", before.name(), after.name());
            addIfChanged(fields, "enabled", before.enabled(), after.enabled());
            addIfChanged(fields, "routeMode", before.routeMode(), after.routeMode());
            addIfChanged(fields, "defaultCapability", before.defaultCapability(), after.defaultCapability());
            addIfChanged(fields, "requestLimit24h", before.requestLimit24h(), after.requestLimit24h());
            addIfChanged(fields, "tokenLimit24h", before.tokenLimit24h(), after.tokenLimit24h());
            if (!fields.isEmpty()) {
                Map<String, Object> change = new LinkedHashMap<>();
                change.put("type", "GROUP_CHANGED");
                change.put("key", slug);
                change.put("fields", fields);
                changes.add(change);
            }
            changes.addAll(diffRoutes(slug, before, after));
        }

        Map<Long, ModelConfigSnapshot.Connection> baseConnections = indexConnections(base);
        Map<Long, ModelConfigSnapshot.Connection> targetConnections = indexConnections(target);
        Set<Long> connectionIds = new TreeSet<>();
        connectionIds.addAll(baseConnections.keySet());
        connectionIds.addAll(targetConnections.keySet());
        for (Long connectionId : connectionIds) {
            ModelConfigSnapshot.Connection before = baseConnections.get(connectionId);
            ModelConfigSnapshot.Connection after = targetConnections.get(connectionId);
            if (before == null) {
                changes.add(Map.of("type", "CONNECTION_ADDED", "key", String.valueOf(connectionId)));
                continue;
            }
            if (after == null) {
                changes.add(Map.of("type", "CONNECTION_REMOVED", "key", String.valueOf(connectionId)));
                continue;
            }
            List<String> fields = new ArrayList<>();
            addIfChanged(fields, "modelName", before.modelName(), after.modelName());
            addIfChanged(fields, "capabilities", before.capabilities(), after.capabilities());
            addIfChanged(fields, "enabled", before.enabled(), after.enabled());
            if (!fields.isEmpty()) {
                Map<String, Object> change = new LinkedHashMap<>();
                change.put("type", "CONNECTION_CHANGED");
                change.put("key", String.valueOf(connectionId));
                change.put("fields", fields);
                changes.add(change);
            }
        }

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("baseVersion", base.version());
        out.put("targetVersion", target.version());
        out.put("count", changes.size());
        out.put("changes", changes);
        return out;
    }

    private List<Map<String, Object>> diffRoutes(String slug, ModelConfigSnapshot.Group before,
                                                 ModelConfigSnapshot.Group after) {
        List<Map<String, Object>> changes = new ArrayList<>();
        Map<Long, ModelConfigSnapshot.Route> baseRoutes = indexRoutes(before);
        Map<Long, ModelConfigSnapshot.Route> targetRoutes = indexRoutes(after);
        Set<Long> ids = new TreeSet<>();
        ids.addAll(baseRoutes.keySet());
        ids.addAll(targetRoutes.keySet());
        for (Long routeId : ids) {
            ModelConfigSnapshot.Route beforeRoute = baseRoutes.get(routeId);
            ModelConfigSnapshot.Route afterRoute = targetRoutes.get(routeId);
            if (beforeRoute == null) {
                changes.add(Map.of("type", "ROUTE_ADDED", "key", slug + "#" + routeId));
                continue;
            }
            if (afterRoute == null) {
                changes.add(Map.of("type", "ROUTE_REMOVED", "key", slug + "#" + routeId));
                continue;
            }
            List<String> fields = new ArrayList<>();
            addIfChanged(fields, "connectionId", beforeRoute.connectionId(), afterRoute.connectionId());
            addIfChanged(fields, "priority", beforeRoute.priority(), afterRoute.priority());
            addIfChanged(fields, "weight", beforeRoute.weight(), afterRoute.weight());
            addIfChanged(fields, "enabled", beforeRoute.enabled(), afterRoute.enabled());
            if (!fields.isEmpty()) {
                Map<String, Object> change = new LinkedHashMap<>();
                change.put("type", "ROUTE_CHANGED");
                change.put("key", slug + "#" + routeId);
                change.put("fields", fields);
                changes.add(change);
            }
        }
        return changes;
    }

    private void addIfChanged(List<String> fields, String name, Object before, Object after) {
        if (!Objects.equals(before, after)) {
            fields.add(name);
        }
    }

    private ModelConfigSnapshot emptySnapshot() {
        return new ModelConfigSnapshot(0, Instant.now().toString(), List.of(), List.of());
    }

    private Map<String, ModelConfigSnapshot.Group> indexGroups(ModelConfigSnapshot snapshot) {
        Map<String, ModelConfigSnapshot.Group> out = new HashMap<>();
        if (snapshot.groups() != null) {
            snapshot.groups().forEach(g -> out.put(g.slug(), g));
        }
        return out;
    }

    private Map<Long, ModelConfigSnapshot.Connection> indexConnections(ModelConfigSnapshot snapshot) {
        Map<Long, ModelConfigSnapshot.Connection> out = new HashMap<>();
        if (snapshot.connections() != null) {
            snapshot.connections().forEach(c -> out.put(c.id(), c));
        }
        return out;
    }

    private Map<Long, ModelConfigSnapshot.Route> indexRoutes(ModelConfigSnapshot.Group group) {
        Map<Long, ModelConfigSnapshot.Route> out = new HashMap<>();
        if (group.routes() != null) {
            group.routes().forEach(r -> out.put(r.id(), r));
        }
        return out;
    }

    /* ── 审批人范围与通知 ──────────────────────────────────── */

    /** 配置了审批人名单时，只有名单内的账号可以审批。 */
    private void requireApprover(long userId) {
        List<Long> allowed = approverUserIds();
        if (!allowed.isEmpty() && !allowed.contains(userId)) {
            throw new BusinessException(403, "当前账号不在模型配置审批人名单内");
        }
    }

    private List<Long> approverUserIds() {
        List<String> names = properties.getApprovers();
        if (names == null || names.isEmpty()) {
            return List.of();
        }
        String placeholders = String.join(",", java.util.Collections.nCopies(names.size(), "?"));
        return jdbc.query("SELECT id FROM app_user WHERE username IN (" + placeholders + ")",
                (rs, n) -> rs.getLong(1), names.toArray());
    }

    /** 未配置审批人时通知所有启用的管理员，排除申请人自己。 */
    private void notifyApprovers(long submitterId, long versionId, String message) {
        List<Long> targets = approverUserIds();
        if (targets.isEmpty()) {
            targets = jdbc.query("SELECT id FROM app_user WHERE role='admin' AND enabled=TRUE AND id<>?",
                    (rs, n) -> rs.getLong(1), submitterId);
        }
        targets.stream()
                .filter(id -> !Objects.equals(id, submitterId))
                .forEach(id -> notifyUser(id, versionId, message));
    }

    private void notifyUser(Long userId, long versionId, String message) {
        if (userId == null) {
            return;
        }
        String text = message.length() > 500 ? message.substring(0, 497) + "..." : message;
        try {
            notifications.notifyUser(userId, null, "MODEL_CONFIG_APPROVAL", "model-config:" + versionId, text);
        } catch (RuntimeException ex) {
            log.warn("模型配置审批通知写入失败：user {} version {}", userId, versionId);
        }
    }

    /** 通知只在事务提交后发送，避免回滚时产生误导性消息。 */
    private void afterCommit(Runnable task) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    task.run();
                }
            });
        } else {
            task.run();
        }
    }

    /* ── 内部工具 ─────────────────────────────────────────── */

    private static final String ROW_COLUMNS =
            "SELECT id,version_no,status,summary,snapshot_json,diff_json,gate_report_json,content_hash,"
                    + "rollout_percent,requested_percent,rejection_comment,created_by,activated_by,created_at,activated_at "
                    + "FROM model_gateway_config_version ";

    private VersionRow loadRow(long id) {
        return jdbc.query(ROW_COLUMNS + "WHERE id=?", (rs, n) -> toRow(rs), id)
                .stream().findFirst().orElse(null);
    }

    /** 最新生效版本（含灰度），用于差异对比与重复发布判断。 */
    private VersionRow activeRow() {
        return jdbc.query(ROW_COLUMNS + "WHERE status=? ORDER BY version_no DESC LIMIT 1",
                (rs, n) -> toRow(rs), STATUS_ACTIVE).stream().findFirst().orElse(null);
    }

    private VersionRow stableRow() {
        return jdbc.query(ROW_COLUMNS + "WHERE status=? AND rollout_percent>=100 "
                        + "ORDER BY version_no DESC LIMIT 1",
                (rs, n) -> toRow(rs), STATUS_ACTIVE).stream().findFirst().orElse(null);
    }

    private VersionRow canaryRow() {
        return jdbc.query(ROW_COLUMNS + "WHERE status=? AND rollout_percent<100 "
                        + "ORDER BY version_no DESC LIMIT 1",
                (rs, n) -> toRow(rs), STATUS_ACTIVE).stream().findFirst().orElse(null);
    }

    private VersionRow toRow(ResultSet rs) throws SQLException {
        Timestamp activated = rs.getTimestamp("activated_at");
        return new VersionRow(
                rs.getLong("id"),
                rs.getInt("version_no"),
                rs.getString("status"),
                rs.getString("summary"),
                rs.getString("snapshot_json"),
                rs.getString("diff_json"),
                rs.getString("gate_report_json"),
                rs.getString("content_hash"),
                rs.getInt("rollout_percent"),
                rs.getObject("requested_percent") == null ? null : rs.getInt("requested_percent"),
                rs.getString("rejection_comment"),
                longOrNull(rs.getObject("created_by")),
                longOrNull(rs.getObject("activated_by")),
                rs.getTimestamp("created_at").toInstant(),
                activated == null ? null : activated.toInstant()
        );
    }

    private ModelConfigSnapshot activeSnapshot() {
        VersionRow active = activeRow();
        return active == null ? null : parseSnapshot(active.snapshotJson());
    }

    private int nextVersionNo() {
        Integer max = jdbc.queryForObject(
                "SELECT COALESCE(MAX(version_no),0) FROM model_gateway_config_version", Integer.class);
        return (max == null ? 0 : max) + 1;
    }

    private String contentHash(ModelConfigSnapshot snapshot) {
        Map<String, Object> content = new LinkedHashMap<>();
        content.put("groups", snapshot.groups());
        content.put("connections", snapshot.connections());
        return sha256(write(content));
    }

    private ModelConfigSnapshot parseSnapshot(String json) {
        try {
            return mapper.readValue(json, ModelConfigSnapshot.class);
        } catch (Exception ex) {
            throw new BusinessException(500, "配置快照解析失败");
        }
    }

    private Object readJson(String json) {
        if (json == null || json.isBlank()) {
            return null;
        }
        try {
            JsonNode node = mapper.readTree(json);
            return node;
        } catch (Exception ex) {
            return json;
        }
    }

    private String write(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (Exception ex) {
            throw new IllegalStateException("配置序列化失败", ex);
        }
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static Long longOrNull(Object value) {
        return value instanceof Number number ? number.longValue() : null;
    }

    private static String instant(java.sql.Timestamp value) {
        return value == null ? null : value.toInstant().toString();
    }

    private static String trim(String value) {
        if (value == null) {
            return null;
        }
        String text = value.trim();
        return text.length() > 500 ? text.substring(0, 500) : text;
    }

    private List<String> parseCapabilities(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            JsonNode node = mapper.readTree(json);
            if (!node.isArray()) {
                return List.of();
            }
            List<String> out = new ArrayList<>();
            node.forEach(item -> out.add(item.asText()));
            return List.copyOf(out);
        } catch (Exception ex) {
            return List.of();
        }
    }

    private void refreshAfterCommit() {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    registry.refreshIfChanged();
                }
            });
            return;
        }
        registry.refreshIfChanged();
    }

    private static long nextId() {
        return java.util.concurrent.ThreadLocalRandom.current().nextLong(1, Long.MAX_VALUE);
    }
}
