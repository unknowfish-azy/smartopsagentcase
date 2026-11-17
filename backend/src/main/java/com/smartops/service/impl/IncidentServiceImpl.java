package com.smartops.service.impl;

import com.smartops.dto.IncidentAssignRequest;
import com.smartops.dto.IncidentCloseRequest;
import com.smartops.dto.IncidentCommentRequest;
import com.smartops.dto.IncidentCreateRequest;
import com.smartops.dto.IncidentRelationRequest;
import com.smartops.dto.IncidentUpdateRequest;
import com.smartops.entity.Incident;
import com.smartops.entity.IncidentEvent;
import com.smartops.entity.IncidentRelation;
import com.smartops.entity.SentinelAlertRef;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.IncidentEventMapper;
import com.smartops.mapper.IncidentMapper;
import com.smartops.mapper.IncidentRelationMapper;
import com.smartops.mapper.SentinelAlertRefMapper;
import com.smartops.module.incident.IncidentEventKind;
import com.smartops.module.incident.IncidentRelationType;
import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentSource;
import com.smartops.module.incident.IncidentStatus;
import com.smartops.service.IncidentService;
import com.smartops.vo.IncidentContractDraftVO;
import com.smartops.vo.IncidentEventVO;
import com.smartops.vo.IncidentRelationVO;
import com.smartops.vo.IncidentVO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Transactional
public class IncidentServiceImpl implements IncidentService {

    private final IncidentMapper incidentMapper;
    private final IncidentEventMapper incidentEventMapper;
    private final IncidentRelationMapper incidentRelationMapper;
    private final SentinelAlertRefMapper sentinelAlertRefMapper;

    @Override
    public IncidentVO create(IncidentCreateRequest request) {
        LocalDateTime now = LocalDateTime.now();
        Incident incident = new Incident();
        incident.setTitle(request.getTitle());
        incident.setDescription(request.getDescription());
        incident.setStatus(IncidentStatus.OPEN);
        incident.setSeverity(request.getSeverity() != null ? request.getSeverity() : IncidentSeverity.P3);
        incident.setPriority(request.getPriority() != null ? request.getPriority() : IncidentSeverity.P3);
        incident.setSource(request.getSource() != null ? request.getSource() : IncidentSource.MANUAL);
        incident.setCategory(request.getCategory());
        incident.setTags(request.getTags());
        incident.setReporterId(request.getReporterId());
        incident.setAssigneeId(request.getAssigneeId());
        incident.setRelatedAssetId(request.getRelatedAssetId());
        incident.setRelatedAssetType(request.getRelatedAssetType());
        incident.setRelatedService(request.getRelatedService());
        incident.setSlaTargetMinutes(request.getSlaTargetMinutes());
        if (request.getSlaTargetMinutes() != null && request.getSlaTargetMinutes() > 0) {
            incident.setSlaDeadline(now.plusMinutes(request.getSlaTargetMinutes()));
        }
        incident.setCreatedAt(now);
        incident.setUpdatedAt(now);

        incidentMapper.insert(incident);

        // 写入创建时间线
        IncidentEvent event = new IncidentEvent();
        event.setIncidentId(incident.getId());
        event.setActorId(request.getReporterId());
        event.setKind(IncidentEventKind.SYSTEM);
        event.setDetail("事件已创建，来源：" + incident.getSource());
        incidentEventMapper.insert(event);

        return toVO(incident);
    }

    @Override
    public IncidentVO update(Long id, IncidentUpdateRequest request) {
        Incident incident = requireIncident(id);
        incident.setTitle(request.getTitle());
        incident.setDescription(request.getDescription());
        if (request.getSeverity() != null) incident.setSeverity(request.getSeverity());
        if (request.getPriority() != null) incident.setPriority(request.getPriority());
        incident.setCategory(request.getCategory());
        incident.setTags(request.getTags());
        incident.setRelatedAssetId(request.getRelatedAssetId());
        incident.setRelatedAssetType(request.getRelatedAssetType());
        incident.setRelatedService(request.getRelatedService());
        if (request.getSlaTargetMinutes() != null) {
            incident.setSlaTargetMinutes(request.getSlaTargetMinutes());
            if (request.getSlaTargetMinutes() > 0) {
                incident.setSlaDeadline(incident.getCreatedAt().plusMinutes(request.getSlaTargetMinutes()));
            } else {
                incident.setSlaDeadline(null);
            }
        }
        incidentMapper.update(incident);
        return toVO(incident);
    }

    @Override
    @Transactional(readOnly = true)
    public IncidentVO getById(Long id) {
        return toVO(requireIncident(id));
    }

    @Override
    @Transactional(readOnly = true)
    public List<IncidentVO> search(IncidentStatus status, IncidentSeverity severity,
                                   Long assigneeId, Long reporterId, Integer limit) {
        return incidentMapper.search(status, severity, assigneeId, reporterId, limit)
                .stream().map(this::toVO).toList();
    }

    @Override
    public IncidentVO acknowledge(Long id, Long actorId) {
        return transition(id, IncidentStatus.ACK, actorId, null, null, null);
    }

    @Override
    public IncidentVO startMitigating(Long id, Long actorId) {
        return transition(id, IncidentStatus.MITIGATING, actorId, null, null, null);
    }

    @Override
    public IncidentVO resolve(Long id, Long actorId, String resolution) {
        return transition(id, IncidentStatus.RESOLVED, actorId, null, resolution, null);
    }

    @Override
    public IncidentVO close(Long id, Long actorId, IncidentCloseRequest request) {
        requireIncident(id);
        if (request.getRootCause() == null || request.getRootCause().isBlank()) {
            throw new BusinessException("关闭事件必须填写根因");
        }
        if (request.getResolution() == null || request.getResolution().isBlank()) {
            throw new BusinessException("关闭事件必须填写处置过程");
        }
        if (request.getPostmortem() == null || request.getPostmortem().isBlank()) {
            throw new BusinessException("关闭事件必须填写复盘结论");
        }
        return transition(id, IncidentStatus.CLOSED, actorId,
                request.getRootCause(), request.getResolution(), request.getPostmortem());
    }

    @Override
    public IncidentVO reopen(Long id, Long actorId) {
        return transition(id, IncidentStatus.OPEN, actorId, null, null, null);
    }

    @Override
    public IncidentVO assign(Long id, IncidentAssignRequest request) {
        Incident incident = requireIncident(id);
        incidentMapper.assign(id, request.getAssigneeId());
        incident.setAssigneeId(request.getAssigneeId());

        IncidentEvent event = new IncidentEvent();
        event.setIncidentId(id);
        event.setActorId(request.getActorId());
        event.setKind(IncidentEventKind.ASSIGN);
        event.setDetail("指派给用户 " + request.getAssigneeId());
        incidentEventMapper.insert(event);

        return toVO(incident);
    }

    @Override
    public IncidentEventVO addComment(Long id, IncidentCommentRequest request) {
        requireIncident(id);
        IncidentEvent event = new IncidentEvent();
        event.setIncidentId(id);
        event.setActorId(request.getActorId());
        event.setKind(IncidentEventKind.COMMENT);
        event.setDetail(request.getContent());
        incidentEventMapper.insert(event);
        return toEventVO(event);
    }

    @Override
    @Transactional(readOnly = true)
    public List<IncidentEventVO> listEvents(Long id) {
        requireIncident(id);
        return incidentEventMapper.findByIncidentId(id)
                .stream().map(this::toEventVO).toList();
    }

    @Override
    public IncidentRelationVO addRelation(Long id, IncidentRelationRequest request) {
        requireIncident(id);
        IncidentRelation relation = new IncidentRelation();
        relation.setIncidentId(id);
        relation.setRelationType(request.getRelationType());
        relation.setRefId(request.getRefId());
        relation.setRefType(request.getRefType());
        incidentRelationMapper.insert(relation);

        IncidentEvent event = new IncidentEvent();
        event.setIncidentId(id);
        event.setKind(IncidentEventKind.RELATION);
        event.setDetail("关联 " + request.getRelationType() + " #" + request.getRefId());
        incidentEventMapper.insert(event);

        return toRelationVO(relation);
    }

    @Override
    public void removeRelation(Long incidentId, Long relationId) {
        int deleted = incidentRelationMapper.deleteById(relationId, incidentId);
        if (deleted == 0) {
            throw new BusinessException("关联不存在");
        }
    }

    @Override
    @Transactional(readOnly = true)
    public List<IncidentRelationVO> listRelations(Long id) {
        requireIncident(id);
        return incidentRelationMapper.findByIncidentId(id)
                .stream().map(this::toRelationVO).toList();
    }

    @Override
    @Transactional(readOnly = true)
    public List<IncidentVO> findSlaBreached(int limit) {
        return incidentMapper.findSlaBreached(LocalDateTime.now(), limit)
                .stream().map(this::toVO).toList();
    }

    @Override
    public IncidentVO createFromAlert(Long alertId, Long actorId) {
        SentinelAlertRef alert = sentinelAlertRefMapper.findById(alertId);
        if (alert == null) {
            throw new BusinessException(404, "告警不存在");
        }

        // 幂等：已关联事件时直接返回，不重复建单
        if (alert.getTicketId() != null) {
            Incident existing = incidentMapper.findById(alert.getTicketId());
            if (existing != null) return toVO(existing);
        }

        IncidentSeverity severity = parseSeverity(alert.getSeverity());
        int slaMinutes = slaMinutesFor(severity);
        LocalDateTime base = alert.getFiredAt() != null ? alert.getFiredAt() : LocalDateTime.now();

        Incident incident = new Incident();
        incident.setTitle(alert.getTitle());
        incident.setDescription(describeAlert(alert));
        incident.setStatus(IncidentStatus.OPEN);
        incident.setSeverity(severity);
        incident.setPriority(severity);
        incident.setSource(IncidentSource.ALERT);
        incident.setCategory("ALERT");
        incident.setReporterId(alert.getOwnerId());
        incident.setRelatedAssetId(alert.getTaskId());
        incident.setRelatedAssetType("SENTINEL_TASK");
        incident.setRelatedService(alert.getTaskName());
        incident.setSlaTargetMinutes(slaMinutes);
        incident.setSlaDeadline(base.plusMinutes(slaMinutes));
        incident.setCreatedAt(LocalDateTime.now());
        incident.setUpdatedAt(LocalDateTime.now());
        incidentMapper.insert(incident);

        IncidentEvent created = new IncidentEvent();
        created.setIncidentId(incident.getId());
        created.setActorId(actorId);
        created.setKind(IncidentEventKind.SYSTEM);
        created.setDetail("由告警 #" + alertId + " 自动创建：" + alert.getTitle());
        incidentEventMapper.insert(created);

        IncidentRelation relation = new IncidentRelation();
        relation.setIncidentId(incident.getId());
        relation.setRelationType(IncidentRelationType.ALERT);
        relation.setRefId(alertId);
        relation.setRefType("sentinel_alert");
        incidentRelationMapper.insert(relation);

        // 回填告警侧引用，让告警列表能看到对应事件
        sentinelAlertRefMapper.linkTicket(alertId, incident.getId());
        sentinelAlertRefMapper.recordIncidentLinked(alertId, actorId, "已创建事件 #" + incident.getId());

        return toVO(incident);
    }

    @Override
    public int bridgeUnlinkedAlerts(int limit) {
        int created = 0;
        for (Long alertId : sentinelAlertRefMapper.findUnlinkedActiveAlertIds(limit)) {
            try {
                createFromAlert(alertId, null);
                created++;
            } catch (BusinessException ignored) {
                // 单条告警数据异常不影响其余告警桥接
            }
        }
        return created;
    }

    @Override
    public int scanSlaBreaches(int limit) {
        LocalDateTime now = LocalDateTime.now();
        int recorded = 0;
        for (Incident incident : incidentMapper.findSlaBreached(now, limit)) {
            // 每条事件只记一次超时，避免轮询重复刷屏
            if (incidentEventMapper.countByKind(incident.getId(), IncidentEventKind.SLA_BREACH) > 0) {
                continue;
            }
            IncidentEvent event = new IncidentEvent();
            event.setIncidentId(incident.getId());
            event.setKind(IncidentEventKind.SLA_BREACH);
            event.setDetail("SLA 超时：截止 " + incident.getSlaDeadline()
                    + "，当前状态 " + incident.getStatus());
            incidentEventMapper.insert(event);
            recorded++;
        }
        return recorded;
    }

    /**
     * 从工单上下文生成恢复契约草案（阶段 C）。
     *
     * <p>草案与 recovery-contract/v1 schema 同形，digest 恒为空串——平台不越权签发：
     * 谓词核对、canonical digest 计算、内部端点登记全部留在 Agent 侧。</p>
     */
    @Override
    public IncidentContractDraftVO buildContractDraft(Long id) {
        Incident incident = requireIncident(id);
        String service = firstNonBlank(incident.getRelatedService(), incident.getCategory(), "unknown-service");
        String ident = toIdent(service);

        Map<String, Object> target = new LinkedHashMap<>();
        target.put("target_id", ident + "-primary");
        target.put("target_kind", "SERVICE");

        Map<String, Object> obligation = new LinkedHashMap<>();
        obligation.put("obligation_id", "service-health-observed");
        obligation.put("predicate_id", "service-health-ok");
        obligation.put("predicate_version", "v1");
        obligation.put("required", true);
        obligation.put("weight", 1);
        obligation.put("collector_ids", List.of("metric-collector"));
        obligation.put("source_groups", List.of("incident-evidence"));
        obligation.put("binding_revision", "unspecified");
        obligation.put("scope", ident);
        obligation.put("target", target);
        obligation.put("predicate_params", Map.of("service", service));

        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("schema_version", "recovery-contract/v1");
        draft.put("id", "incident-" + incident.getId() + "-"
                + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHHmmss")));
        draft.put("version", "v1");
        draft.put("scope", ident);
        draft.put("target", target);
        draft.put("expected_revision", "unspecified");
        draft.put("template_id", "incident-reactive");
        draft.put("template_version", "v1");
        draft.put("obligations", List.of(obligation));
        draft.put("source_groups", List.of("incident-evidence", "sentinel-metrics"));
        // window/budgets 是 semantics.md 冻结常量，草案直接给出冻结值，签发前不得修改。
        draft.put("window", Map.of(
                "sample_groups", 3,
                "min_first_last_gap_ms", 4000,
                "max_adjacent_gap_ms", 4000,
                "max_intra_group_skew_ms", 1250,
                "min_next_group_gap_ms", 2000));
        draft.put("budgets", Map.of(
                "max_probe_calls", 12,
                "per_probe_timeout_ms", 1000,
                "run_deadline_ms", 30000,
                "evidence_ttl_ms", 15000,
                "receipt_ttl_ms", 8000));
        draft.put("expires_after", 3600000);
        draft.put("digest", "");

        // 草案生成是可追溯动作：写入时间线
        IncidentEvent event = new IncidentEvent();
        event.setIncidentId(incident.getId());
        event.setKind(IncidentEventKind.SYSTEM);
        event.setDetail("已生成恢复契约草案 " + draft.get("id") + "（未签发，待 Agent 校验 digest）。");
        incidentEventMapper.insert(event);

        return IncidentContractDraftVO.builder()
                .incidentId(incident.getId())
                .incidentTitle(incident.getTitle())
                .summary("针对 " + service + " 的服务健康义务契约草案，模板 incident-reactive/v1，有效期 1 小时。")
                .draft(draft)
                .notes(List.of(
                        "草案 digest 为空串，不是可执行契约——签发必须由 Agent 侧完成"
                                + "（核对谓词绑定、计算 canonical digest、经内部端点登记）。",
                        "predicate_id=service-health-ok 为占位谓词，签发前需按团队谓词库核对替换。",
                        "source_groups 已给默认两项，可按采集面调整；window/budgets 为冻结常量，不可修改。"))
                .build();
    }

    // ---------------------------------------------------------------
    // 内部方法
    // ---------------------------------------------------------------

    private Incident requireIncident(Long id) {
        Incident incident = incidentMapper.findById(id);
        if (incident == null) {
            throw new BusinessException(404, "事件不存在");
        }
        return incident;
    }

    /** 依次取第一个非空白值，全空时返回兜底值。 */
    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return values[values.length - 1];
    }

    /**
     * 归一化为契约合法标识：^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$。
     * 非法字符折叠为 "-"，数字开头不足时加 "svc-" 前缀。
     */
    private String toIdent(String raw) {
        String cleaned = raw.toLowerCase().replaceAll("[^a-z0-9._:-]+", "-");
        cleaned = cleaned.replaceAll("^-+", "").replaceAll("-+$", "");
        if (cleaned.isEmpty()) {
            cleaned = "unknown-service";
        }
        if (!cleaned.matches("^[A-Za-z0-9].*")) {
            cleaned = "svc-" + cleaned;
        }
        return cleaned.length() > 96 ? cleaned.substring(0, 96) : cleaned;
    }

    /**
     * 状态流转核心：校验状态机 -> 更新状态 -> 写入时间线。
     */
    private IncidentVO transition(Long id, IncidentStatus target, Long actorId,
                                  String rootCause, String resolution, String postmortem) {
        Incident incident = requireIncident(id);
        IncidentStatus current = incident.getStatus();

        if (!current.canTransitionTo(target)) {
            throw new BusinessException("不允许从 " + current + " 转移到 " + target);
        }

        incidentMapper.updateStatus(id, target, rootCause, resolution, postmortem);
        incident.setStatus(target);

        IncidentEvent event = new IncidentEvent();
        event.setIncidentId(id);
        event.setActorId(actorId);
        event.setKind(IncidentEventKind.STATUS_CHANGE);
        event.setDetail(current + " -> " + target);
        incidentEventMapper.insert(event);

        return toVO(incident);
    }

    private IncidentSeverity parseSeverity(String raw) {
        if (raw == null) return IncidentSeverity.P2;
        try {
            return IncidentSeverity.valueOf(raw.trim().toUpperCase(java.util.Locale.ROOT));
        } catch (IllegalArgumentException invalid) {
            return IncidentSeverity.P2;
        }
    }

    /** 按严重等级给出默认 SLA 时长（分钟）。 */
    private int slaMinutesFor(IncidentSeverity severity) {
        return switch (severity) {
            case P0 -> 15;
            case P1 -> 30;
            case P2 -> 120;
            case P3 -> 480;
        };
    }

    private String describeAlert(SentinelAlertRef alert) {
        StringBuilder text = new StringBuilder();
        if (alert.getTaskName() != null) text.append("哨兵任务：").append(alert.getTaskName());
        if (alert.getMetric() != null) {
            if (text.length() > 0) text.append('；');
            text.append("指标：").append(alert.getMetric());
        }
        if (alert.getObservedValue() != null) {
            if (text.length() > 0) text.append('；');
            text.append("观测值：").append(alert.getObservedValue());
        }
        if (alert.getThresholdValue() != null) {
            if (text.length() > 0) text.append('；');
            text.append("阈值：").append(alert.getThresholdValue());
        }
        return text.toString();
    }

    private IncidentVO toVO(Incident e) {
        return IncidentVO.builder()
                .id(e.getId())
                .title(e.getTitle())
                .description(e.getDescription())
                .status(e.getStatus())
                .severity(e.getSeverity())
                .priority(e.getPriority())
                .source(e.getSource())
                .category(e.getCategory())
                .tags(e.getTags())
                .reporterId(e.getReporterId())
                .assigneeId(e.getAssigneeId())
                .relatedAssetId(e.getRelatedAssetId())
                .relatedAssetType(e.getRelatedAssetType())
                .relatedService(e.getRelatedService())
                .slaTargetMinutes(e.getSlaTargetMinutes())
                .slaDeadline(e.getSlaDeadline())
                .acknowledgedAt(e.getAcknowledgedAt())
                .mitigatedAt(e.getMitigatedAt())
                .resolvedAt(e.getResolvedAt())
                .closedAt(e.getClosedAt())
                .rootCause(e.getRootCause())
                .resolution(e.getResolution())
                .postmortem(e.getPostmortem())
                .createdAt(e.getCreatedAt())
                .updatedAt(e.getUpdatedAt())
                .build();
    }

    private IncidentEventVO toEventVO(IncidentEvent e) {
        return IncidentEventVO.builder()
                .id(e.getId())
                .incidentId(e.getIncidentId())
                .at(e.getAt())
                .actorId(e.getActorId())
                .kind(e.getKind())
                .detail(e.getDetail())
                .build();
    }

    private IncidentRelationVO toRelationVO(IncidentRelation r) {
        return IncidentRelationVO.builder()
                .id(r.getId())
                .incidentId(r.getIncidentId())
                .relationType(r.getRelationType())
                .refId(r.getRefId())
                .refType(r.getRefType())
                .createdAt(r.getCreatedAt())
                .build();
    }
}
