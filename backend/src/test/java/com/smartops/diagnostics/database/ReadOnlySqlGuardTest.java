package com.smartops.diagnostics.database;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** OPS-07：只读 SQL 守卫的单语句与只读边界。 */
class ReadOnlySqlGuardTest {

    @Test
    void selectPassesThrough() {
        assertThat(ReadOnlySqlGuard.requireReadOnly("SELECT 1")).isEqualTo("SELECT 1");
    }

    @Test
    void showPassesThrough() {
        assertThat(ReadOnlySqlGuard.requireReadOnly("SHOW REPLICA STATUS")).isEqualTo("SHOW REPLICA STATUS");
    }

    @Test
    void leadingWhitespaceAndCommentsAreIgnored() {
        assertThat(ReadOnlySqlGuard.requireReadOnly("  /* 只读巡检 */\n SELECT COUNT(*) FROM t"))
                .isEqualTo("  /* 只读巡检 */\n SELECT COUNT(*) FROM t");
        assertThat(ReadOnlySqlGuard.requireReadOnly("-- 诊断\nSHOW VARIABLES"))
                .isEqualTo("-- 诊断\nSHOW VARIABLES");
    }

    @Test
    void multipleStatementsAreRejected() {
        assertRejected("SELECT 1; DROP TABLE users");
        assertRejected("SHOW TABLES; SELECT 1");
    }

    @Test
    void trailingSemicolonIsAccepted() {
        assertThat(ReadOnlySqlGuard.requireReadOnly("SELECT 1;")).isEqualTo("SELECT 1;");
    }

    @Test
    void mutatingStatementsAreRejected() {
        assertRejected("UPDATE users SET role='admin'");
        assertRejected("DELETE FROM users");
        assertRejected("INSERT INTO users (id) VALUES (1)");
    }

    @Test
    void lockingReadsAreRejected() {
        assertRejected("SELECT * FROM users FOR UPDATE");
        assertRejected("SELECT * FROM users LOCK IN SHARE MODE");
    }

    @Test
    void writingResultFilesIsRejected() {
        assertRejected("SELECT * FROM users INTO OUTFILE '/tmp/users.txt'");
        assertRejected("SELECT * FROM users INTO DUMPFILE '/tmp/users.bin'");
    }

    @Test
    void commentBypassIsRejected() {
        assertRejected("/* SELECT */ DELETE FROM users");
        assertRejected("-- SELECT\nDROP TABLE users");
    }

    private static void assertRejected(String sql) {
        assertThatThrownBy(() -> ReadOnlySqlGuard.requireReadOnly(sql))
                .isInstanceOfSatisfying(BusinessException.class, error -> {
                    assertThat(error.getCode()).isEqualTo(400);
                    assertThat(error.getMessage()).isEqualTo("DB_STATEMENT_NOT_READONLY");
                });
    }
}
