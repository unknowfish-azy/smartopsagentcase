package com.smartops.controller;

import com.smartops.service.KnowledgeCandidateService;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class KnowledgeCandidateControllerTest {
    @Test
    void createsCandidateForCurrentUserAndRun() {
        var service = mock(KnowledgeCandidateService.class);
        var candidate = new KnowledgeCandidateService.KnowledgeCandidate(
                3L, 8L, "trace", "k8s.pods", "标题", "摘要", "# 内容", "PENDING_REVIEW", Instant.EPOCH, "OPERATION_RUN", null, null, null, null);
        when(service.createFromRun(7L, 8L)).thenReturn(candidate);

        var response = new KnowledgeCandidateController(service).createFromOperationRun(7L, 8L);

        assertThat(response.getData()).isSameAs(candidate);
        verify(service).createFromRun(7L, 8L);
    }

    @Test
    void createsCandidateFromOwnedWebResearchTask() {
        var service = mock(KnowledgeCandidateService.class);
        var candidate = new KnowledgeCandidateService.KnowledgeCandidate(
                4L, null, "web-research-12", "WEB_RESEARCH", "网页标题", "摘要", "# 内容", "PENDING_REVIEW", Instant.EPOCH,
                "WEB_RESEARCH", 12L, "https://example.com/source", "a".repeat(64), Instant.EPOCH);
        when(service.createFromWebResearch(7L, 12L)).thenReturn(candidate);

        var response = new KnowledgeCandidateController(service).createFromWebResearch(7L, 12L);

        assertThat(response.getData()).isSameAs(candidate);
        verify(service).createFromWebResearch(7L, 12L);
    }

    @Test
    void listsAndReadsCandidatesForCurrentUser() {
        var service = mock(KnowledgeCandidateService.class);
        var candidate = new KnowledgeCandidateService.KnowledgeCandidate(
                3L, 8L, "trace", "k8s.pods", "标题", "摘要", "# 内容", "PENDING_REVIEW", Instant.EPOCH, "OPERATION_RUN", null, null, null, null);
        var page = new KnowledgeCandidateService.KnowledgeCandidatePage(java.util.List.of(candidate), 1, 1, 20);
        when(service.list(7L, "PENDING_REVIEW", 1, 20)).thenReturn(page);
        when(service.detail(7L, 3L)).thenReturn(candidate);
        var controller = new KnowledgeCandidateController(service);

        assertThat(controller.list(7L, "PENDING_REVIEW", 1, 20).getData()).isSameAs(page);
        assertThat(controller.detail(7L, 3L).getData()).isSameAs(candidate);
        verify(service).list(7L, "PENDING_REVIEW", 1, 20);
        verify(service).detail(7L, 3L);
    }
}
