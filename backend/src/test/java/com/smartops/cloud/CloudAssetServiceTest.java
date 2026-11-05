package com.smartops.cloud;

import com.fasterxml.jackson.databind.ObjectMapper;
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

import java.time.LocalDateTime;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * OPS-02 / OPS-03 服务层验证：
 * 同一资源重复同步不重复建档、MISSING/DELETED/STALE 可区分、
 * 部分失败不误判资源消失、跨团队请求被拒绝、业务影响视图带关系依据。
 */
class CloudAssetServiceTest {

    private static final SessionUser OWNER = new SessionUser(7L, "alice", "user");
    private static final SessionUser OUTSIDER = new SessionUser(1L, "bob", "user");

    private JdbcTemplate jdbc;
    private CloudAssetService service;
    private FakeProvider provider;
    private long accountDbId;
    private String cloudAccountId;

    @BeforeEach
    void setUp() {
        DriverManagerDataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:cloud-asset-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        new ResourceDatabasePopulator(
                new ClassPathResource("schema.sql"),
                new ClassPathResource("db/migration/V20261105.4__cloud_assets.sql")
        ).execute(source);
        jdbc = new JdbcTemplate(source);
        jdbc.execute("CREATE TABLE IF NOT EXISTS app_user (id BIGINT PRIMARY KEY, enabled BOOLEAN NOT NULL DEFAULT TRUE)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_workspace (id BIGINT PRIMARY KEY, status VARCHAR(32) NOT NULL)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_member (team_id BIGINT NOT NULL, user_id BIGINT NOT NULL, role VARCHAR(32) NOT NULL)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_member_capability (team_id BIGINT NOT NULL, user_id BIGINT NOT NULL, capability VARCHAR(32) NOT NULL)");

        AesGcmCryptoService crypto = new AesGcmCryptoService(Base64.getEncoder().encodeToString(bytes()));
        provider = new FakeProvider();
        service = new CloudAssetService(
                new CloudAssetRepository(jdbc),
                new CloudCredentialResolver(jdbc, crypto),
                new TeamResourceAuthorizer(jdbc),
                List.of(provider),
                new ObjectMapper(),
                2, 5, 60);
    }

    @Test
    void repeatedSyncUpdatesTheSameResourceInsteadOfDuplicatingIt() {
        createAccount("credential:" + insertCredential("AKID", "SECRET"));
        provider.pages = List.of(List.of(host("i-1"), host("i-2")));

        CloudAssetService.SyncResult first = service.sync(OWNER, accountDbId);
        assertThat(first.status()).isEqualTo("SUCCEEDED");
        assertThat(first.created()).isEqualTo(2);
        assertThat(assetCount()).isEqualTo(2);

        CloudAssetService.SyncResult second = service.sync(OWNER, accountDbId);
        assertThat(second.created()).isZero();
        assertThat(second.updated()).isEqualTo(2);
        assertThat(assetCount()).isEqualTo(2);
        assertThat(jdbc.queryForObject("SELECT first_seen_at FROM asset_resource WHERE resource_uid=?",
                java.sql.Timestamp.class, uid("i-1"))).isNotNull();
    }

    @Test
    void missingDeletedAndStaleAreDistinguishable() {
        createAccount("credential:" + insertCredential("AKID", "SECRET"));
        provider.pages = List.of(List.of(host("i-1"), host("i-2")));
        service.sync(OWNER, accountDbId);

        provider.pages = List.of(List.of(host("i-1")));
        CloudAssetService.SyncResult second = service.sync(OWNER, accountDbId);
        assertThat(second.markedMissing()).isEqualTo(1);

        Map<String, CloudAssetService.ResourceView> items = byUid(
                service.resources(OWNER, "checkout", "prod", null, null, null, 1, 100));
        assertThat(items.get(uid("i-1")).status()).isEqualTo("ACTIVE");
        assertThat(items.get(uid("i-2")).status()).isEqualTo("MISSING");

        CloudAssetService.ResourceView deleted = service.markStatus(OWNER, uid("i-2"),
                new CloudAssetService.StatusRequest("DELETED", "云控制台已释放该实例"));
        assertThat(deleted.status()).isEqualTo("DELETED");
        assertThat(deleted.statusReason()).contains("云控制台");

        // 采集时间回拨到两小时前：只影响展示的 STALE，不改写库里的 ACTIVE
        jdbc.update("UPDATE asset_resource SET collected_at=?, last_seen_at=? WHERE resource_uid=?",
                java.sql.Timestamp.valueOf(LocalDateTime.now().minusHours(2)),
                java.sql.Timestamp.valueOf(LocalDateTime.now().minusHours(2)), uid("i-1"));
        assertThat(byUid(service.resources(OWNER, "checkout", "prod", null, null, null, 1, 100))
                .get(uid("i-1")).status()).isEqualTo("STALE");
        assertThat(jdbc.queryForObject("SELECT status FROM asset_resource WHERE resource_uid=?",
                String.class, uid("i-1"))).isEqualTo("ACTIVE");
    }

    @Test
    void partialFailureKeepsExistingResourcesInsteadOfMarkingThemMissing() {
        createAccount("credential:" + insertCredential("AKID", "SECRET"));
        provider.pages = List.of(List.of(host("i-1"), host("i-2")));
        service.sync(OWNER, accountDbId);

        provider.failure = new CloudProviderException("CLOUD_RATE_LIMITED", "云 API 限流，已停止本次同步");
        provider.failAtPage = 1;
        provider.pages = List.of(List.of(host("i-1")), List.of(host("i-2")));

        CloudAssetService.SyncResult partial = service.sync(OWNER, accountDbId);
        assertThat(partial.status()).isEqualTo("PARTIAL");
        assertThat(partial.markedMissing()).isZero();
        assertThat(partial.errorCode()).isEqualTo("CLOUD_RATE_LIMITED");
        assertThat(jdbc.queryForObject("SELECT status FROM asset_resource WHERE resource_uid=?",
                String.class, uid("i-2"))).isEqualTo("ACTIVE");
    }

    @Test
    void crossTeamAccountIsRejectedAndHiddenFromListing() {
        jdbc.update("INSERT INTO app_user (id, enabled) VALUES (1, TRUE)");
        jdbc.update("INSERT INTO app_user (id, enabled) VALUES (2, TRUE)");
        jdbc.update("INSERT INTO team_workspace (id, status) VALUES (7, 'active')");
        jdbc.update("INSERT INTO team_member (team_id, user_id, role) VALUES (7, 2, 'owner')");
        insertAccount(7L, 2L, "env:SMARTOPS_TEST_UNSET_ALIYUN");

        assertThatThrownBy(() -> service.sync(OUTSIDER, accountDbId))
                .isInstanceOfSatisfying(BusinessException.class,
                        error -> assertThat(error.getCode()).isEqualTo(403));
        assertThat(service.accounts(OUTSIDER)).isEmpty();
        assertThat(service.accounts(new SessionUser(2L, "carol", "user"))).hasSize(1);
    }

    @Test
    void unavailableCredentialFailsTheRunWithoutLeakingAnything() {
        createAccount("env:SMARTOPS_TEST_UNSET_ALIYUN");
        CloudAssetService.SyncResult result = service.sync(OWNER, accountDbId);

        assertThat(result.status()).isEqualTo("FAILED");
        assertThat(result.errorCode()).isEqualTo("CLOUD_CREDENTIAL_UNAVAILABLE");
        assertThat(result.created()).isZero();
        assertThat(assetCount()).isZero();
    }

    @Test
    void businessImpactCarriesRelationEvidence() {
        createAccount("credential:" + insertCredential("AKID", "SECRET"));
        provider.pages = List.of(List.of(host("i-1"), database("db-1")));
        service.sync(OWNER, accountDbId);

        CloudAssetService.RelationView relation = service.declareRelation(OWNER,
                new CloudAssetService.DeclareRelationRequest(uid("db-1"), uid("i-1"), "HOSTED_ON",
                        "DBA 登记的数据库宿主关系（变更单 CHG-1024）"));
        assertThat(relation.source()).isEqualTo("DECLARED");

        CloudAssetService.ImpactView impact = service.businessImpact(OWNER, "checkout", "prod");
        assertThat(impact.byType()).containsEntry("HOST", 1L).containsEntry("DATABASE", 1L);
        assertThat(impact.byStatus()).containsEntry("ACTIVE", 2L);
        assertThat(impact.relations()).hasSize(1);
        assertThat(impact.relations().get(0).evidence()).contains("CHG-1024");
        CloudAssetService.ResourceView database = impact.resources().stream()
                .filter(view -> view.resourceType().equals("DATABASE")).findFirst().orElseThrow();
        assertThat(database.relations()).singleElement()
                .satisfies(edge -> {
                    assertThat(edge.direction()).isEqualTo("OUT");
                    assertThat(edge.relationType()).isEqualTo("HOSTED_ON");
                    assertThat(edge.otherUid()).isEqualTo(uid("i-1"));
                });
        assertThat(impact.incompleteAccounts()).isEmpty();
    }

    // ===================== 辅助 =====================

    private void createAccount(String credentialRef) {
        String rawAccountId = "account-" + UUID.randomUUID();
        CloudAssetService.AccountView view = service.createAccount(OWNER,
                new CloudAssetService.CreateAccountRequest(
                        "aliyun", rawAccountId, "只读账号", "cn-hangzhou", null, null, null, credentialRef));
        accountDbId = view.id();
        cloudAccountId = view.accountId();
    }

    private long insertCredential(String accessKeyId, String secret) {
        AesGcmCryptoService crypto = new AesGcmCryptoService(Base64.getEncoder().encodeToString(bytes()));
        jdbc.update("INSERT INTO operation_credential (user_id, name, type, secret_ciphertext, last4) VALUES (?,?,?,?,?)",
                7L, "aliyun-readonly", "ACCESS_KEY", crypto.encrypt(accessKeyId + ":" + secret), "CRET");
        return jdbc.queryForObject("SELECT MAX(id) FROM operation_credential", Long.class);
    }

    private void insertAccount(long teamId, long ownerUserId, String credentialRef) {
        cloudAccountId = "team-account-" + UUID.randomUUID();
        jdbc.update("""
                INSERT INTO cloud_account
                    (provider, account_id, display_name, region, team_id, owner_user_id, credential_ref,
                     credential_scope, enabled, created_at, updated_at)
                VALUES ('aliyun', ?, '团队账号', 'cn-hangzhou', ?, ?, ?, 'READ_ONLY', TRUE, ?, ?)
                """,
                cloudAccountId, teamId, ownerUserId, credentialRef,
                java.sql.Timestamp.valueOf(LocalDateTime.now()), java.sql.Timestamp.valueOf(LocalDateTime.now()));
        accountDbId = jdbc.queryForObject("SELECT MAX(id) FROM cloud_account", Long.class);
    }

    private int assetCount() {
        Integer count = jdbc.queryForObject("SELECT COUNT(1) FROM asset_resource", Integer.class);
        return count == null ? 0 : count;
    }

    private Map<String, CloudAssetService.ResourceView> byUid(CloudAssetService.ResourcePage page) {
        Map<String, CloudAssetService.ResourceView> result = new LinkedHashMap<>();
        page.items().forEach(item -> result.put(item.uid(), item));
        return result;
    }

    private String uid(String providerResourceId) {
        String type = providerResourceId.startsWith("db") ? "DATABASE" : "HOST";
        return "aliyun:" + cloudAccountId + ":cn-hangzhou:" + type + ":" + providerResourceId;
    }

    private CloudResourceSnapshot host(String id) {
        return snapshot(id, "HOST", "host-" + id);
    }

    private CloudResourceSnapshot database(String id) {
        return snapshot(id, "DATABASE", "db-" + id);
    }

    private CloudResourceSnapshot snapshot(String id, String type, String name) {
        return new CloudResourceSnapshot(id, type, name, "cn-hangzhou", "Running",
                "1.2.3.4", "10.0.0.1", "prod", "checkout", "team-a",
                Map.of("environment", "prod", "business", "checkout"), Map.of("status", "Running"));
    }

    private static byte[] bytes() {
        byte[] key = new byte[32];
        for (int i = 0; i < key.length; i++) {
            key[i] = (byte) (i + 1);
        }
        return key;
    }

    private static final class FakeProvider implements CloudInventoryProvider {

        private List<List<CloudResourceSnapshot>> pages = List.of();
        private CloudProviderException failure;
        private int failAtPage = -1;

        @Override
        public CloudProvider provider() {
            return CloudProvider.ALIYUN;
        }

        @Override
        public CloudPage listInstances(CloudAccount account, CloudCredentials credentials, String cursor, int pageSize) {
            int page = cursor == null ? 0 : Integer.parseInt(cursor);
            if (failure != null && page == failAtPage) {
                throw failure;
            }
            if (page >= pages.size()) {
                return new CloudPage(List.of(), null, false);
            }
            boolean hasMore = page + 1 < pages.size();
            return new CloudPage(pages.get(page), hasMore ? String.valueOf(page + 1) : null, hasMore);
        }
    }
}
