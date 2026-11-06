package com.smartops.integration;

import com.smartops.dto.inspector.InspectionRecordRequest;
import com.smartops.service.InspectorEventService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class InspectorPersistenceIntegrationTest {

    @Autowired
    private InspectorEventService service;

    @Test
    void inspectionResultPersistsWithIssueEvidenceAndVerification() {
        InspectionRecordRequest request = new InspectionRecordRequest();
        request.setInspectionId("INS-INTEGRATION-01");
        request.setTaskId("TASK-NGINX-502");
        request.setStatus("VIOLATION");
        request.setSeverity("HIGH");
        request.setCategory("APPROVAL");
        request.setReason("Approval missing");
        request.setRecommendation("Collect evidence before state change");
        request.setRequiresHuman(true);
        request.setMetadata(Map.of(
                "reasoningSummary", "日志显示 upstream 超时",
                "tool", "nginx.logs"
        ));

        InspectionRecordRequest.Issue issue = new InspectionRecordRequest.Issue();
        issue.setCategory("APPROVAL");
        issue.setSeverity("HIGH");
        issue.setReason("Approval missing");
        request.getIssues().add(issue);

        InspectionRecordRequest.Evidence evidence = new InspectionRecordRequest.Evidence();
        evidence.setContent("upstream timed out");
        evidence.setSource("nginx.log");
        evidence.setVersion("1.24");
        evidence.setScore(0.91);
        request.getEvidence().add(evidence);

        InspectionRecordRequest.Verification verification =
                new InspectionRecordRequest.Verification();
        verification.setResolved(false);
        verification.setStatus("502");
        request.setVerification(verification);

        Map<String, Object> stored = service.record(request);

        assertThat(stored.get("id")).isEqualTo("INS-INTEGRATION-01");
        assertThat((Iterable<?>) stored.get("issues")).hasSize(1);
        assertThat((Iterable<?>) stored.get("evidence")).hasSize(1);
        assertThat(stored.get("verification")).isNotNull();
        assertThat(stored.get("metadata"))
                .isInstanceOfSatisfying(Map.class, metadata ->
                        assertThat(metadata.get("tool")).isEqualTo("nginx.logs"));
        // 内部通道事件 user_id 为 NULL，用全局视图确认落库（SEC-08）。
        assertThat(service.summary(null, true).get("total")).isEqualTo(1L);
    }
}
