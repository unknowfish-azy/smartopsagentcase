package com.smartops.logging;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * SEC-11 框架级日志脱敏单元测试：验证 LogMasker 对 Bearer token、URL 密钥参数、JSON 凭据字段的掩码。
 */
class LogMaskerTest {

    @Test
    void masksBearerToken() {
        assertThat(LogMasker.mask("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"))
                .isEqualTo("Authorization: Bearer ***");
    }

    @Test
    void masksUrlQueryParams() {
        assertThat(LogMasker.mask("GET /api/crawl?url=https://example.com&api_key=secret123&token=abc456"))
                .isEqualTo("GET /api/crawl?url=https://example.com&api_key=***&token=***");
    }

    @Test
    void masksJsonCredentialFields() {
        String json = "{\"password\":\"P@ssw0rd\",\"apiKey\":\"key-abc\",\"token\":\"tok-xyz\"}";
        String masked = LogMasker.mask(json);
        assertThat(masked).contains("\"password\":\"***\"");
        assertThat(masked).contains("\"apiKey\":\"***\"");
        assertThat(masked).contains("\"token\":\"***\"");
    }

    @Test
    void leavesNormalTextUntouched() {
        String normal = "User 123 created session successfully at 2026-11-07";
        assertThat(LogMasker.mask(normal)).isEqualTo(normal);
    }

    @Test
    void handlesNullAndEmpty() {
        assertThat(LogMasker.mask(null)).isNull();
        assertThat(LogMasker.mask("")).isEmpty();
    }
}
