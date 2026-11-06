package com.smartops.service;

import com.smartops.dto.IncidentCloseRequest;
import com.smartops.dto.IncidentCreateRequest;
import com.smartops.entity.Incident;
import com.smartops.entity.SentinelAlertRef;
import com.smartops.exception.BusinessException;
import com.smartops.mapper.IncidentEventMapper;
import com.smartops.mapper.IncidentMapper;
import com.smartops.mapper.IncidentRelationMapper;
import com.smartops.mapper.SentinelAlertRefMapper;
import com.smartops.module.incident.IncidentEventKind;
import com.smartops.module.incident.IncidentSeverity;
import com.smartops.module.incident.IncidentSource;
import com.smartops.module.incident.IncidentStatus;
import com.smartops.service.impl.IncidentServiceImpl;
import com.smartops.vo.IncidentVO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class IncidentServiceTest {

    @Mock private IncidentMapper incidentMapper;
    @Mock private IncidentEventMapper incidentEventMapper;
    @Mock private IncidentRelationMapper incidentRelationMapper;
    @Mock private SentinelAlertRefMapper sentinelAlertRefMapper;

    private IncidentService incidentService;

    @BeforeEach
    void setUp() {
        incidentService = new IncidentServiceImpl(incidentMapper, incidentEventMapper,
                incidentRelationMapper, sentinelAlertRefMapper);
    }

    @Test
    void createShouldSetOpenStatusAndSlaDeadline() {
        IncidentCreateRequest request = new IncidentCreateRequest();
        request.setTitle("CPU 使用率过高");
        request.setDescription("prod-web-01 CPU 持续 95%");
        request.setSeverity(IncidentSeverity.P1);
        request.setSource(IncidentSource.ALERT);
        request.setReporterId(10L);
        request.setSlaTargetMinutes(30);

        doAnswer(invocation -> {
            Incident entity = invocation.getArgument(0);
            entity.setId(100L);
            return 1;
        }).when(incidentMapper).insert(any(Incident.class));

        IncidentVO vo = incidentService.create(request);

        assertNotNull(vo);
        assertEquals(100L, vo.getId());
        assertEquals(IncidentStatus.OPEN, vo.getStatus());
        assertEquals(IncidentSeverity.P1, vo.getSeverity());
        assertEquals(IncidentSource.ALERT, vo.getSource());
        assertNotNull(vo.getSlaDeadline());
        verify(incidentMapper).insert(any(Incident.class));
        verify(incidentEventMapper).insert(any());
    }

    @Test
    void acknowledgeShouldTransitionFromOpenToAck() {
        Incident incident = buildIncident(1L, IncidentStatus.OPEN);
        when(incidentMapper.findById(1L)).thenReturn(incident);
        when(incidentMapper.updateStatus(eq(1L), eq(IncidentStatus.ACK), any(), any(), any())).thenReturn(1);

        IncidentVO vo = incidentService.acknowledge(1L, 10L);

        assertEquals(IncidentStatus.ACK, vo.getStatus());
        verify(incidentMapper).updateStatus(eq(1L), eq(IncidentStatus.ACK), any(), any(), any());
        verify(incidentEventMapper).insert(any());
    }

    @Test
    void closeWithoutRootCauseShouldFail() {
        Incident incident = buildIncident(1L, IncidentStatus.RESOLVED);
        when(incidentMapper.findById(1L)).thenReturn(incident);

        IncidentCloseRequest request = new IncidentCloseRequest();
        request.setResolution("重启服务");
        request.setPostmortem("无");

        assertThrows(BusinessException.class, () -> incidentService.close(1L, 10L, request));
        verify(incidentMapper, never()).updateStatus(any(), any(), any(), any(), any());
    }

    @Test
    void closeWithFullInfoShouldSucceed() {
        Incident incident = buildIncident(1L, IncidentStatus.RESOLVED);
        when(incidentMapper.findById(1L)).thenReturn(incident);
        when(incidentMapper.updateStatus(eq(1L), eq(IncidentStatus.CLOSED), any(), any(), any())).thenReturn(1);

        IncidentCloseRequest request = new IncidentCloseRequest();
        request.setRootCause("日志盘满导致写入失败");
        request.setResolution("清理日志并扩容");
        request.setPostmortem("增加磁盘监控告警阈值");

        IncidentVO vo = incidentService.close(1L, 10L, request);

        assertEquals(IncidentStatus.CLOSED, vo.getStatus());
    }

    @Test
    void invalidTransitionShouldFail() {
        Incident incident = buildIncident(1L, IncidentStatus.CLOSED);
        when(incidentMapper.findById(1L)).thenReturn(incident);

        // CLOSED -> ACK 不合法
        assertThrows(BusinessException.class, () -> incidentService.acknowledge(1L, 10L));
        verify(incidentMapper, never()).updateStatus(any(), any(), any(), any(), any());
    }

    @Test
    void reopenFromClosedShouldSucceed() {
        Incident incident = buildIncident(1L, IncidentStatus.CLOSED);
        when(incidentMapper.findById(1L)).thenReturn(incident);
        when(incidentMapper.updateStatus(eq(1L), eq(IncidentStatus.OPEN), any(), any(), any())).thenReturn(1);

        IncidentVO vo = incidentService.reopen(1L, 10L);

        assertEquals(IncidentStatus.OPEN, vo.getStatus());
    }

    @Test
    void getByIdNotFoundShouldThrow() {
        when(incidentMapper.findById(999L)).thenReturn(null);
        assertThrows(BusinessException.class, () -> incidentService.getById(999L));
    }

    @Test
    void createFromAlertShouldBuildIncidentAndLinkBothSides() {
        SentinelAlertRef alert = new SentinelAlertRef();
        alert.setId(7L);
        alert.setTaskId(3L);
        alert.setSeverity("P1");
        alert.setTitle("prod-web-01：CPU 使用率过高");
        alert.setMetric("cpu");
        alert.setObservedValue("97.5");
        alert.setThresholdValue("cpu>90");
        alert.setFiredAt(LocalDateTime.now());
        alert.setOwnerId(11L);
        alert.setTaskName("prod-web-01");
        when(sentinelAlertRefMapper.findById(7L)).thenReturn(alert);

        doAnswer(invocation -> {
            Incident entity = invocation.getArgument(0);
            entity.setId(55L);
            return 1;
        }).when(incidentMapper).insert(any(Incident.class));

        IncidentVO vo = incidentService.createFromAlert(7L, 11L);

        assertEquals(55L, vo.getId());
        assertEquals(IncidentSource.ALERT, vo.getSource());
        assertEquals(IncidentSeverity.P1, vo.getSeverity());
        assertEquals(11L, vo.getReporterId());
        assertEquals("SENTINEL_TASK", vo.getRelatedAssetType());
        assertEquals(30, vo.getSlaTargetMinutes());
        assertNotNull(vo.getSlaDeadline());

        verify(incidentRelationMapper).insert(any());
        verify(sentinelAlertRefMapper).linkTicket(7L, 55L);
        verify(sentinelAlertRefMapper).recordIncidentLinked(eq(7L), eq(11L), any());
    }

    @Test
    void createFromAlertShouldBeIdempotentWhenAlreadyLinked() {
        SentinelAlertRef alert = new SentinelAlertRef();
        alert.setId(7L);
        alert.setTicketId(55L);

        Incident existing = buildIncident(55L, IncidentStatus.OPEN);
        when(sentinelAlertRefMapper.findById(7L)).thenReturn(alert);
        when(incidentMapper.findById(55L)).thenReturn(existing);

        IncidentVO vo = incidentService.createFromAlert(7L, 11L);

        assertEquals(55L, vo.getId());
        verify(incidentMapper, never()).insert(any());
        verify(sentinelAlertRefMapper, never()).linkTicket(any(), any());
    }

    @Test
    void createFromAlertWithUnknownAlertShouldFail() {
        when(sentinelAlertRefMapper.findById(404L)).thenReturn(null);
        assertThrows(BusinessException.class, () -> incidentService.createFromAlert(404L, 11L));
    }

    @Test
    void scanSlaBreachesShouldRecordOnlyOnce() {
        Incident breached = buildIncident(1L, IncidentStatus.ACK);
        breached.setSlaDeadline(LocalDateTime.now().minusMinutes(5));
        when(incidentMapper.findSlaBreached(any(), eq(100))).thenReturn(List.of(breached));
        when(incidentEventMapper.countByKind(1L, IncidentEventKind.SLA_BREACH)).thenReturn(0, 1);

        assertEquals(1, incidentService.scanSlaBreaches(100));
        // 第二次扫描时已有超时记录，不再重复写入
        assertEquals(0, incidentService.scanSlaBreaches(100));
        verify(incidentEventMapper, times(1)).insert(any());
    }

    private Incident buildIncident(Long id, IncidentStatus status) {
        Incident incident = new Incident();
        incident.setId(id);
        incident.setTitle("测试事件");
        incident.setStatus(status);
        incident.setSeverity(IncidentSeverity.P2);
        incident.setPriority(IncidentSeverity.P2);
        incident.setSource(IncidentSource.MANUAL);
        incident.setCreatedAt(LocalDateTime.now());
        incident.setUpdatedAt(LocalDateTime.now());
        return incident;
    }
}
