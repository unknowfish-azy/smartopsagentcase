package com.smartops.operations;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OperationRedactorTest {
    @Test
    void removes_secret_values_from_a_command_or_output() {
        String redacted = OperationRedactor.redact("token=abc123 password: hunter2");
        assertThat(redacted).doesNotContain("abc123", "hunter2").contains("[REDACTED]");
    }
}
