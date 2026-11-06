package com.smartops.cloud;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.LongConsumer;

/**
 * 华为云 ECS 只读清单适配器（OPS-02）。
 *
 * 只调用 {@code GET /v1/{project_id}/cloudservers/detail}，不调用任何写接口：
 *   - 分页：offset / limit，按返回的 count 判断是否还有下一页；
 *   - 限流：HTTP 429 / 5xx 按 Retry-After 或指数退避 + 抖动重试，次数有上限；
 *   - 权限：401/403 归类 CLOUD_PERMISSION_DENIED，不重试、不伪装成"空账号"；
 *   - 绑定：必须绑定 projectId，缺失时直接拒绝而不是拼出一个错误的 URL；
 *   - 签名：SDK-HMAC-SHA256（AccessKeySecret 只在内存中参与 HMAC，不出现在请求头与异常文本）。
 *
 * 说明：签名与错误映射由单元测试用替身传输验证；"真实云端调用已通过"
 * 必须由部署环境用只读 AK/SK 与项目 ID 另行验收。
 */
@Component
public class HuaweiEcsInventoryProvider implements CloudInventoryProvider {

    private static final String SIGNATURE_ALGORITHM = "SDK-HMAC-SHA256";
    private static final DateTimeFormatter SDK_DATE =
            DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC);
    private static final Set<Integer> RETRYABLE_STATUS = Set.of(429, 500, 502, 503, 504);

    private final CloudHttpTransport transport;
    private final ObjectMapper mapper;
    private final int maxAttempts;
    private final long baseBackoffMs;
    private final long maxBackoffMs;
    private final LongConsumer sleeper;

    @Autowired
    public HuaweiEcsInventoryProvider(
            CloudHttpTransport transport,
            ObjectMapper mapper,
            @Value("${smartops.cloud.sync.max-attempts:3}") int maxAttempts,
            @Value("${smartops.cloud.sync.backoff-base-ms:500}") long baseBackoffMs,
            @Value("${smartops.cloud.sync.backoff-max-ms:4000}") long maxBackoffMs) {
        this(transport, mapper, maxAttempts, baseBackoffMs, maxBackoffMs,
                ms -> { try { Thread.sleep(ms); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } });
    }

    HuaweiEcsInventoryProvider(
            CloudHttpTransport transport,
            ObjectMapper mapper,
            int maxAttempts,
            long baseBackoffMs,
            long maxBackoffMs,
            LongConsumer sleeper) {
        this.transport = transport;
        this.mapper = mapper;
        this.maxAttempts = Math.max(1, maxAttempts);
        this.baseBackoffMs = Math.max(50, baseBackoffMs);
        this.maxBackoffMs = Math.max(this.baseBackoffMs, maxBackoffMs);
        this.sleeper = sleeper;
    }

    @Override
    public CloudProvider provider() {
        return CloudProvider.HUAWEI;
    }

    @Override
    public CloudPage listInstances(CloudAccount account, CloudCredentials credentials, String cursor, int pageSize) {
        String projectId = account.projectId();
        if (projectId == null || projectId.isBlank()) {
            throw new CloudProviderException("CLOUD_PROJECT_ID_REQUIRED",
                    "华为云账号必须绑定 projectId 才能读取 ECS 清单");
        }
        int offset = parseOffset(cursor);
        int limit = Math.max(1, pageSize);

        String canonicalUri = "/v1/" + projectId.trim() + "/cloudservers/detail";
        String canonicalQuery = "limit=" + limit + "&offset=" + offset;
        String uri = account.endpointOrDefault() + canonicalUri + "?" + canonicalQuery;

        CloudHttpTransport.Response response = send(account.endpointOrDefault(), uri, canonicalUri, canonicalQuery,
                credentials);
        return parsePage(response.body(), offset, limit);
    }

    private CloudHttpTransport.Response send(String endpoint, String uri, String canonicalUri, String canonicalQuery,
                                             CloudCredentials credentials) {
        CloudProviderException lastError = null;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            CloudHttpTransport.Response response;
            try {
                response = transport.get(uri, signedHeaders(endpoint, canonicalUri, canonicalQuery, credentials));
            } catch (IOException | UnsupportedOperationException e) {
                lastError = new CloudProviderException("CLOUD_PROVIDER_UNREACHABLE",
                        "云 API 连接失败，请检查网络与端点配置", false, e);
                if (attempt == maxAttempts) {
                    throw lastError;
                }
                sleep(backoffMillis(attempt, null));
                continue;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new CloudProviderException("CLOUD_PROVIDER_INTERRUPTED", "云 API 调用被中断", false, e);
            }

            int status = response.status();
            if (status >= 200 && status < 300) {
                return response;
            }
            if (status == 401 || status == 403) {
                throw new CloudProviderException("CLOUD_PERMISSION_DENIED",
                        "云账号无权读取 ECS 清单，请检查只读 IAM 策略与项目范围", true, null);
            }
            if (RETRYABLE_STATUS.contains(status)) {
                lastError = new CloudProviderException(status == 429 ? "CLOUD_RATE_LIMITED" : "CLOUD_PROVIDER_UNAVAILABLE",
                        "云 API 暂时不可用（HTTP " + status + "）");
                if (attempt == maxAttempts) {
                    throw lastError;
                }
                sleep(backoffMillis(attempt, response.header("Retry-After")));
                continue;
            }
            throw new CloudProviderException("CLOUD_PROVIDER_ERROR", "云 API 返回 HTTP " + status);
        }
        throw lastError == null
                ? new CloudProviderException("CLOUD_PROVIDER_ERROR", "云 API 调用失败")
                : lastError;
    }

    private CloudPage parsePage(String body, int offset, int limit) {
        try {
            JsonNode root = mapper.readTree(body);
            List<CloudResourceSnapshot> items = new ArrayList<>();
            JsonNode servers = root.path("servers");
            if (servers.isArray()) {
                for (JsonNode server : servers) {
                    items.add(toSnapshot(server));
                }
            }
            long total = root.path("count").asLong(-1);
            boolean hasMore = total >= 0
                    ? (long) offset + limit < total
                    : items.size() >= limit;
            return new CloudPage(items, hasMore ? String.valueOf(offset + limit) : null, hasMore);
        } catch (IOException | RuntimeException e) {
            throw new CloudProviderException("CLOUD_RESPONSE_INVALID", "云 API 响应无法解析", false, e);
        }
    }

    private CloudResourceSnapshot toSnapshot(JsonNode server) {
        Map<String, String> tags = new LinkedHashMap<>();
        JsonNode tagArray = server.path("tags");
        if (tagArray.isArray()) {
            for (JsonNode tag : tagArray) {
                String key = tag.path("key").asText("");
                if (!key.isBlank()) {
                    tags.put(key, tag.path("value").asText(""));
                }
            }
        }
        String publicIp = null;
        String privateIp = null;
        JsonNode addresses = server.path("addresses");
        if (addresses.isArray()) {
            for (JsonNode address : addresses) {
                String ip = address.path("addr").asText("");
                if (ip.isBlank()) {
                    continue;
                }
                if ("floating".equalsIgnoreCase(address.path("OS-EXT-IPS:type").asText(""))) {
                    publicIp = publicIp == null ? ip : publicIp;
                } else {
                    privateIp = privateIp == null ? ip : privateIp;
                }
            }
        }
        Map<String, String> metadata = new LinkedHashMap<>();
        putIfPresent(metadata, "flavor", server.path("flavor").path("id").asText(""));
        putIfPresent(metadata, "availabilityZone", server.path("availability_zone").asText(""));
        putIfPresent(metadata, "projectId", server.path("metadata").path("project_id").asText(""));

        String id = server.path("id").asText("");
        return new CloudResourceSnapshot(
                id,
                "HOST",
                server.path("name").asText(id),
                "",
                server.path("status").asText(""),
                publicIp,
                privateIp,
                firstTag(tags, "environment", "env"),
                firstTag(tags, "business", "app", "application"),
                firstTag(tags, "owner", "team"),
                tags,
                metadata);
    }

    private static void putIfPresent(Map<String, String> target, String key, String value) {
        if (value != null && !value.isBlank()) {
            target.put(key, value);
        }
    }

    private static String firstTag(Map<String, String> tags, String... keys) {
        for (String key : keys) {
            String value = tags.get(key);
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private Map<String, String> signedHeaders(String endpoint, String canonicalUri, String canonicalQuery,
                                              CloudCredentials credentials) {
        String host = URI.create(endpoint).getHost();
        String date = SDK_DATE.format(Instant.now());
        String payloadHash = sha256Hex("");

        String canonicalHeaders = "host:" + host + "\nx-sdk-date:" + date + "\n";
        String signedHeaders = "host;x-sdk-date";
        String canonicalRequest = "GET\n" + canonicalUri + "\n" + canonicalQuery + "\n"
                + canonicalHeaders + "\n" + signedHeaders + "\n" + payloadHash;
        String stringToSign = SIGNATURE_ALGORITHM + "\n" + date + "\n" + canonicalRequest;
        String signature = hex(hmacSha256(credentials.accessKeySecret(), stringToSign));

        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Host", host);
        headers.put("X-Sdk-Date", date);
        headers.put("Authorization", SIGNATURE_ALGORITHM
                + " Access=" + credentials.accessKeyId()
                + ", SignedHeaders=" + signedHeaders
                + ", Signature=" + signature);
        return headers;
    }

    private long backoffMillis(int attempt, String retryAfter) {
        if (retryAfter != null && !retryAfter.isBlank()) {
            try {
                long seconds = Long.parseLong(retryAfter.trim());
                return Math.min(maxBackoffMs, Math.max(baseBackoffMs, seconds * 1000L));
            } catch (NumberFormatException ignored) {
                // 非秒数格式（例如 HTTP 日期）时回落指数退避
            }
        }
        long exponential = Math.min(maxBackoffMs, baseBackoffMs * (1L << Math.min(6, attempt - 1)));
        long jitter = (long) (exponential * (Math.random() * 0.25));
        return Math.min(maxBackoffMs, exponential + jitter);
    }

    private void sleep(long millis) {
        sleeper.accept(Math.max(1, millis));
    }

    private static int parseOffset(String cursor) {
        if (cursor == null || cursor.isBlank()) {
            return 0;
        }
        try {
            return Math.max(0, Integer.parseInt(cursor));
        } catch (NumberFormatException e) {
            throw new CloudProviderException("CLOUD_CURSOR_INVALID", "分页游标无效");
        }
    }

    private static byte[] hmacSha256(String secret, String content) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return mac.doFinal(content.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException("云 API 签名失败", e);
        }
    }

    static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return hex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 不可用", e);
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder builder = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            builder.append(String.format(Locale.ROOT, "%02x", value));
        }
        return builder.toString();
    }
}
