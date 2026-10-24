package com.smartops.diagnostics;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import static org.assertj.core.api.Assertions.*;

class DiagnosticProbeLimiterTest {
    @Test void enforcesUserAndGlobalCapsAndReleasesExactlyOnce() {
        var limiter = new DiagnosticProbeLimiter();
        var first = limiter.acquire(11L);
        var second = limiter.acquire(11L);
        assertThatThrownBy(() -> limiter.acquire(11L)).isInstanceOf(BusinessException.class);
        first.close(); first.close();
        var replacement = limiter.acquire(11L);
        assertThatThrownBy(() -> limiter.acquire(11L)).isInstanceOf(BusinessException.class);
        second.close(); replacement.close();
        var leases = new ArrayList<DiagnosticProbeLimiter.Lease>();
        for (long index = 1; index <= 8; index++) leases.add(limiter.acquire(index));
        assertThatThrownBy(() -> limiter.acquire(20L)).isInstanceOf(BusinessException.class);
        leases.forEach(DiagnosticProbeLimiter.Lease::close);
        try (var lease = limiter.acquire(20L)) { assertThat(lease).isNotNull(); }
    }
}
