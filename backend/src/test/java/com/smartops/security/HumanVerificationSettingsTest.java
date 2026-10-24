package com.smartops.security;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.*;

class HumanVerificationSettingsTest {
    @Test
    void disablingIsForbiddenForProductionAndUnknownEnvironments() {
        for (String profiles : new String[] { "prod", "prod,dev", "staging", "" }) {
            var environment = new MockEnvironment().withProperty("spring.profiles.active", profiles);
            assertThrows(IllegalStateException.class, () -> new HumanVerificationSettings(false, "", "", "", 600, true, environment));
        }
    }

    @Test
    void productionRejectsProviderTestKeys() {
        var production = new MockEnvironment().withProperty("spring.profiles.active", "prod");
        assertThrows(IllegalStateException.class, () -> new HumanVerificationSettings(true, "1x00000000000000000000AA", "secret", "ops.example.test", 600, true, production));
        assertThrows(IllegalStateException.class, () -> new HumanVerificationSettings(true, "site", "1x0000000000000000000000000000000AA", "ops.example.test", 600, true, production));
    }

    @Test
    void hostnamesAreExactNamesNotUrlsOrWildcards() {
        var environment = new MockEnvironment();
        assertTrue(new HumanVerificationSettings(true, "site", "secret", "OPS.EXAMPLE.TEST, internal.example.test", 600, true, environment).available());
        assertFalse(new HumanVerificationSettings(true, "site", "secret", "*.example.test", 600, true, environment).available());
        assertFalse(new HumanVerificationSettings(true, "site", "secret", "https://ops.example.test", 600, true, environment).available());
    }

    @Test
    void providerKindPrefersTurnstileAndFallsBackToOfflineGraphicalVerification() {
        var environment = new MockEnvironment();
        assertEquals("turnstile", new HumanVerificationSettings(true, "site", "secret", "ops.example.test", 600, true, environment).providerKind());
        assertEquals("local", new HumanVerificationSettings(true, "", "", "", 600, true, environment).providerKind());
        assertEquals("local", new HumanVerificationSettings(true, "site", "", "", 600, true, environment).providerKind());
    }

    @Test
    void responseTimeFloorIsBoundedAndDefaultsToTheHumanThreshold() {
        var environment = new MockEnvironment();
        assertEquals(600, new HumanVerificationSettings(true, "", "", "", 600, true, environment).minResponseMillis);
        assertEquals(0, new HumanVerificationSettings(true, "", "", "", -1, true, environment).minResponseMillis);
        assertEquals(1200, new HumanVerificationSettings(true, "", "", "", 1200, true, environment).minResponseMillis);
    }
}
