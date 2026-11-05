package com.smartops.diagnostics.database;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** OPS-07：慢 SQL 与诊断语句的脱敏边界。 */
class SqlSanitizerTest {

    @Test
    void singleQuotedLiteralsAreReplacedAndTheOriginalValueDisappears() {
        String sanitized = SqlSanitizer.sanitize("SELECT * FROM users WHERE email='alice@example.com'");
        assertThat(sanitized).doesNotContain("alice@example.com");
        assertThat(sanitized).isEqualTo("SELECT * FROM users WHERE email=?");
    }

    @Test
    void quotedIdentifiersAndEscapedQuotesAreReplaced() {
        String sanitized = SqlSanitizer.sanitize("SELECT \"secret column\" FROM t WHERE name='O''Brien'");
        assertThat(sanitized).doesNotContain("secret column").doesNotContain("Brien");
        assertThat(sanitized).isEqualTo("SELECT ? FROM t WHERE name=?");
    }

    @Test
    void numbersAreReplaced() {
        assertThat(SqlSanitizer.sanitize("SELECT * FROM t LIMIT 100")).isEqualTo("SELECT * FROM t LIMIT ?");
        assertThat(SqlSanitizer.sanitize("SELECT 3.14")).isEqualTo("SELECT ?");
    }

    @Test
    void commentsAreStripped() {
        String sanitized = SqlSanitizer.sanitize("/* trace=abc */ SELECT 1 -- 业务备注\nFROM t");
        assertThat(sanitized).doesNotContain("trace=abc").doesNotContain("业务备注");
        assertThat(sanitized).isEqualTo("SELECT ? FROM t");
    }

    @Test
    void whitespaceIsCollapsedAndLongStatementsAreTruncated() {
        assertThat(SqlSanitizer.sanitize("SELECT\n\n  1 FROM   t")).isEqualTo("SELECT ? FROM t");
        String longSql = "SELECT " + "a".repeat(600);
        assertThat(SqlSanitizer.sanitize(longSql)).hasSize(300);
    }

    @Test
    void blankInputProducesEmptyText() {
        assertThat(SqlSanitizer.sanitize(null)).isEmpty();
        assertThat(SqlSanitizer.sanitize("   ")).isEmpty();
    }
}
