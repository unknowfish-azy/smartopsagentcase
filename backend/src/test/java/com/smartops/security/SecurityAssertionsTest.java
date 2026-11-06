package com.smartops.security;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SecurityAssertionsTest {

    private static final String TOKEN = "internal-token-0123456789";
    private static final String CHAT_SECRET = "chat-run-token-secret-0123456789";

    @Test
    void productionRejectsInternalBypass() {
        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verify(true, true, TOKEN, CHAT_SECRET));

        assertTrue(failure.getMessage().contains("SECURITY_ASSERTION_FAILED"));
        assertTrue(failure.getMessage().contains("SMARTOPS_INTERNAL_BYPASS"));
    }

    @Test
    void productionRejectsMissingOrWeakInternalToken() {
        IllegalStateException missing = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verify(true, false, "", CHAT_SECRET));
        assertTrue(missing.getMessage().contains("SMARTOPS_INTERNAL_TOKEN 未配置"));

        IllegalStateException weak = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verify(true, false, "short", CHAT_SECRET));
        assertTrue(weak.getMessage().contains("长度不足"));
    }

    @Test
    void productionRejectsMissingChatRunTokenSecret() {
        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verify(true, false, TOKEN, ""));

        assertTrue(failure.getMessage().contains("SMARTOPS_CHAT_RUN_TOKEN_SECRET"));
    }

    @Test
    void productionAggregatesAllFailuresInOneMessage() {
        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verify(true, true, "", ""));

        assertTrue(failure.getMessage().contains("SMARTOPS_INTERNAL_BYPASS"));
        assertTrue(failure.getMessage().contains("SMARTOPS_INTERNAL_TOKEN"));
        assertTrue(failure.getMessage().contains("SMARTOPS_CHAT_RUN_TOKEN_SECRET"));
    }

    @Test
    void productionAcceptsCompleteConfiguredSecrets() {
        assertDoesNotThrow(() -> SecurityAssertions.verify(true, false, TOKEN, CHAT_SECRET));
    }

    @Test
    void nonProductionDoesNotBlockLocalDebugging() {
        assertDoesNotThrow(() -> SecurityAssertions.verify(false, true, "", ""));
    }

    @Test
    void productionIsDetectedFromProfilesOrExplicitFlag() {
        assertTrue(SecurityAssertions.isProduction(List.of("dev", "PROD"), false));
        assertTrue(SecurityAssertions.isProduction(List.of("production"), false));
        assertEquals(false, SecurityAssertions.isProduction(List.of("dev"), false));
        assertTrue(SecurityAssertions.isProduction(List.of(), true));
    }

    @Test
    void productionRejectsMissingDeploymentPasswords() {
        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verifyDeploymentSecrets(true, "", "", ""));

        assertTrue(failure.getMessage().contains("MYSQL_PASSWORD 未配置"));
        assertTrue(failure.getMessage().contains("REDIS_PASSWORD 未配置"));
        assertTrue(failure.getMessage().contains("SMARTOPS_API_KEY_ENCRYPTION_KEY 未配置"));
    }

    @Test
    void productionRejectsKnownDefaultPasswords() {
        IllegalStateException mysqlDefault = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verifyDeploymentSecrets(true, "change-me-password", "strong-pass", "key"));
        assertTrue(mysqlDefault.getMessage().contains("已知默认口令"));

        IllegalStateException redisDefault = assertThrows(IllegalStateException.class,
                () -> SecurityAssertions.verifyDeploymentSecrets(true, "strong-pass", "change-me-root-password", "key"));
        assertTrue(redisDefault.getMessage().contains("已知默认口令"));
    }

    @Test
    void productionAcceptsInjectedDeploymentSecrets() {
        assertDoesNotThrow(() -> SecurityAssertions.verifyDeploymentSecrets(
                true, "injected-strong-mysql-pass", "injected-strong-redis-pass", "base64key"));
    }

    @Test
    void nonProductionAllowsEmptyDeploymentPasswordsForLocalDev() {
        assertDoesNotThrow(() -> SecurityAssertions.verifyDeploymentSecrets(false, "", "", ""));
    }
}
