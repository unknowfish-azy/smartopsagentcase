package com.smartops.service;

import com.smartops.dto.IncidentAssignRequest;
import com.smartops.dto.IncidentCloseRequest;
import com.smartops.dto.IncidentCommentRequest;
import com.smartops.dto.IncidentCreateRequest;
import com.smartops.dto.IncidentRelationRequest;
import com.smartops.dto.IncidentUpdateRequest;
import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentStatus;
import com.smartops.vo.IncidentEventVO;
import com.smartops.vo.IncidentRelationVO;
import com.smartops.vo.IncidentVO;

import java.util.List;

/**
 * 事件 / 工单中心服务。
 *
 * <p>状态机：OPEN -> ACK -> MITIGATING -> RESOLVED -> CLOSED</p>
 */
public interface IncidentService {

    IncidentVO create(IncidentCreateRequest request);

    IncidentVO update(Long id, IncidentUpdateRequest request);

    IncidentVO getById(Long id);

    List<IncidentVO> search(IncidentStatus status, IncidentSeverity severity,
                            Long assigneeId, Long reporterId, Integer limit);

    /** 确认事件（OPEN -> ACK）。 */
    IncidentVO acknowledge(Long id, Long actorId);

    /** 开始处置（ACK -> MITIGATING）。 */
    IncidentVO startMitigating(Long id, Long actorId);

    /** 标记已解决（-> RESOLVED）。 */
    IncidentVO resolve(Long id, Long actorId, String resolution);

    /** 关闭事件（RESOLVED -> CLOSED），必须填写根因与复盘。 */
    IncidentVO close(Long id, Long actorId, IncidentCloseRequest request);

    /** 重新打开（CLOSED -> OPEN）。 */
    IncidentVO reopen(Long id, Long actorId);

    /** 指派 / 转派负责人。 */
    IncidentVO assign(Long id, IncidentAssignRequest request);

    /** 添加评论。 */
    IncidentEventVO addComment(Long id, IncidentCommentRequest request);

    /** 查询时间线。 */
    List<IncidentEventVO> listEvents(Long id);

    /** 添加关联资源。 */
    IncidentRelationVO addRelation(Long id, IncidentRelationRequest request);

    /** 移除关联资源。 */
    void removeRelation(Long incidentId, Long relationId);

    /** 查询关联资源。 */
    List<IncidentRelationVO> listRelations(Long id);

    /** 查询 SLA 即将超时或已超时的事件（供定时器 / Sentinel 调用）。 */
    List<IncidentVO> findSlaBreached(int limit);

    /**
     * 从告警创建事件（P0-01 告警联动）。
     *
     * <p>幂等：告警已关联事件时直接返回既有事件，不重复建单。</p>
     */
    IncidentVO createFromAlert(Long alertId, Long actorId);

    /** 把尚未关联事件的活动告警批量桥接成事件，返回本次新建数量。 */
    int bridgeUnlinkedAlerts(int limit);

    /** 扫描 SLA 超时事件并写入时间线，返回本次新记录数量（每条事件只记一次）。 */
    int scanSlaBreaches(int limit);
}
