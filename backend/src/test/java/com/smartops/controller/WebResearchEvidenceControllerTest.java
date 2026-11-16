package com.smartops.controller;

import com.smartops.knowledge.WebResearchEvidenceService;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class WebResearchEvidenceControllerTest {
    private final SessionUser actor = new SessionUser(7L, "alice", "user");

    @Test
    void comparesOnlyRequestedSnapshotsForCurrentUser() {
        WebResearchEvidenceService evidence = mock(WebResearchEvidenceService.class);
        var comparison = new WebResearchEvidenceService.EvidenceComparison(
                List.of(), List.of(), "仅作人工核验", Instant.EPOCH);
        when(evidence.compare(actor, List.of(11L, 12L))).thenReturn(comparison);

        var response = new WebResearchController(null, null, null, evidence, null)
                .compare(actor, new WebResearchController.CompareRequest(List.of(11L, 12L)));

        assertThat(response.getData()).isSameAs(comparison);
        verify(evidence).compare(actor, List.of(11L, 12L));
    }

    @Test
    void readsCrawlDiffForCurrentUser() {
        WebResearchEvidenceService evidence = mock(WebResearchEvidenceService.class);
        var diff = new WebResearchEvidenceService.CrawlPageDiff(
                12L, 11L, "https://docs.example.com/guide", true, List.of(), List.of(), false, "仅供人工核验");
        when(evidence.diffCrawlPage(actor, 12L)).thenReturn(diff);

        var response = new KnowledgeCrawlController(null, evidence).diff(actor, 12L);

        assertThat(response.getData()).isSameAs(diff);
        verify(evidence).diffCrawlPage(actor, 12L);
    }
}
