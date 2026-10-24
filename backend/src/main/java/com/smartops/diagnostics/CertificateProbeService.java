package com.smartops.diagnostics;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.springframework.stereotype.Service;
import java.time.Duration;
import java.time.Instant;

@Service
public class CertificateProbeService {
    private final DiagnosticTargetPolicy policy;
    private final DiagnosticProbeLimiter limiter;
    private final DiagnosticTransport transport;

    public CertificateProbeService(DiagnosticTargetPolicy policy, DiagnosticProbeLimiter limiter, DiagnosticTransport transport) {
        this.policy = policy;
        this.limiter = limiter;
        this.transport = transport;
    }

    public Result check(SessionUser user, String targetId) {
        var target = policy.require(user, targetId);
        if (!"https".equals(target.uri().getScheme())) throw new BusinessException(400, "证书检查仅支持 HTTPS 目标");
        try (var lease = limiter.acquire(user.id())) {
            try {
                var certificate = transport.certificate(target);
                long days = Duration.between(Instant.now(), certificate.notAfter()).toDays();
                String severity = days < 0 ? "EXPIRED" : days <= 7 ? "URGENT" : days <= 30 ? "WARNING" : "HEALTHY";
                return new Result(severity.equals("HEALTHY") ? "HEALTHY" : "UNHEALTHY", severity, true, certificate,
                        "证书链和主机名校验通过", "按剩余天数安排续期", severity.equals("HEALTHY") ? null : "ASSERTION");
            } catch (java.net.SocketTimeoutException ex) {
                return new Result("UNHEALTHY", "CHECK_FAILED", false, null, "目标连接或读取超时", "检查网络后重试", "TIMEOUT");
            } catch (Exception ex) {
                return new Result("UNHEALTHY", "CHECK_FAILED", false, null, "TLS 握手或证书校验失败", "检查证书链、主机名和目标配置", "NETWORK");
            }
        }
    }

    public record Result(String status, String severity, boolean verified, DiagnosticTransport.CertificateResult certificate,
            String summary, String nextAction, String errorCategory) {
        public Result(String status, String severity, boolean verified, DiagnosticTransport.CertificateResult certificate,
                String summary, String nextAction) {
            this(status, severity, verified, certificate, summary, nextAction, null);
        }
    }
}
