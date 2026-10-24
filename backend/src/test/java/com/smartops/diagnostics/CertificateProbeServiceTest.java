package com.smartops.diagnostics;

import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;
import javax.net.ssl.SSLHandshakeException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class CertificateProbeServiceTest {
    @Test void certificateTimeoutHasItsOwnCategoryAndReleasesLease() throws Exception {
        var transport = mock(DiagnosticTransport.class);
        when(transport.certificate(any())).thenThrow(new java.net.SocketTimeoutException("private address"));
        var service = new CertificateProbeService(DiagnosticTargetPolicyTest.policy("203.0.113.10"), new DiagnosticProbeLimiter(), transport);
        for (int attempt = 0; attempt < 3; attempt++) {
            assertThat(service.check(DiagnosticTargetPolicyTest.user(11), "web").errorCategory()).isEqualTo("TIMEOUT");
        }
    }
    @Test void validCertificateShowsExpiryWhileFailedHandshakeNeverInventsDates() throws Exception {
        var transport = mock(DiagnosticTransport.class);
        var service = new CertificateProbeService(DiagnosticTargetPolicyTest.policy("203.0.113.10"), new DiagnosticProbeLimiter(), transport);
        var certificate = new DiagnosticTransport.CertificateResult("issuer", List.of("service.example"), Instant.now().minusSeconds(100), Instant.now().plusSeconds(3 * 86400));
        when(transport.certificate(any())).thenReturn(certificate);
        var result = service.check(DiagnosticTargetPolicyTest.user(11), "web");
        assertThat(result.severity()).isEqualTo("URGENT");
        assertThat(result.verified()).isTrue();
        when(transport.certificate(any())).thenThrow(new SSLHandshakeException("internal secret reason"));
        var failed = service.check(DiagnosticTargetPolicyTest.user(11), "web");
        assertThat(failed.status()).isEqualTo("UNHEALTHY");
        assertThat(failed.certificate()).isNull();
        assertThat(failed.summary()).doesNotContain("secret");
    }

    @Test
    void classifiesCertificateFailuresWithoutReturningExceptionDetails() throws Exception {
        var transport = mock(DiagnosticTransport.class);
        when(transport.certificate(any())).thenThrow(new javax.net.ssl.SSLHandshakeException("secret certificate detail"));
        var service = new CertificateProbeService(DiagnosticTargetPolicyTest.policy("203.0.113.10"), new DiagnosticProbeLimiter(), transport);
        var result = service.check(DiagnosticTargetPolicyTest.user(11), "web");
        assertThat(result.errorCategory()).isEqualTo("NETWORK");
        assertThat(result.summary()).doesNotContain("secret");
    }

}
