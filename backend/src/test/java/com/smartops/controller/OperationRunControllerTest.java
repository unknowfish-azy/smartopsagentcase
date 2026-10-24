package com.smartops.controller;

import com.smartops.service.OperationRunQueryService;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class OperationRunControllerTest {
    @Test
    void forwardsUserAndFiltersToListService() {
        var service = mock(OperationRunQueryService.class);
        var expected = new OperationRunQueryService.RunPage(List.of(), 0, 1, 20);
        var from = Instant.parse("2026-09-01T00:00:00Z");
        var to = Instant.parse("2026-10-01T00:00:00Z");
        when(service.list(7L, "trace", "docker.ps", "SUCCESS", from, to, 1, 20)).thenReturn(expected);

        var response = new OperationRunController(service).list(7L, "trace", "docker.ps", "SUCCESS", from, to, 1, 20);

        assertThat(response.getData()).isSameAs(expected);
        verify(service).list(7L, "trace", "docker.ps", "SUCCESS", from, to, 1, 20);
    }

    @Test
    void forwardsUserToDetailService() {
        var service = mock(OperationRunQueryService.class);
        var summary = new OperationRunQueryService.RunSummary(4L, "trace", 1L, "runtime", "linux.uptime", "SUCCESS",
                Instant.EPOCH, Instant.EPOCH.plusSeconds(1), 1, 0);
        var expected = new OperationRunQueryService.RunDetail(summary, List.of(), List.of());
        when(service.detail(8L, 4L)).thenReturn(expected);

        var response = new OperationRunController(service).detail(8L, 4L);

        assertThat(response.getData()).isSameAs(expected);
        verify(service).detail(8L, 4L);
    }
}
