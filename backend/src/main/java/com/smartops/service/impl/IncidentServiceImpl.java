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
import com.smartops.vo.IncidentEventVO;
import com.smartops.vo.IncidentRelationVO;
import com.smartops.vo.IncidentVO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

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
