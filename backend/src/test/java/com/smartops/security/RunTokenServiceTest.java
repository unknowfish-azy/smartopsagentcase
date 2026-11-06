package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Base64;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RunTokenServiceTest {

    private static final String SECRET = "test-run-token-secret-0123456789";

    @Test
    void issuedTokenRoundTripsAndBindsSubjectAndRun() {
        RunTokenService service = new RunTokenService(SECRET, 300);
        RunTokenService.Issued issued = service.issue(42L);

        RunTokenService.Token token = service.verify(issued.token());

        assertEquals("42", token.subject());
        assertEquals(issued.runId(), token.runId());
        assertEquals(300, issued.ttlSeconds());
    }

    @Test
    void runIdsAreUniqueAndMatchTheSharedIdPattern() {
        RunTokenService service = new RunTokenService(SECRET, 300);
        RunTokenService.Issued first = service.issue(7L);
        RunTokenService.Issued second = service.issue(7L);

        assertNotEquals(first.runId(), second.runId());
        assertEquals(true, first.runId().matches("[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}"));
    }

    @Test
    void expiredTokenIsRejected() {
        RunTokenService service = new RunTokenService(SECRET, 300);
        RunTokenService.Issued issued = service.issue(1L, Instant.now().minusSeconds(400));

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.verify(issued.token()));

        assertEquals(401, failure.getCode());
        assertEquals("RUN_TOKEN_EXPIRED", failure.getMessage());
    }

    @Test
    void tamperedPayloadIsRejected() {
        RunTokenService service = new RunTokenService(SECRET, 300);
        RunTokenService.Issued issued = service.issue(1L);
        String[] parts = issued.token().split("\\.");
        String forgedPayload = Base64.getUrlEncoder().withoutPadding()
                .encodeToString("{\"sub\":\"999\",\"run\":\"run-forged\",\"iat\":1,\"exp\":9999999999}"
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8));

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.verify("v1." + forgedPayload + "." + parts[2]));

        assertEquals(401, failure.getCode());
        assertEquals("RUN_TOKEN_INVALID", failure.getMessage());
    }

    @Test
    void signatureFromAnotherSecretIsRejected() {
        RunTokenService issuer = new RunTokenService(SECRET, 300);
        RunTokenService verifier = new RunTokenService("another-secret-0123456789abcdef", 300);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> verifier.verify(issuer.issue(1L).token()));

        assertEquals(401, failure.getCode());
    }

    @Test
    void missingSecretFailsClosedInsteadOfIssuingUnverifiableTokens() {
        RunTokenService service = new RunTokenService("", 300);

        BusinessException failure = assertThrows(BusinessException.class,
                () -> service.issue(1L));

        assertEquals(503, failure.getCode());
        assertEquals("CHAT_RUN_TOKEN_NOT_CONFIGURED", failure.getMessage());
    }
}
