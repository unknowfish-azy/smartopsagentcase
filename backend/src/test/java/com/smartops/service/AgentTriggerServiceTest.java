package com.smartops.service;

import com.smartops.diagnosis.AgentDiagnosisClient;
import com.smartops.dto.inspector.InspectionRecordRequest;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * W7：事件驱动的防抖与写回口径。
 *
 * <p>这里只覆盖纯逻辑：防抖窗口、REVIEW/requiresHuman 载荷、模型不可用不产事件。
 * 真实 HTTP 与内部令牌门禁分别在 {@link com.smartops.controller.InternalAgentTriggerControllerTest}
 * 与 ai-service 的 test_agent_trigger.py 覆盖。</p>
 */
class AgentTriggerServiceTest {

    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final InspectorEventService inspector = mock(InspectorEventService.class);
    private final AgentDiagnosisClient client = mock(AgentDiagnosisClient.class);
    private final AgentTriggerService service = new AgentTriggerService(jdbc, inspector, client, true, 5);

    @Test
    void sameResourceIsDebouncedWithinFiveMinutes() {
        Instant start = Instant.parse("2026-11-20T10:00:00Z");
        assertThat(service.reserve("task:7", start)).isTrue();
        assertThat(service.reserve("task:7", start.plusSeconds(60))).isFalse();
        assertThat(service.reserve("task:7", start.plusSeconds(299))).isFalse();
        assertThat(service.reserve("task:7", start.plusSeconds(301))).isTrue();
        assertThat(service.reserve("task:8", start.plusSeconds(302))).isTrue();
    }

    @Test
    void recordIsReviewAndRequiresHuman() {
        InspectionRecordRequest request = service.buildRecord(
                context("P1"),
                Map.of("created", true, "answer", "只读初诊结论", "runId", "run-1", "toolCalls", java.util.List.of()));

        assertThat(request.getStatus()).isEqualTo("REVIEW");
        assertThat(request.getRequiresHuman()).isTrue();
        assertThat(request.getSeverity()).isEqualTo("HIGH");
        assertThat(request.getTarget()).isEqualTo("task:7");
        assertThat(request.getTaskId()).isEqualTo("SENTINEL-42");
        assertThat(request.getAgentClaim()).isEqualTo("只读初诊结论");
        assertThat(request.getEvidence()).isNotEmpty();
        assertThat(request.getMetadata()).containsEntry("runId", "run-1");
        assertThat(request.getMetadata()).containsEntry("alertId", 42L);
    }

    @Test
    void severityMapFollowsSentinelLevels() {
        assertThat(service.buildRecord(context("P0"), Map.of()).getSeverity()).isEqualTo("CRITICAL");
        assertThat(service.buildRecord(context("P2"), Map.of()).getSeverity()).isEqualTo("WARN");
        assertThat(service.buildRecord(context("P3"), Map.of()).getSeverity()).isEqualTo("INFO");
    }

    @Test
    void noEventWhenModelUnavailable() {
        when(client.diagnose(any())).thenReturn(
                Optional.of(Map.of("created", false, "reason", "MODEL_UNAVAILABLE")));

        service.diagnose(context("P1"));

        verify(inspector, never()).record(any(), any());
    }

    @Test
    void writesReviewEventWithAlertOwner() {
        when(client.diagnose(any())).thenReturn(Optional.of(Map.of(
                "created", true,
                "answer", "线索指向磁盘写满",
                "runId", "run-9",
                "toolCalls", java.util.List.of(Map.of("toolName", "sentinel.alerts", "success", true)))));
        when(inspector.record(any(), eq(81L))).thenReturn(Map.of("id", "INS-1"));

        service.diagnose(context("P1"));

        ArgumentCaptor<InspectionRecordRequest> captor = ArgumentCaptor.forClass(InspectionRecordRequest.class);
        verify(inspector).record(captor.capture(), eq(81L));
        InspectionRecordRequest request = captor.getValue();
        assertThat(request.getStatus()).isEqualTo("REVIEW");
        assertThat(request.getRequiresHuman()).isTrue();
        assertThat(request.getAgentClaim()).isEqualTo("线索指向磁盘写满");
        assertThat(request.getRecommendation()).contains("未执行任何写操作");
    }

    private static AgentTriggerService.TriggerContext context(String severity) {
        return new AgentTriggerService.TriggerContext(
                42L, 7L, 81L, severity, "cpu", "95", "cpu>90", "web-prod：cpu>90", "task:7");
    }
}
