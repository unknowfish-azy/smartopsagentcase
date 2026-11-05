package com.smartops.cloud;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import com.smartops.security.TeamResourceAuthorizer;
import jakarta.validation.constraints.NotBlank;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 云账号只读接入与轻量 CMDB 的服务层（OPS-02、OPS-03）。
 *
 * 边界：
 *   - 账号归属个人或团队；跨团队访问在服务层直接 403，不依赖前端过滤；
 *   - 同步只调用只读清单接口，不产生任何远端副作用，因此可以安全重跑；
 *   - 资源身份由 provider:account:region:type:resourceId 组成，重复同步只更新不新建；
 *   - 只有"全量分页成功取完"才把未出现的资源标为 MISSING，部分失败不改写资源状态；
 *   - 对外视图永不包含 AccessKeySecret（凭据只有 credential_ref）。
 */
@Service
public class CloudAssetService {

    private static final Set<String> RELATION_TYPES =
            Set.of("HOSTED_ON", "MEMBER_OF", "ROUTES_TO", "DEPENDS_ON", "RUNS_ON");
    private static final Set<String> MANUAL_STATUSES = Set.of("ACTIVE", "DELETED");

    private final CloudAssetRepository repository;
    private final CloudCredentialResolver credentials;
    private final TeamResourceAuthorizer authorizer;
    private final Map<CloudProvider, CloudInventoryProvider> providers;
    private final ObjectMapper mapper;
    private final int pageSize;
    private final int maxPages;
    private final long staleAfterSeconds;

    public CloudAssetService(
            CloudAssetRepository repository,
            CloudCredentialResolver credentials,
            TeamResourceAuthorizer authorizer,
            List<CloudInventoryProvider> providers,
            ObjectMapper mapper,
            @Value("${smartops.cloud.sync.page-size:50}") int pageSize,
            @Value("${smartops.cloud.sync.max-pages:20}") int maxPages,
            @Value("${smartops.cloud.stale-after-seconds:3600}") long staleAfterSeconds) {
        this.repository = repository;
        this.credentials = credentials;
        this.authorizer = authorizer;
        this.providers = providers.stream()
                .collect(Collectors.toMap(CloudInventoryProvider::provider, provider -> provider, (left, right) -> left));
        this.mapper = mapper;
        this.pageSize = Math.max(1, pageSize);
        this.maxPages = Math.max(1, maxPages);
        this.staleAfterSeconds = Math.max(60, staleAfterSeconds);
    }

    // ===================== 账号 =====================

    public AccountView createAccount(SessionUser actor, CreateAccountRequest request) {
        CloudProvider provider = parseProvider(request.provider());
        if (!provider.implemented()) {
            throw new BusinessException(400, "CLOUD_PROVIDER_NOT_IMPLEMENTED");
        }
        if (!CloudCredentialResolver.isValidRef(request.credentialRef())) {
            throw new BusinessException(400, "CLOUD_CREDENTIAL_REF_INVALID");
        }
        if (request.teamId() != null) {
            // 团队账号只有团队管理员可以创建，避免任何成员替全团队绑定密钥。
            authorizer.requireMember(actor, request.teamId(), "manage");
        }
        if (repository.findByProviderIdentity(provider, request.accountId(), request.region()).isPresent()) {
            throw new BusinessException(409, "CLOUD_ACCOUNT_EXISTS");
        }
        CloudAccount account = new CloudAccount(
                null, provider, request.accountId().trim(), request.displayName().trim(), request.region().trim(),
                blankToNull(request.endpoint()), blankToNull(request.projectId()),
                request.teamId(), actor.id(), request.credentialRef().trim(), "READ_ONLY", true,
                null, null, LocalDateTime.now());
        try {
            long id = repository.insertAccount(account);
            return toAccountView(repository.findAccount(id)
                    .orElseThrow(() -> new BusinessException(500, "CLOUD_ACCOUNT_WRITE_FAILED")));
        } catch (DuplicateKeyException e) {
            throw new BusinessException(409, "CLOUD_ACCOUNT_EXISTS");
        }
    }

    public List<AccountView> accounts(SessionUser actor) {
        return repository.listAccountsForUser(actor.id()).stream().map(this::toAccountView).toList();
    }

    public List<SyncRunResult> syncRuns(SessionUser actor, long accountId, int limit) {
        CloudAccount account = requireAccount(actor, accountId, "view");
        return repository.listSyncRuns(account.id(), Math.min(Math.max(1, limit), 100)).stream()
                .map(SyncRunResult::from)
                .toList();
    }

    // ===================== 同步 =====================

    public SyncResult sync(SessionUser actor, long accountId) {
        CloudAccount account = requireAccount(actor, accountId, "run");
        LocalDateTime startedAt = LocalDateTime.now();
        long startNanos = System.nanoTime();

        if (!account.provider().implemented() || !providers.containsKey(account.provider())) {
            // 未实现的厂商不返回"空清单成功"，而是 SKIPPED + 明确原因。
            return finish(account, actor, startedAt, startNanos, 0, "SKIPPED", 0, 0, 0, 0, 0, false,
                    "CLOUD_PROVIDER_NOT_IMPLEMENTED", account.provider().displayName() + " 尚无真实只读适配器");
        }

        CloudCredentials accessKey;
        try {
            accessKey = credentials.resolve(account.ownerUserId(), account.credentialRef());
        } catch (CloudProviderException e) {
            return finish(account, actor, startedAt, startNanos, 0, "FAILED", 0, 0, 0, 0, 0, false,
                    e.code(), e.getMessage());
        }

        // 先登记本次同步 run，资源行通过 last_sync_run_id 精确记账"本轮是否命中"，
        // 这样 MISSING 判定不依赖 DB 时间戳精度（同秒写入不会被误判）。
        long runId = repository.insertSyncRun(new CloudAssetRepository.SyncRunRecord(
                0, account.id(), actor.id(), "RUNNING", startedAt, null, 0, 0, 0, 0, 0, false, null, null));

        CloudInventoryProvider provider = providers.get(account.provider());
        List<CloudResourceSnapshot> snapshots = new ArrayList<>();
        CloudProviderException failure = null;
        String cursor = null;
        int pages = 0;
        boolean complete = false;

        while (true) {
            if (pages >= maxPages) {
                failure = new CloudProviderException("CLOUD_SYNC_PAGE_LIMIT",
                        "单次同步超过分页上限 " + maxPages + " 页，已停止并保留已取到的部分");
                break;
            }
            try {
                CloudPage page = provider.listInstances(account, accessKey, cursor, pageSize);
                pages++;
                snapshots.addAll(page.items());
                if (!page.hasMore() || page.nextCursor() == null || page.nextCursor().isBlank()) {
                    complete = true;
                    break;
                }
                cursor = page.nextCursor();
            } catch (CloudProviderException e) {
                failure = e;
                break;
            }
        }

        int created = 0;
        int updated = 0;
        for (CloudResourceSnapshot snapshot : snapshots) {
            UpsertOutcome outcome = upsert(account, snapshot, startedAt, runId);
            if (outcome == UpsertOutcome.CREATED) {
                created++;
            } else {
                updated++;
            }
        }

        int markedMissing = 0;
        if (complete) {
            markedMissing = repository.markMissing(account.id(), runId);
        }

        String status = failure == null ? "SUCCEEDED" : (pages > 0 ? "PARTIAL" : "FAILED");
        return finish(account, actor, startedAt, startNanos, runId, status, pages, snapshots.size(), created, updated,
                markedMissing, failure != null && failure.permissionDenied(),
                failure == null ? null : failure.code(), failure == null ? null : failure.getMessage());
    }

    private SyncResult finish(CloudAccount account, SessionUser actor, LocalDateTime startedAt, long startNanos,
                              long runId, String status, int pages, int discovered, int created, int updated,
                              int markedMissing, boolean permissionDenied, String errorCode, String errorMessage) {
        LocalDateTime endedAt = LocalDateTime.now();
        CloudAssetRepository.SyncRunRecord record = new CloudAssetRepository.SyncRunRecord(
                runId, account.id(), actor.id(), status, startedAt, endedAt, pages, discovered, created, updated,
                markedMissing, permissionDenied, errorCode, truncate(errorMessage));
        if (runId == 0) {
            runId = repository.insertSyncRun(record);
        } else {
            repository.updateSyncRun(record);
        }
        repository.updateSyncState(account.id(), endedAt, status);
        return new SyncResult(runId, status, pages, discovered, created, updated, markedMissing, permissionDenied,
                errorCode, errorMessage, Duration.ofNanos(System.nanoTime() - startNanos).toMillis());
    }

    private UpsertOutcome upsert(CloudAccount account, CloudResourceSnapshot snapshot, LocalDateTime collectedAt,
                                 long syncRunId) {
        if (snapshot.providerResourceId() == null || snapshot.providerResourceId().isBlank()) {
            throw new BusinessException(502, "CLOUD_RESOURCE_ID_MISSING");
        }
        String uid = resourceUid(account, snapshot);
        String tagsJson = writeJson(snapshot.tags());
        String metadataJson = writeJson(snapshot.providerMetadata());
        CloudAssetRepository.AssetWrite write = new CloudAssetRepository.AssetWrite(
                uid, account.provider().wireName(), account.accountId(),
                snapshot.region() == null || snapshot.region().isBlank() ? account.region() : snapshot.region(),
                snapshot.resourceType(), snapshot.providerResourceId(), snapshot.name(),
                snapshot.environment(), snapshot.business(), snapshot.owner(),
                account.id(), syncRunId, collectedAt, tagsJson, metadataJson);

        if (repository.findAssetIdByUid(uid).isEmpty()) {
            try {
                repository.insertAsset(write);
                return UpsertOutcome.CREATED;
            } catch (DuplicateKeyException race) {
                repository.updateAsset(write);
                return UpsertOutcome.UPDATED;
            }
        }
        repository.updateAsset(write);
        return UpsertOutcome.UPDATED;
    }

    public static String resourceUid(CloudAccount account, CloudResourceSnapshot snapshot) {
        String region = snapshot.region() == null || snapshot.region().isBlank() ? account.region() : snapshot.region();
        return account.provider().wireName() + ":" + account.accountId() + ":" + region + ":"
                + snapshot.resourceType() + ":" + snapshot.providerResourceId();
    }

    // ===================== CMDB 查询 =====================

    public ResourcePage resources(SessionUser actor, String business, String environment, String resourceType,
                                  String status, String keyword, int page, int size) {
        int safePage = Math.max(1, page);
        int safeSize = Math.min(Math.max(1, size), 100);
        LocalDateTime staleBefore = LocalDateTime.now().minusSeconds(staleAfterSeconds);
        CloudAssetRepository.AssetQuery query = new CloudAssetRepository.AssetQuery(
                blankToNull(business), blankToNull(environment), blankToNull(resourceType), blankToNull(status),
                blankToNull(keyword), safePage, safeSize).withUser(actor.id(), staleBefore);
        long total = repository.countAssets(query);
        List<ResourceView> items = repository.queryAssets(query).stream()
                .map(row -> toResourceView(row, staleBefore, List.of()))
                .toList();
        return new ResourcePage(total, safePage, safeSize, items);
    }

    public ResourceView resource(SessionUser actor, String resourceUid) {
        CloudAssetRepository.AssetRow row = requireAsset(resourceUid);
        requireAccount(actor, row.sourceAccountId(), "view");
        LocalDateTime staleBefore = LocalDateTime.now().minusSeconds(staleAfterSeconds);
        return toResourceView(row, staleBefore, relationsFor(List.of(resourceUid)));
    }

    public ResourceView markStatus(SessionUser actor, String resourceUid, StatusRequest request) {
        CloudAssetRepository.AssetRow row = requireAsset(resourceUid);
        requireAccount(actor, row.sourceAccountId(), "manage");
        String status = request.status() == null ? "" : request.status().trim().toUpperCase();
        if (!MANUAL_STATUSES.contains(status)) {
            throw new BusinessException(400, "ASSET_STATUS_INVALID");
        }
        String reason = blankToNull(request.evidence());
        if ("DELETED".equals(status) && reason == null) {
            throw new BusinessException(400, "ASSET_DELETE_EVIDENCE_REQUIRED");
        }
        if (reason != null && reason.length() > 500) {
            throw new BusinessException(400, "ASSET_STATUS_EVIDENCE_TOO_LONG");
        }
        repository.updateAssetStatus(resourceUid, status,
                reason == null ? "人工复核标记为 " + status : reason);
        return resource(actor, resourceUid);
    }

    public ImpactView businessImpact(SessionUser actor, String business, String environment) {
        if (business == null || business.isBlank()) {
            throw new BusinessException(400, "ASSET_BUSINESS_REQUIRED");
        }
        LocalDateTime staleBefore = LocalDateTime.now().minusSeconds(staleAfterSeconds);
        List<CloudAssetRepository.AssetRow> rows = repository.assetsByBusiness(actor.id(), business, blankToNull(environment), staleBefore);
        List<String> uids = rows.stream().map(CloudAssetRepository.AssetRow::resourceUid).toList();
        List<CloudAssetRepository.RelationRow> relationRows = repository.relationsAmong(uids);
        Map<String, List<RelationEdge>> edgesByUid = new LinkedHashMap<>();
        for (CloudAssetRepository.RelationRow relation : relationRows) {
            if (uids.contains(relation.fromUid())) {
                edgesByUid.computeIfAbsent(relation.fromUid(), key -> new ArrayList<>())
                        .add(new RelationEdge("OUT", relation.relationType(), relation.toUid(),
                                relation.source(), relation.evidence(), relation.updatedAt()));
            }
            if (uids.contains(relation.toUid())) {
                edgesByUid.computeIfAbsent(relation.toUid(), key -> new ArrayList<>())
                        .add(new RelationEdge("IN", relation.relationType(), relation.fromUid(),
                                relation.source(), relation.evidence(), relation.updatedAt()));
            }
        }
        List<ResourceView> resources = rows.stream()
                .map(row -> toResourceView(row, staleBefore, edgesByUid.getOrDefault(row.resourceUid(), List.of())))
                .toList();

        Map<String, Long> byType = new LinkedHashMap<>();
        Map<String, Long> byStatus = new LinkedHashMap<>();
        for (CloudAssetRepository.AssetRow row : rows) {
            byType.merge(row.resourceType(), 1L, Long::sum);
            byStatus.merge(effectiveStatus(row, staleBefore), 1L, Long::sum);
        }
        List<RelationView> relations = relationRows.stream().map(RelationView::from).toList();
        List<AccountView> incomplete = repository.incompleteAccounts(actor.id(), business).stream()
                .map(this::toAccountView).toList();

        return new ImpactView(business.trim(), blankToNull(environment), LocalDateTime.now(), staleAfterSeconds,
                byType, byStatus, resources, relations, incomplete);
    }

    public RelationView declareRelation(SessionUser actor, DeclareRelationRequest request) {
        String type = request.relationType().trim().toUpperCase();
        if (!RELATION_TYPES.contains(type)) {
            throw new BusinessException(400, "ASSET_RELATION_TYPE_INVALID");
        }
        String evidence = request.evidence().trim();
        if (evidence.length() > 500) {
            throw new BusinessException(400, "ASSET_RELATION_EVIDENCE_TOO_LONG");
        }
        CloudAssetRepository.AssetRow from = requireAsset(request.fromUid().trim());
        CloudAssetRepository.AssetRow to = requireAsset(request.toUid().trim());
        requireAccount(actor, from.sourceAccountId(), "view");
        requireAccount(actor, to.sourceAccountId(), "view");
        repository.upsertRelation(from.resourceUid(), to.resourceUid(), type, "DECLARED", evidence);
        return repository.relationsAmong(List.of(from.resourceUid())).stream()
                .filter(relation -> relation.fromUid().equals(from.resourceUid())
                        && relation.toUid().equals(to.resourceUid())
                        && relation.relationType().equals(type))
                .findFirst()
                .map(RelationView::from)
                .orElseThrow(() -> new BusinessException(500, "ASSET_RELATION_WRITE_FAILED"));
    }

    // ===================== 授权与辅助 =====================

    private CloudAccount requireAccount(SessionUser actor, long accountId, String capability) {
        CloudAccount account = repository.findAccount(accountId)
                .orElseThrow(() -> new BusinessException(404, "CLOUD_ACCOUNT_NOT_FOUND"));
        authorize(actor, account, capability);
        return account;
    }

    private void authorize(SessionUser actor, CloudAccount account, String capability) {
        if (actor == null) {
            throw new BusinessException(403, "CLOUD_ACCESS_FORBIDDEN");
        }
        if (account.teamId() == null) {
            if (!account.ownerUserId().equals(actor.id())) {
                throw new BusinessException(403, "CLOUD_ACCOUNT_FORBIDDEN");
            }
            return;
        }
        // 团队账号：非成员一律拒绝；写操作需要 manage，同步需要 run。
        authorizer.requireMember(actor, account.teamId(), capability);
    }

    private CloudAssetRepository.AssetRow requireAsset(String resourceUid) {
        return repository.findAssetByUid(resourceUid)
                .orElseThrow(() -> new BusinessException(404, "ASSET_NOT_FOUND"));
    }

    private List<RelationEdge> relationsFor(List<String> uids) {
        List<RelationEdge> edges = new ArrayList<>();
        for (CloudAssetRepository.RelationRow relation : repository.relationsAmong(uids)) {
            if (uids.contains(relation.fromUid())) {
                edges.add(new RelationEdge("OUT", relation.relationType(), relation.toUid(),
                        relation.source(), relation.evidence(), relation.updatedAt()));
            }
            if (uids.contains(relation.toUid())) {
                edges.add(new RelationEdge("IN", relation.relationType(), relation.fromUid(),
                        relation.source(), relation.evidence(), relation.updatedAt()));
            }
        }
        return edges;
    }

    private ResourceView toResourceView(CloudAssetRepository.AssetRow row, LocalDateTime staleBefore,
                                        List<RelationEdge> relations) {
        long freshness = row.collectedAt() == null ? 0
                : Math.max(0, Duration.between(row.collectedAt(), LocalDateTime.now()).getSeconds());
        return new ResourceView(row.resourceUid(), row.provider(), row.providerAccountId(), row.region(),
                row.resourceType(), row.providerResourceId(), row.name(),
                effectiveStatus(row, staleBefore), row.statusReason(), row.environment(), row.business(), row.owner(),
                row.source(), row.collectedAt(), row.firstSeenAt(), row.lastSeenAt(), freshness,
                readMap(row.tagsJson()), readMap(row.metadataJson()), relations);
    }

    private AccountView toAccountView(CloudAccount account) {
        return new AccountView(account.id(), account.provider().wireName(), account.provider().displayName(),
                account.accountId(), account.displayName(), account.region(), account.projectId(), account.teamId(),
                account.credentialRef(), account.enabled(), account.lastSyncAt(), account.lastSyncStatus(),
                account.provider().implemented());
    }

    static String effectiveStatus(CloudAssetRepository.AssetRow row, LocalDateTime staleBefore) {
        if ("ACTIVE".equals(row.status()) && row.collectedAt() != null && row.collectedAt().isBefore(staleBefore)) {
            return "STALE";
        }
        return row.status();
    }

    private static CloudProvider parseProvider(String value) {
        try {
            return CloudProvider.fromWireName(value);
        } catch (CloudProviderException e) {
            throw new BusinessException(400, e.code());
        }
    }

    private Map<String, String> readMap(String json) {
        if (json == null || json.isBlank()) {
            return Map.of();
        }
        try {
            return mapper.readValue(json, new TypeReference<Map<String, String>>() {});
        } catch (Exception e) {
            return Map.of();
        }
    }

    private String writeJson(Map<String, String> value) {
        try {
            return mapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (Exception e) {
            throw new BusinessException(500, "CLOUD_ASSET_SERIALIZE_FAILED");
        }
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static String truncate(String value) {
        if (value == null) {
            return null;
        }
        return value.length() <= 500 ? value : value.substring(0, 500);
    }

    private enum UpsertOutcome { CREATED, UPDATED }

    // ===================== 对外记录 =====================

    public record CreateAccountRequest(
            @NotBlank String provider,
            @NotBlank String accountId,
            @NotBlank String displayName,
            @NotBlank String region,
            String endpoint,
            String projectId,
            Long teamId,
            @NotBlank String credentialRef
    ) {}

    public record StatusRequest(String status, String evidence) {}

    public record DeclareRelationRequest(
            @NotBlank String fromUid,
            @NotBlank String toUid,
            @NotBlank String relationType,
            @NotBlank String evidence
    ) {}

    public record AccountView(
            long id,
            String provider,
            String providerName,
            String accountId,
            String displayName,
            String region,
            String projectId,
            Long teamId,
            String credentialRef,
            boolean enabled,
            LocalDateTime lastSyncAt,
            String lastSyncStatus,
            boolean providerImplemented
    ) {}

    public record SyncResult(
            long runId,
            String status,
            int pages,
            int discovered,
            int created,
            int updated,
            int markedMissing,
            boolean permissionDenied,
            String errorCode,
            String errorMessage,
            long durationMs
    ) {}

    public record SyncRunResult(
            long id,
            long accountId,
            Long actorUserId,
            String status,
            LocalDateTime startedAt,
            LocalDateTime endedAt,
            int pages,
            int discovered,
            int created,
            int updated,
            int markedMissing,
            boolean permissionDenied,
            String errorCode,
            String errorMessage
    ) {
        static SyncRunResult from(CloudAssetRepository.SyncRunRecord record) {
            return new SyncRunResult(record.id(), record.accountId(), record.actorUserId(), record.status(),
                    record.startedAt(), record.endedAt(), record.pages(), record.discovered(), record.created(),
                    record.updated(), record.markedMissing(), record.permissionDenied(), record.errorCode(),
                    record.errorMessage());
        }
    }

    public record RelationEdge(
            String direction,
            String relationType,
            String otherUid,
            String source,
            String evidence,
            LocalDateTime updatedAt
    ) {}

    public record ResourceView(
            String uid,
            String provider,
            String providerAccountId,
            String region,
            String resourceType,
            String providerResourceId,
            String name,
            String status,
            String statusReason,
            String environment,
            String business,
            String owner,
            String source,
            LocalDateTime collectedAt,
            LocalDateTime firstSeenAt,
            LocalDateTime lastSeenAt,
            long freshnessSeconds,
            Map<String, String> tags,
            Map<String, String> metadata,
            List<RelationEdge> relations
    ) {}

    public record ResourcePage(long total, int page, int size, List<ResourceView> items) {}

    public record RelationView(
            long id,
            String fromUid,
            String toUid,
            String relationType,
            String source,
            String evidence,
            LocalDateTime updatedAt
    ) {
        static RelationView from(CloudAssetRepository.RelationRow row) {
            return new RelationView(row.id(), row.fromUid(), row.toUid(), row.relationType(), row.source(),
                    row.evidence(), row.updatedAt());
        }
    }

    public record ImpactView(
            String business,
            String environment,
            LocalDateTime generatedAt,
            long staleAfterSeconds,
            Map<String, Long> byType,
            Map<String, Long> byStatus,
            List<ResourceView> resources,
            List<RelationView> relations,
            List<AccountView> incompleteAccounts
    ) {}
}
