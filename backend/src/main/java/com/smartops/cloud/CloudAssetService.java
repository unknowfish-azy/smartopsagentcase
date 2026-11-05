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

    /** 手工登记允许的资产类型，对应清单要求的资产种类。 */
    private static final Set<String> MANUAL_ASSET_TYPES = Set.of(
            "HOST", "VM", "CONTAINER", "K8S_CLUSTER", "SERVICE",
            "DATABASE", "MIDDLEWARE", "DOMAIN", "IP");

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
        requireAssetAccess(actor, row, "view");
        LocalDateTime staleBefore = LocalDateTime.now().minusSeconds(staleAfterSeconds);
        return toResourceView(row, staleBefore, relationsFor(List.of(resourceUid)));
    }

    public ResourceView markStatus(SessionUser actor, String resourceUid, StatusRequest request) {
        CloudAssetRepository.AssetRow row = requireAsset(resourceUid);
        requireAssetAccess(actor, row, "manage");
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
        requireAssetAccess(actor, from, "view");
        requireAssetAccess(actor, to, "view");
        repository.upsertRelation(from.resourceUid(), to.resourceUid(), type, "DECLARED", evidence);
        return repository.relationsAmong(List.of(from.resourceUid())).stream()
                .filter(relation -> relation.fromUid().equals(from.resourceUid())
                        && relation.toUid().equals(to.resourceUid())
                        && relation.relationType().equals(type))
                .findFirst()
                .map(RelationView::from)
                .orElseThrow(() -> new BusinessException(500, "ASSET_RELATION_WRITE_FAILED"));
    }

    // ===================== 资产治理：变更历史 / 人工确认 / 目标解析 =====================

    /** 资产变更历史（采集侧与人工侧同一时间线）。 */
    public List<ChangeView> history(SessionUser actor, String resourceUid, int limit) {
        CloudAssetRepository.AssetRow row = requireAsset(resourceUid);
        requireAssetAccess(actor, row, "view");
        return repository.listChanges(resourceUid, limit).stream().map(ChangeView::from).toList();
    }

    /**
     * 人工确认资产。
     *
     * <p>CONFIRM：承认该资产存在，可同时补齐环境/业务/负责人；
     * REJECT：确认该资产应下线，状态置为 DELETED。两者都必须给出依据。</p>
     */
    public ResourceView confirm(SessionUser actor, String resourceUid, ConfirmRequest request) {
        CloudAssetRepository.AssetRow row = requireAsset(resourceUid);
        requireAssetAccess(actor, row, "manage");

        String decision = request.decision() == null ? "" : request.decision().trim().toUpperCase();
        if (!"CONFIRM".equals(decision) && !"REJECT".equals(decision)) {
            throw new BusinessException(400, "ASSET_CONFIRM_DECISION_INVALID");
        }
        String note = blankToNull(request.note());
        if (note == null) {
            throw new BusinessException(400, "ASSET_CONFIRM_NOTE_REQUIRED");
        }
        if (note.length() > 500) {
            throw new BusinessException(400, "ASSET_CONFIRM_NOTE_TOO_LONG");
        }

        String actorName = actor == null ? null : actor.username();
        String status = "CONFIRM".equals(decision) ? "ACTIVE" : "DELETED";

        // 先补齐归属，再写决策，保证历史里能看到"确认时把环境/负责人定成了什么"
        String environment = blankToNull(request.environment());
        String business = blankToNull(request.business());
        String owner = blankToNull(request.owner());
        if (environment != null || business != null || owner != null) {
            repository.updateAttribution(resourceUid, environment, business, owner);
            recordAttributionChanges(resourceUid, row, environment, business, owner, actorName, note);
        }
        repository.confirmAsset(resourceUid, status, actorName, note);
        repository.appendChange(new CloudAssetRepository.ChangeWrite(resourceUid,
                "CONFIRM".equals(decision) ? "CONFIRMED" : "REJECTED", "status",
                row.status(), status, actorName, note));
        return resource(actor, resourceUid);
    }

    /**
     * Agent 执行前的目标解析。
     *
     * <p>能唯一定位到 ACTIVE 资产才放行；查不到、匹配多条、资产已失联/删除
     * 都返回 {@code requiresConfirmation=true}，交由人工确认后再执行。</p>
     */
    public TargetResolution resolveTarget(SessionUser actor, ResolveTargetRequest request) {
        if (actor == null) {
            throw new BusinessException(403, "ASSET_RESOLVE_FORBIDDEN");
        }
        String target = request == null ? null : blankToNull(request.target());
        if (target == null) {
            throw new BusinessException(400, "ASSET_TARGET_REQUIRED");
        }
        LocalDateTime staleBefore = LocalDateTime.now().minusSeconds(staleAfterSeconds);

        // 1) 精确 resource_uid
        CloudAssetRepository.AssetRow exact = repository.findAssetByUid(target).orElse(null);
        if (exact != null) {
            requireAssetAccess(actor, exact, "view");
            return resolveFromRow(target, exact, staleBefore);
        }

        // 2) 名称 / 资源 ID / IP 关键字，限定在当前用户可见范围与环境内
        CloudAssetRepository.AssetQuery query = new CloudAssetRepository.AssetQuery(
                null, blankToNull(request.environment()), null, null, target, 1, 50)
                .withUser(actor.id(), staleBefore);
        List<CloudAssetRepository.AssetRow> matches = repository.queryAssets(query);

        if (matches.isEmpty()) {
            return new TargetResolution(target, false, true, "NO_MATCH",
                    null, null, null, null, null, List.of());
        }
        if (matches.size() > 1) {
            return new TargetResolution(target, false, true, "AMBIGUOUS",
                    null, null, null, null, null,
                    matches.stream().map(TargetResolution::candidate).toList());
        }
        return resolveFromRow(target, matches.get(0), staleBefore);
    }

    private TargetResolution resolveFromRow(String requested, CloudAssetRepository.AssetRow row,
                                            LocalDateTime staleBefore) {
        String status = effectiveStatus(row, staleBefore);
        if (!"ACTIVE".equals(status)) {
            return new TargetResolution(requested, false, true, "ASSET_NOT_ACTIVE",
                    toResourceView(row, staleBefore, List.of()), row.environment(), row.business(), row.owner(),
                    authorizationScope(row), List.of());
        }
        ResourceView view = toResourceView(row, staleBefore, relationsFor(List.of(row.resourceUid())));
        return new TargetResolution(requested, true, false, "RESOLVED", view,
                row.environment(), row.business(), row.owner(), authorizationScope(row), List.of());
    }

    private String authorizationScope(CloudAssetRepository.AssetRow row) {
        if (row.sourceAccountId() == null) {
            return "MANUAL";
        }
        return repository.findAccount(row.sourceAccountId())
                .map(CloudAccount::credentialScope)
                .orElse("MANUAL");
    }

    /**
     * 资产可见性：云资产按云账号归属，手工资产按登记人/所属团队。
     */
    private void requireAssetAccess(SessionUser actor, CloudAssetRepository.AssetRow row, String capability) {
        if (actor == null) {
            throw new BusinessException(403, "CLOUD_ASSET_FORBIDDEN");
        }
        if (row.sourceAccountId() != null) {
            requireAccount(actor, row.sourceAccountId(), capability);
            return;
        }
        if (row.ownerUserId() != null && row.ownerUserId().equals(actor.id())) {
            return;
        }
        if (row.teamId() != null) {
            authorizer.requireMember(actor, row.teamId(), capability);
            return;
        }
        throw new BusinessException(403, "CLOUD_ASSET_FORBIDDEN");
    }

    /**
     * 手工登记资产（无云账号）。
     *
     * <p>清单要求的类型（主机/VM/容器/K8s/服务/数据库/中间件/域名/IP）之外一律拒绝，
     * 避免 CMDB 变成自由文本表。登记即生效，同时写入变更历史。</p>
     */
    public ResourceView registerManualAsset(SessionUser actor, ManualAssetRequest request) {
        if (actor == null) {
            throw new BusinessException(403, "CLOUD_ASSET_FORBIDDEN");
        }
        String type = request.resourceType() == null ? "" : request.resourceType().trim().toUpperCase();
        if (!MANUAL_ASSET_TYPES.contains(type)) {
            throw new BusinessException(400, "ASSET_TYPE_UNSUPPORTED");
        }
        String name = blankToNull(request.name());
        if (name == null || name.length() > 120) {
            throw new BusinessException(400, "ASSET_NAME_INVALID");
        }
        String environment = blankToNull(request.environment());
        if (environment == null) {
            throw new BusinessException(400, "ASSET_ENVIRONMENT_REQUIRED");
        }
        String owner = blankToNull(request.owner());
        if (owner == null) {
            throw new BusinessException(400, "ASSET_OWNER_REQUIRED");
        }
        if (request.teamId() != null) {
            authorizer.requireMember(actor, request.teamId(), "manage");
        }

        String uid = manualUid(type, name);
        String tagsJson = writeJson(request.tags());
        String metadataJson = writeJson(request.metadata());
        try {
            repository.insertManualAsset(new CloudAssetRepository.ManualAssetWrite(uid,
                    blankToNull(request.region()) == null ? "manual" : request.region().trim(),
                    type, blankToNull(request.externalId()) == null ? uid : request.externalId().trim(),
                    name, environment, blankToNull(request.business()), owner,
                    tagsJson, metadataJson, actor.id(), request.teamId()));
        } catch (DuplicateKeyException duplicate) {
            throw new BusinessException(400, "ASSET_ALREADY_REGISTERED");
        }

        repository.appendChange(new CloudAssetRepository.ChangeWrite(uid, "DISCOVERED", "status",
                null, "ACTIVE", actor.username(), "人工登记资产：" + name));

        return resource(actor, uid);
    }

    private String manualUid(String type, String name) {
        String slug = name.trim().toLowerCase(java.util.Locale.ROOT)
                .replaceAll("[^a-z0-9\\u4e00-\\u9fa5]+", "-")
                .replaceAll("^-+|-+$", "");
        if (slug.isEmpty()) {
            slug = "asset";
        }
        if (slug.length() > 120) {
            slug = slug.substring(0, 120);
        }
        return "manual:" + type.toLowerCase(java.util.Locale.ROOT) + ":" + slug;
    }

    private void recordAttributionChanges(String resourceUid, CloudAssetRepository.AssetRow row,
                                          String environment, String business, String owner,
                                          String actorName, String note) {
        recordIfChanged(resourceUid, "environment", row.environment(), environment, actorName, note);
        recordIfChanged(resourceUid, "business", row.business(), business, actorName, note);
        recordIfChanged(resourceUid, "owner", row.owner(), owner, actorName, note);
    }

    private void recordIfChanged(String resourceUid, String field, String before, String after,
                                 String actorName, String note) {
        if (after == null || (before == null ? false : before.equals(after))) {
            return;
        }
        repository.appendChange(new CloudAssetRepository.ChangeWrite(resourceUid, "UPDATED", field,
                before, after, actorName, note));
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

    // ===================== 治理相关对外记录 =====================

    public record ConfirmRequest(
            @NotBlank String decision,
            @NotBlank String note,
            String environment,
            String business,
            String owner
    ) {}

    public record ResolveTargetRequest(@NotBlank String target, String environment) {}

    /** 手工登记资产请求。 */
    public record ManualAssetRequest(
            @NotBlank String resourceType,
            @NotBlank String name,
            String environment,
            String business,
            String owner,
            String region,
            String externalId,
            Long teamId,
            Map<String, String> tags,
            Map<String, String> metadata
    ) {}

    public record ChangeView(
            long id,
            String changeType,
            String fieldName,
            String oldValue,
            String newValue,
            String actor,
            String note,
            LocalDateTime changedAt
    ) {
        static ChangeView from(CloudAssetRepository.ChangeRow row) {
            return new ChangeView(row.id(), row.changeType(), row.fieldName(), row.oldValue(),
                    row.newValue(), row.actor(), row.note(), row.changedAt());
        }
    }

    /**
     * 目标解析结果。
     *
     * <p>{@code requiresConfirmation=true} 时执行器必须停下来等人工确认，
     * 不允许把 UNKNOWN 目标猜成某台机器继续跑。</p>
     */
    public record TargetResolution(
            String requested,
            boolean resolved,
            boolean requiresConfirmation,
            String reason,
            ResourceView asset,
            String environment,
            String business,
            String owner,
            String authorizationScope,
            List<TargetCandidate> candidates
    ) {
        static TargetCandidate candidate(CloudAssetRepository.AssetRow row) {
            return new TargetCandidate(row.resourceUid(), row.name(), row.resourceType(), row.environment(),
                    row.business(), row.owner(), row.status());
        }
    }

    public record TargetCandidate(
            String uid,
            String name,
            String resourceType,
            String environment,
            String business,
            String owner,
            String status
    ) {}
}
