package com.smartops.diagnostics.database;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-07：以 H2 充当真实数据库，验证诊断五项覆盖、DATA_MISSING 不被误报为故障、
 * 凭据/引擎失败的可追溯性，以及越权请求不落审计。
 *
 * <p>连接由注入的 H2 {@link DatabaseConnectionProvider} 提供，
 * {@link MysqlDiagnosticAdapter} 真实参与，因此 performance_schema 缺失分支是真实走出来的。</p>
 */
class DatabaseDiagnosisServiceTest {

    private static final SessionUser ACTOR = new SessionUser(7L, "alice", "user");
    private static final SessionUser OUTSIDER = new SessionUser(1L, "bob", "user");
    private static final String PASSWORD = "S3cr3tPa55word";

    private JdbcTemplate jdbc;
    private DatabaseDiagnosisService service;
    private H2Provider provider;

    @BeforeEach
    void setUp() {
        String url = "jdbc:h2:mem:db-diag-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1";
        DriverManagerDataSource source = new DriverManagerDataSource(url, "sa", "sa");
        new ResourceDatabasePopulator(
                new ClassPathResource("schema.sql"),
                new ClassPathResource("db/migration/V20261105.9__database_diagnosis_audit.sql")
        ).execute(source);
        jdbc = new JdbcTemplate(source);
        jdbc.execute("CREATE TABLE IF NOT EXISTS app_user (id BIGINT PRIMARY KEY, enabled BOOLEAN NOT NULL DEFAULT TRUE)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_workspace (id BIGINT PRIMARY KEY, status VARCHAR(32) NOT NULL)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_member (team_id BIGINT NOT NULL, user_id BIGINT NOT NULL, role VARCHAR(32) NOT NULL)");

        AesGcmCryptoService crypto = new AesGcmCryptoService(Base64.getEncoder().encodeToString(bytes()));
        provider = new H2Provider(url);
        service = new DatabaseDiagnosisService(
                new DatabaseCredentialResolver(jdbc, crypto),
                new TeamResourceAuthorizer(jdbc),
                List.of(new MysqlDiagnosticAdapter()),
                jdbc,
                provider);
    }

    @Test
    void diagnosesFiveChecksAndWritesOneSucceededAuditRow() {
        long credentialId = insertCredential("dbreader", PASSWORD);

        DatabaseDiagnosisService.DatabaseDiagnosisResult result =
                service.diagnose(ACTOR, request("mysql", "credential:" + credentialId, null));

        assertThat(result.checks()).extracting(DatabaseCheck::name).containsExactly(
                "CONNECTIVITY", "READ_ONLY_SESSION", "LOCK_WAITS", "SLOW_SQL", "REPLICATION_LAG");
        assertThat(result.overallStatus()).isNotBlank();
        assertThat(provider.opens).isEqualTo(1);
        assertThat(provider.username).isEqualTo("dbreader");
        assertThat(provider.password).isEqualTo(PASSWORD);

        List<Map<String, Object>> audits = jdbc.queryForList(
                "SELECT status, error_code FROM database_diagnosis_audit");
        assertThat(audits).hasSize(1);
        assertThat(audits.get(0).get("status")).isEqualTo("SUCCEEDED");
        assertThat(audits.get(0).get("error_code")).isNull();
    }

    @Test
    void missingPerformanceSchemaIsDataMissingAndNeverFailed() {
        long credentialId = insertCredential("dbreader", PASSWORD);

        DatabaseDiagnosisService.DatabaseDiagnosisResult result =
                service.diagnose(ACTOR, request("MYSQL", "credential:" + credentialId, null));

        assertThat(statusOf(result, "LOCK_WAITS")).isEqualTo("DATA_MISSING");
        assertThat(statusOf(result, "SLOW_SQL")).isEqualTo("DATA_MISSING");
        assertThat(result.dataMissing()).isTrue();
        assertThat(result.overallStatus()).isNotEqualTo("FAILED");
    }

    @Test
    void missingCredentialFailsButLeavesAFailedAuditRowWithStableErrorCode() {
        assertThatThrownBy(() -> service.diagnose(ACTOR, request("mysql", "credential:999999", null)))
                .isInstanceOfSatisfying(BusinessException.class, error -> {
                    assertThat(error.getCode()).isEqualTo(502);
                    assertThat(error.getMessage()).contains("DB_CREDENTIAL_UNAVAILABLE");
                });

        List<Map<String, Object>> audits = jdbc.queryForList(
                "SELECT status, error_code FROM database_diagnosis_audit");
        assertThat(audits).hasSize(1);
        assertThat(audits.get(0).get("status")).isEqualTo("FAILED");
        assertThat(audits.get(0).get("error_code")).isEqualTo("DB_CREDENTIAL_UNAVAILABLE");
        assertThat(provider.opens).isZero();
    }

    @Test
    void unimplementedEngineIsRejectedWithoutConnecting() {
        assertThatThrownBy(() -> service.diagnose(ACTOR, request("postgresql", "env:SMARTOPS_TEST_UNSET_DB", null)))
                .isInstanceOfSatisfying(BusinessException.class, error -> {
                    assertThat(error.getCode()).isEqualTo(400);
                    assertThat(error.getMessage()).contains("DATABASE_ENGINE_NOT_IMPLEMENTED");
                    assertThat(error.getMessage()).contains("POSTGRESQL");
                });

        assertThat(provider.opens).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(1) FROM database_diagnosis_audit", Integer.class)).isZero();
    }

    @Test
    void nonTeamMemberIsForbiddenAndLeavesNoAuditRow() {
        jdbc.update("INSERT INTO app_user (id, enabled) VALUES (2, TRUE)");
        jdbc.update("INSERT INTO team_workspace (id, status) VALUES (7, 'active')");
        jdbc.update("INSERT INTO team_member (team_id, user_id, role) VALUES (7, 2, 'owner')");
        long credentialId = insertCredential("dbreader", PASSWORD);

        assertThatThrownBy(() -> service.diagnose(OUTSIDER, request("mysql", "credential:" + credentialId, 7L)))
                .isInstanceOfSatisfying(BusinessException.class,
                        error -> assertThat(error.getCode()).isEqualTo(403));

        assertThat(jdbc.queryForObject("SELECT COUNT(1) FROM database_diagnosis_audit", Integer.class)).isZero();
        assertThat(provider.opens).isZero();
    }

    @Test
    void resultAndAuditNeverContainThePasswordOrRawLiterals() {
        long credentialId = insertCredential("dbreader", PASSWORD);

        DatabaseDiagnosisService.DatabaseDiagnosisResult result =
                service.diagnose(ACTOR, request("mysql", "credential:" + credentialId, null));

        assertThat(result.toString()).doesNotContain(PASSWORD);
        for (DatabaseCheck check : result.checks()) {
            assertThat(check.toString()).doesNotContain(PASSWORD);
            assertThat(check.sql()).doesNotContain("'").doesNotContain(PASSWORD);
            assertThat(check.evidence()).doesNotContain(PASSWORD);
        }
        for (Map<String, Object> audit : jdbc.queryForList("SELECT * FROM database_diagnosis_audit")) {
            assertThat(audit.values().toString()).doesNotContain(PASSWORD);
        }
    }

    // ===================== 辅助 =====================

    private static String statusOf(DatabaseDiagnosisService.DatabaseDiagnosisResult result, String name) {
        return result.checks().stream()
                .filter(check -> check.name().equals(name))
                .findFirst()
                .orElseThrow()
                .status();
    }

    private DatabaseDiagnosisRequest request(String engine, String credentialRef, Long teamId) {
        return new DatabaseDiagnosisRequest(engine, "localhost", 3306, "appdb", credentialRef, teamId, 5, 50);
    }

    private long insertCredential(String username, String password) {
        AesGcmCryptoService crypto = new AesGcmCryptoService(Base64.getEncoder().encodeToString(bytes()));
        jdbc.update("INSERT INTO operation_credential (user_id, name, type, secret_ciphertext, last4) VALUES (?,?,?,?,?)",
                7L, "db-readonly", "DB_ACCOUNT", crypto.encrypt(username + ":" + password), "RDON");
        return jdbc.queryForObject("SELECT MAX(id) FROM operation_credential", Long.class);
    }

    private static byte[] bytes() {
        byte[] key = new byte[32];
        for (int i = 0; i < key.length; i++) {
            key[i] = (byte) (i + 1);
        }
        return key;
    }

    /** 真实 H2 连接：凭据由解析器解密后传入，这里只记录，用固定账号连库。 */
    private static final class H2Provider implements DatabaseConnectionProvider {

        private final String url;
        private int opens;
        private String username;
        private String password;

        private H2Provider(String url) {
            this.url = url;
        }

        @Override
        public Connection open(DatabaseTarget target, String username, String password) throws SQLException {
            opens++;
            this.username = username;
            this.password = password;
            return DriverManager.getConnection(url, "sa", "sa");
        }
    }
}
