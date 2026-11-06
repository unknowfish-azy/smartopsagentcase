package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.dto.IncidentAssignRequest;
import com.smartops.dto.IncidentCloseRequest;
import com.smartops.dto.IncidentCommentRequest;
import com.smartops.dto.IncidentCreateRequest;
import com.smartops.dto.IncidentRelationRequest;
import com.smartops.dto.IncidentUpdateRequest;
import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentStatus;
import com.smartops.service.IncidentService;
import com.smartops.vo.IncidentEventVO;
import com.smartops.vo.IncidentRelationVO;
import com.smartops.vo.IncidentVO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 事件 / 工单中心 API。
 *
 * <p>状态机：OPEN -> ACK -> MITIGATING -> RESOLVED -> CLOSED</p>
 */
@RestController
@RequestMapping("/api/incidents")
@RequiredArgsConstructor
public class IncidentController {

    private final IncidentService incidentService;

    @PostMapping
    public ApiResponse<IncidentVO> create(@Valid @RequestBody IncidentCreateRequest request) {
        return ApiResponse.success(incidentService.create(request));
    }

    @PutMapping("/{id}")
    public ApiResponse<IncidentVO> update(@PathVariable Long id,
                                          @Valid @RequestBody IncidentUpdateRequest request) {
        return ApiResponse.success(incidentService.update(id, request));
    }

    @GetMapping("/{id}")
    public ApiResponse<IncidentVO> getById(@PathVariable Long id) {
        return ApiResponse.success(incidentService.getById(id));
    }

    @GetMapping
    public ApiResponse<List<IncidentVO>> search(
            @RequestParam(required = false) IncidentStatus status,
            @RequestParam(required = false) IncidentSeverity severity,
            @RequestParam(required = false) Long assigneeId,
            @RequestParam(required = false) Long reporterId,
            @RequestParam(required = false) Integer limit) {
        return ApiResponse.success(incidentService.search(status, severity, assigneeId, reporterId, limit));
    }

    /** 确认事件（OPEN -> ACK）。 */
    @PostMapping("/{id}/acknowledge")
    public ApiResponse<IncidentVO> acknowledge(@PathVariable Long id,
                                               @RequestParam(required = false) Long actorId) {
        return ApiResponse.success(incidentService.acknowledge(id, actorId));
    }

    /** 开始处置（ACK -> MITIGATING）。 */
    @PostMapping("/{id}/mitigate")
    public ApiResponse<IncidentVO> mitigate(@PathVariable Long id,
                                            @RequestParam(required = false) Long actorId) {
        return ApiResponse.success(incidentService.startMitigating(id, actorId));
    }

    /** 标记已解决。 */
    @PostMapping("/{id}/resolve")
    public ApiResponse<IncidentVO> resolve(@PathVariable Long id,
                                           @RequestParam(required = false) Long actorId,
                                           @RequestParam(required = false) String resolution) {
        return ApiResponse.success(incidentService.resolve(id, actorId, resolution));
    }

    /** 关闭事件（必须填写根因、处置过程、复盘结论）。 */
    @PostMapping("/{id}/close")
    public ApiResponse<IncidentVO> close(@PathVariable Long id,
                                         @RequestParam(required = false) Long actorId,
                                         @Valid @RequestBody IncidentCloseRequest request) {
        return ApiResponse.success(incidentService.close(id, actorId, request));
    }

    /** 重新打开事件。 */
    @PostMapping("/{id}/reopen")
    public ApiResponse<IncidentVO> reopen(@PathVariable Long id,
                                          @RequestParam(required = false) Long actorId) {
        return ApiResponse.success(incidentService.reopen(id, actorId));
    }

    /** 指派 / 转派负责人。 */
    @PostMapping("/{id}/assign")
    public ApiResponse<IncidentVO> assign(@PathVariable Long id,
                                          @Valid @RequestBody IncidentAssignRequest request) {
        return ApiResponse.success(incidentService.assign(id, request));
    }

    /** 添加评论。 */
    @PostMapping("/{id}/comments")
    public ApiResponse<IncidentEventVO> addComment(@PathVariable Long id,
                                                   @Valid @RequestBody IncidentCommentRequest request) {
        return ApiResponse.success(incidentService.addComment(id, request));
    }

    /** 查询时间线。 */
    @GetMapping("/{id}/events")
    public ApiResponse<List<IncidentEventVO>> listEvents(@PathVariable Long id) {
        return ApiResponse.success(incidentService.listEvents(id));
    }

    /** 添加关联资源（告警、Agent Run、知识、证据）。 */
    @PostMapping("/{id}/relations")
    public ApiResponse<IncidentRelationVO> addRelation(@PathVariable Long id,
                                                       @Valid @RequestBody IncidentRelationRequest request) {
        return ApiResponse.success(incidentService.addRelation(id, request));
    }

    /** 移除关联资源。 */
    @DeleteMapping("/{id}/relations/{relationId}")
    public ApiResponse<Void> removeRelation(@PathVariable Long id,
                                            @PathVariable Long relationId) {
        incidentService.removeRelation(id, relationId);
        return ApiResponse.success();
    }

    /** 查询关联资源。 */
    @GetMapping("/{id}/relations")
    public ApiResponse<List<IncidentRelationVO>> listRelations(@PathVariable Long id) {
        return ApiResponse.success(incidentService.listRelations(id));
    }

    /**
     * 从告警创建事件（告警联动入口）。
     *
     * <p>幂等：告警已有对应事件时返回既有事件。</p>
     */
    @PostMapping("/from-alert/{alertId}")
    public ApiResponse<IncidentVO> createFromAlert(@PathVariable Long alertId,
                                                   @RequestParam(required = false) Long actorId) {
        return ApiResponse.success(incidentService.createFromAlert(alertId, actorId));
    }

    /** 手动触发 SLA 超时扫描，返回本次新增的超时记录数。 */
    @PostMapping("/sla/scan")
    public ApiResponse<Integer> scanSla(@RequestParam(defaultValue = "100") int limit) {
        return ApiResponse.success(incidentService.scanSlaBreaches(limit));
    }
}
