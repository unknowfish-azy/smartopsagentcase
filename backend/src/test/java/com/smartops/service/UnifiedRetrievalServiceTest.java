package com.smartops.service;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class UnifiedRetrievalServiceTest {

    @Test
    void scoreFullMatchReturnsOne() {
        assertThat(UnifiedRetrievalService.score("nginx 502", "nginx 502 bad gateway")).isEqualTo(1.0);
    }

    @Test
    void scoreNoMatchReturnsZero() {
        assertThat(UnifiedRetrievalService.score("redis timeout", "nginx 502")).isEqualTo(0.0);
    }

    @Test
    void scorePartialMatch() {
        double score = UnifiedRetrievalService.score("nginx 502", "nginx error");
        assertThat(score).isGreaterThan(0).isLessThan(1.0);
    }

    @Test
    void scoreEmptyInputs() {
        assertThat(UnifiedRetrievalService.score(null, "text")).isEqualTo(0.0);
        assertThat(UnifiedRetrievalService.score("query", null)).isEqualTo(0.0);
        assertThat(UnifiedRetrievalService.score("", "text")).isEqualTo(0.0);
    }

    @Test
    void scoreCaseInsensitive() {
        assertThat(UnifiedRetrievalService.score("NGINX", "nginx error")).isEqualTo(1.0);
    }
}
