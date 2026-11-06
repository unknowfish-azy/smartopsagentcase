package com.smartops.operations;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OperationRedactorTest {
    @Test
    void removes_secret_values_from_a_command_or_output() {
        String redacted = OperationRedactor.redact("token=abc123 password: hunter2");
        assertThat(redacted).doesNotContain("abc123", "hunter2").contains("[REDACTED]");
    }

    /** TM-30：env / Authorization / JSON 三种最常见泄漏形态都要遮蔽。 */
    @Test
    void masks_env_headers_and_json_forms() {
        String output = "API_TOKEN=abc123\n"
                + "DB_PASSWORD=hunter2\n"
                + "Authorization: Bearer xyz-789\n"
                + "{\"password\":\"s3cr3t\",\"apiKey\":\"k-123\"}";

        String redacted = OperationRedactor.redact(output);

        assertThat(redacted)
                .doesNotContain("abc123", "hunter2", "xyz-789", "s3cr3t", "k-123")
                .contains("[REDACTED]");
        // 键名保留，便于判断"哪一项被遮蔽"，但值不可回读。
        assertThat(redacted).contains("API_TOKEN=", "Authorization: ");
    }

    @Test
    void masks_private_key_blocks_and_cookie_headers() {
        String pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----";

        assertThat(OperationRedactor.redact(pem)).isEqualTo("[REDACTED]");
        assertThat(OperationRedactor.redact("Cookie: session=abcdef; theme=dark"))
                .doesNotContain("abcdef");
    }

    @Test
    void leaves_text_without_secrets_untouched() {
        String text = "kubectl get pods -n default\npod/api-0 1/1 Running";
        assertThat(OperationRedactor.redact(text)).isEqualTo(text);
        assertThat(OperationRedactor.redact(null)).isNull();
    }
}
