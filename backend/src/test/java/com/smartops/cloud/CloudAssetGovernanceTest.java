package com.smartops.cloud;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import java.time.LocalDateTime;
import java.util.Base64;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * P0-02 补齐部分的服务层验证：资产变更历史、人工确认、Agent 执行前目标解析。
 *
 * <p>用真实迁移脚本建表，验证的是"人看到的变更"而不是方法被调用过。</p>
 */
class CloudAssetGovernanceTest {

    private static final SessionUser OWNER = new SessionUser(7L, "alice", "user");
    private static final SessionUser OUTSIDER = new SessionUser(1L, "bob", "user");
    private static final String PROVIDER_ACCOUNT = "acc-1";

    private JdbcTemplate jdbc;
    private CloudAssetRepository repository;
    private CloudAssetService service;
    private long accountDbId;

    @BeforeEach
    void setUp() {
        DriverManagerDataSource source = new DriverManagerDataSource(
                "jdbc:h2:mem:cloud-governance-" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", "");
        new ResourceDatabasePopulator(
                new ClassPathResource("schema.sql"),
                new ClassPathResource("db/migration/V20261105.4__cloud_assets.sql"),
                new ClassPathResource("db/migration/V20261105.5__asset_governance.sql"),
                new ClassPathResource("db/migration/V20261105.6__manual_assets.sql")
        ).execute(source);
        jdbc = new JdbcTemplate(source);
        repository = new CloudAssetRepository(jdbc);
        jdbc.execute("CREATE TABLE IF NOT EXISTS app_user (id BIGINT PRIMARY KEY, enabled BOOLEAN NOT NULL DEFAULT TRUE)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_workspace (id BIGINT PRIMARY KEY, status VARCHAR(32) NOT NULL)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_member (team_id BIGINT NOT NULL, user_id BIGINT NOT NULL, role VARCHAR(32) NOT NULL)");
        jdbc.execute("CREATE TABLE IF NOT EXISTS team_member_capability (team_id BIGINT NOT NULL, user_id BIGINT NOT NULL, capability VARCHAR(32) NOT NULL)");

        service = new CloudAssetService(repository,
                new CloudCredentialResolver(jdbc, new AesGcmCryptoService(
                        Base64.getEncoder().encodeToString(bytes()))),
                new TeamResourceAuthorizer(jdbc),
                List.of(),
                new ObjectMapper(),
                2, 5, 3600);

        jdbc.update("""
                INSERT INTO cloud_account
                    (provider, account_id, display_name, region, owner_user_id, credential_ref,
                     credential_scope, enabled, created_at, updated_at)
                VALUES ('aliyun', ?, '只读账号', 'cn-hangzhou', ?, 'env:AK', 'READ_ONLY', TRUE, ?, ?)
                """, PROVIDER_ACCOUNT, OWNER.id(), now(), now());
        accountDbId = jdbc.queryForObject("SELECT MAX(id) FROM cloud_account", Long.class);
    }

    @Test
    @DisplayName("变更历史：首次发现记一条，无变化的重复同步不记，真实变化才记")
    void changeHistoryOnlyRecordsRealChanges() {
        repository.insertAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));

        List<CloudAssetRepository.ChangeRow> afterDiscovery = repository.listChanges(uid("i-1"), 50);
        assertThat(afterDiscovery).hasSize(1);
        assertThat(afterDiscovery.get(0).changeType()).isEqualTo("DISCOVERED");

        // 内容完全一致的重复同步：不应产生噪音
        repository.updateAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));
        assertThat(repository.listChanges(uid("i-1"), 50)).hasSize(1);

        // 负责人变化：记一条 UPDATED，并保留改前改后
        repository.updateAsset(asset("i-1", "prod-web-01", "production", "order", "bob"));
        List<CloudAssetRepository.ChangeRow> afterOwnerChange = repository.listChanges(uid("i-1"), 50);
        assertThat(afterOwnerChange).hasSize(2);
        CloudAssetRepository.ChangeRow ownerRow = afterOwnerChange.get(0);
        assertThat(ownerRow.changeType()).isEqualTo("UPDATED");
        assertThat(ownerRow.fieldName()).isEqualTo("owner");
        assertThat(ownerRow.oldValue()).isEqualTo("alice");
        assertThat(ownerRow.newValue()).isEqualTo("bob");
    }

    @Test
    @DisplayName("失联判定写入时间线，而不是只改状态")
    void markMissingRecordsStatusChange() {
        repository.insertAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));

        int marked = repository.markMissing(accountDbId, 999L);

        assertThat(marked).isEqualTo(1);
        assertThat(repository.findAssetByUid(uid("i-1")).orElseThrow().status()).isEqualTo("MISSING");
        assertThat(repository.listChanges(uid("i-1"), 50))
                .anyMatch(row -> row.changeType().equals("STATUS_CHANGED")
                        && row.newValue().equals("MISSING"));
    }

    @Test
    @DisplayName("人工确认：必须给依据；CONFIRM 可补齐环境/负责人，REJECT 置为 DELETED")
    void confirmRequiresEvidenceAndUpdatesAttribution() {
        repository.insertAsset(asset("i-1", "prod-web-01", null, null, null));

        assertThatThrownBy(() -> service.confirm(OWNER, uid("i-1"),
                new CloudAssetService.ConfirmRequest("CONFIRM", " ", null, null, null)))
                .isInstanceOf(BusinessException.class);

        CloudAssetService.ResourceView confirmed = service.confirm(OWNER, uid("i-1"),
                new CloudAssetService.ConfirmRequest("CONFIRM", "已与业务方核对", "production", "order", "alice"));

        assertThat(confirmed.status()).isEqualTo("ACTIVE");
        assertThat(confirmed.environment()).isEqualTo("production");
        assertThat(confirmed.business()).isEqualTo("order");
        assertThat(confirmed.owner()).isEqualTo("alice");

        Integer confirmedRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM asset_change_event WHERE resource_uid=? AND change_type='CONFIRMED'",
                Integer.class, uid("i-1"));
        assertThat(confirmedRows).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT confirmed_by FROM asset_resource WHERE resource_uid=?",
                String.class, uid("i-1"))).isEqualTo("alice");

        CloudAssetService.ResourceView rejected = service.confirm(OWNER, uid("i-1"),
                new CloudAssetService.ConfirmRequest("REJECT", "该实例已下线", null, null, null));
        assertThat(rejected.status()).isEqualTo("DELETED");
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM asset_change_event WHERE resource_uid=? AND change_type='REJECTED'",
                Integer.class, uid("i-1"))).isEqualTo(1);
    }

    @Test
    @DisplayName("目标解析：唯一命中直接放行，并带回环境、负责人与授权范围")
    void resolveUniqueTargetReturnsContext() {
        repository.insertAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));

        CloudAssetService.TargetResolution resolution = service.resolveTarget(OWNER,
                new CloudAssetService.ResolveTargetRequest(uid("i-1"), null));

        assertThat(resolution.resolved()).isTrue();
        assertThat(resolution.requiresConfirmation()).isFalse();
        assertThat(resolution.reason()).isEqualTo("RESOLVED");
        assertThat(resolution.environment()).isEqualTo("production");
        assertThat(resolution.owner()).isEqualTo("alice");
        assertThat(resolution.authorizationScope()).isEqualTo("READ_ONLY");
        assertThat(resolution.asset().uid()).isEqualTo(uid("i-1"));
    }

    @Test
    @DisplayName("目标解析：查不到目标时必须转人工确认，不能猜")
    void resolveUnknownTargetRequiresConfirmation() {
        repository.insertAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));

        CloudAssetService.TargetResolution resolution = service.resolveTarget(OWNER,
                new CloudAssetService.ResolveTargetRequest("prod-db-01", null));

        assertThat(resolution.resolved()).isFalse();
        assertThat(resolution.requiresConfirmation()).isTrue();
        assertThat(resolution.reason()).isEqualTo("NO_MATCH");
    }

    @Test
    @DisplayName("目标解析：多条命中返回候选列表并转人工确认")
    void resolveAmbiguousTargetReturnsCandidates() {
        repository.insertAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));
        repository.insertAsset(asset("i-2", "prod-web-02", "production", "order", "alice"));

        CloudAssetService.TargetResolution resolution = service.resolveTarget(OWNER,
                new CloudAssetService.ResolveTargetRequest("prod-web", null));

        assertThat(resolution.resolved()).isFalse();
        assertThat(resolution.requiresConfirmation()).isTrue();
        assertThat(resolution.reason()).isEqualTo("AMBIGUOUS");
        assertThat(resolution.candidates()).hasSize(2);
    }

    @Test
    @DisplayName("目标解析：已失联资产不允许直接执行")
    void resolveMissingAssetRequiresConfirmation() {
        repository.insertAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));
        repository.updateAssetStatus(uid("i-1"), "MISSING", "全量同步未返回", "system");

        CloudAssetService.TargetResolution resolution = service.resolveTarget(OWNER,
                new CloudAssetService.ResolveTargetRequest(uid("i-1"), null));

        assertThat(resolution.resolved()).isFalse();
        assertThat(resolution.requiresConfirmation()).isTrue();
        assertThat(resolution.reason()).isEqualTo("ASSET_NOT_ACTIVE");
    }

    @Test
    @DisplayName("变更历史与目标解析都受账号归属限制，跨用户读不到")
    void governanceIsScopedToAccountOwner() {
        repository.insertAsset(asset("i-1", "prod-web-01", "production", "order", "alice"));

        assertThatThrownBy(() -> service.history(OUTSIDER, uid("i-1"), 50))
                .isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.resolveTarget(OUTSIDER,
                new CloudAssetService.ResolveTargetRequest(uid("i-1"), null)))
                .isInstanceOf(BusinessException.class);

        CloudAssetService.TargetResolution outsiderSearch = service.resolveTarget(OUTSIDER,
                new CloudAssetService.ResolveTargetRequest("prod-web-01", null));
        assertThat(outsiderSearch.resolved()).isFalse();
        assertThat(outsiderSearch.reason()).isEqualTo("NO_MATCH");
    }

    @Test
    @DisplayName("手工登记：无云账号也能进入 CMDB，且云端列表照常可用")
    void registerManualAssetWithoutCloudAccount() {
        CloudAssetService.ResourceView registered = service.registerManualAsset(OWNER,
                new CloudAssetService.ManualAssetRequest("DATABASE", "prod-mysql-01", "production",
                        "order", "alice", "idc", "db-01", null,
                        java.util.Map.of("engine", "mysql"), java.util.Map.of("port", "3306")));

        assertThat(registered.uid()).isEqualTo("manual:database:prod-mysql-01");
        assertThat(registered.status()).isEqualTo("ACTIVE");
        assertThat(registered.source()).isEqualTo("MANUAL");
        assertThat(registered.environment()).isEqualTo("production");
        assertThat(registered.owner()).isEqualTo("alice");

        // 归属的是登记人，不是云账号
        assertThat(jdbc.queryForObject("SELECT source_account_id FROM asset_resource WHERE resource_uid=?",
                Long.class, registered.uid())).isNull();
        assertThat(jdbc.queryForObject("SELECT owner_user_id FROM asset_resource WHERE resource_uid=?",
                Long.class, registered.uid())).isEqualTo(OWNER.id());
    }

    @Test
    @DisplayName("手工登记：可见范围只给登记人，其他人既看不到详情也搜不到")
    void manualAssetIsVisibleOnlyToRegistrant() {
        CloudAssetService.ResourceView registered = service.registerManualAsset(OWNER,
                new CloudAssetService.ManualAssetRequest("MIDDLEWARE", "prod-redis-01", "production",
                        "order", "alice", "idc", null, null, null, null));

        assertThat(service.resource(OWNER, registered.uid()).name()).isEqualTo("prod-redis-01");
        assertThatThrownBy(() -> service.resource(OUTSIDER, registered.uid()))
                .isInstanceOf(BusinessException.class);
        assertThatThrownBy(() -> service.history(OUTSIDER, registered.uid(), 50))
                .isInstanceOf(BusinessException.class);

        long ownerVisible = service.resources(OWNER, null, null, null, null, "prod-redis", 1, 20).total();
        long outsiderVisible = service.resources(OUTSIDER, null, null, null, null, "prod-redis", 1, 20).total();
        assertThat(ownerVisible).isEqualTo(1);
        assertThat(outsiderVisible).isZero();
    }

    @Test
    @DisplayName("手工登记：类型必须在清单范围内，重复登记被拒绝")
    void manualRegistrationValidatesTypeAndUniqueness() {
        assertThatThrownBy(() -> service.registerManualAsset(OWNER,
                new CloudAssetService.ManualAssetRequest("PRINTER", "printer-01", "production",
                        null, "alice", null, null, null, null, null)))
                .isInstanceOf(BusinessException.class);

        service.registerManualAsset(OWNER, new CloudAssetService.ManualAssetRequest("DOMAIN",
                "api.example.com", "production", null, "alice", null, null, null, null, null));

        assertThatThrownBy(() -> service.registerManualAsset(OWNER, new CloudAssetService.ManualAssetRequest(
                "DOMAIN", "api.example.com", "production", null, "alice", null, null, null, null, null)))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    @DisplayName("手工登记：登记动作进入变更历史，actor 是人不是系统")
    void manualRegistrationWritesActorIntoHistory() {
        CloudAssetService.ResourceView registered = service.registerManualAsset(OWNER,
                new CloudAssetService.ManualAssetRequest("HOST", "idc-db-01", "production",
                        "order", "alice", "idc", null, null, null, null));

        List<CloudAssetService.ChangeView> history = service.history(OWNER, registered.uid(), 20);

        assertThat(history).hasSize(1);
        assertThat(history.get(0).changeType()).isEqualTo("DISCOVERED");
        assertThat(history.get(0).actor()).isEqualTo("alice");
    }

    @Test
    @DisplayName("手工登记：目标解析可用，授权范围标记为 MANUAL")
    void resolveManualAssetUsesManualScope() {
        CloudAssetService.ResourceView registered = service.registerManualAsset(OWNER,
                new CloudAssetService.ManualAssetRequest("K8S_CLUSTER", "prod-k8s", "production",
                        "order", "alice", "idc", null, null, null, null));

        CloudAssetService.TargetResolution resolution = service.resolveTarget(OWNER,
                new CloudAssetService.ResolveTargetRequest("prod-k8s", null));

        assertThat(resolution.resolved()).isTrue();
        assertThat(resolution.authorizationScope()).isEqualTo("MANUAL");
        assertThat(resolution.environment()).isEqualTo("production");
        assertThat(resolution.owner()).isEqualTo("alice");
        assertThat(resolution.asset().uid()).isEqualTo(registered.uid());
    }

    private CloudAssetRepository.AssetWrite asset(String providerResourceId, String name,
                                                  String environment, String business, String owner) {
        return new CloudAssetRepository.AssetWrite(uid(providerResourceId), "aliyun", PROVIDER_ACCOUNT,
                "cn-hangzhou", "ecs", providerResourceId, name, environment, business, owner,
                accountDbId, 1L, LocalDateTime.now(), "{}", "{\"privateIp\":\"10.0.0.11\"}");
    }

    private static String uid(String providerResourceId) {
        return "aliyun:" + PROVIDER_ACCOUNT + ":cn-hangzhou:ecs:" + providerResourceId;
    }

    private static java.sql.Timestamp now() {
        return java.sql.Timestamp.valueOf(LocalDateTime.now());
    }

    private static byte[] bytes() {
        byte[] key = new byte[32];
        for (int i = 0; i < key.length; i++) {
            key[i] = (byte) (i + 1);
        }
        return key;
    }
}
