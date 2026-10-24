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
                3L, 8L, "trace", "k8s.pods", "标题", "摘要", "# 内容", "PENDING_REVIEW", Instant.EPOCH);
        when(service.createFromRun(7L, 8L)).thenReturn(candidate);

        var response = new KnowledgeCandidateController(service).createFromOperationRun(7L, 8L);

        assertThat(response.getData()).isSameAs(candidate);
        verify(service).createFromRun(7L, 8L);
    }

    @Test
    void listsAndReadsCandidatesForCurrentUser() {
        var service = mock(KnowledgeCandidateService.class);
        var candidate = new KnowledgeCandidateService.KnowledgeCandidate(
                3L, 8L, "trace", "k8s.pods", "标题", "摘要", "# 内容", "PENDING_REVIEW", Instant.EPOCH);
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
