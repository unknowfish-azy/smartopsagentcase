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
import java.util.TreeMap;
import java.util.UUID;
import java.util.function.LongConsumer;

/**
 * 阿里云 ECS 只读清单适配器（OPS-02 首家云）。
 *
 * 只调用 DescribeInstances，不调用任何写接口：
 *   - 分页：PageNumber / PageSize，按 TotalCount 判断是否还有下一页；
 *   - 限流：429 / 5xx 按 Retry-After 或指数退避 + 抖动重试，次数有上限；
 *   - 权限：401/403 归类 CLOUD_PERMISSION_DENIED，不重试、不伪装成"空账号"；
 *   - 签名：ACS3-HMAC-SHA256（AccessKeySecret 只在内存中参与 HMAC）。
 *
 * 说明：本仓库没有可用云账号，签名与错误映射由单元测试用替身传输验证；
 * "真实云端调用已通过"必须由部署环境用只读 AK 另行验收。
 */
@Component
public class AliyunEcsInventoryProvider implements CloudInventoryProvider {

    private static final String API_VERSION = "2014-05-26";
    private static final String SIGNATURE_ALGORITHM = "ACS3-HMAC-SHA256";
    private static final DateTimeFormatter ACS_DATE =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'").withZone(ZoneOffset.UTC);
    private static final Set<Integer> RETRYABLE_STATUS = Set.of(429, 500, 502, 503, 504);

    private final CloudHttpTransport transport;
    private final ObjectMapper mapper;
    private final int maxAttempts;
    private final long baseBackoffMs;
    private final long maxBackoffMs;
    private final LongConsumer sleeper;

    @Autowired
    public AliyunEcsInventoryProvider(
            CloudHttpTransport transport,
            ObjectMapper mapper,
            @Value("${smartops.cloud.sync.max-attempts:3}") int maxAttempts,
            @Value("${smartops.cloud.sync.backoff-base-ms:500}") long baseBackoffMs,
            @Value("${smartops.cloud.sync.backoff-max-ms:4000}") long maxBackoffMs) {
        this(transport, mapper, maxAttempts, baseBackoffMs, maxBackoffMs,
                ms -> { try { Thread.sleep(ms); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } });
    }

    AliyunEcsInventoryProvider(
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
        return CloudProvider.ALIYUN;
    }

    @Override
    public CloudPage listInstances(CloudAccount account, CloudCredentials credentials, String cursor, int pageSize) {
        int pageNumber = parsePage(cursor);
        String endpoint = account.endpointOrDefault();
        String body = form(
                "Action", "DescribeInstances",
                "Version", API_VERSION,
                "RegionId", account.region(),
                "PageNumber", String.valueOf(pageNumber),
                "PageSize", String.valueOf(Math.max(1, pageSize)));

        CloudHttpTransport.Response response = send(endpoint, credentials, body, "DescribeInstances");
        return parsePage(response.body(), pageNumber, pageSize);
    }

    private CloudHttpTransport.Response send(String endpoint, CloudCredentials credentials, String body, String action) {
        CloudProviderException lastError = null;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            CloudHttpTransport.Response response;
            try {
                response = transport.post(endpoint, signedHeaders(endpoint, credentials, body, action), body);
            } catch (IOException e) {
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
                // 权限不足是稳定结论：重试只会放大失败，且不能对外伪装成空结果。
                throw new CloudProviderException("CLOUD_PERMISSION_DENIED",
                        "云账号无权调用 " + action + "，请检查只读 RAM/策略授权", true, null);
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

    private CloudPage parsePage(String body, int pageNumber, int pageSize) {
        try {
            JsonNode root = mapper.readTree(body);
            JsonNode instances = root.path("Instances").path("Instance");
            List<CloudResourceSnapshot> items = new ArrayList<>();
            if (instances.isArray()) {
                for (JsonNode instance : instances) {
                    items.add(toSnapshot(instance));
                }
            }
            long total = root.path("TotalCount").asLong(-1);
            boolean hasMore = total >= 0 ? (long) pageNumber * pageSize < total : items.size() >= pageSize;
            return new CloudPage(items, hasMore ? String.valueOf(pageNumber + 1) : null, hasMore);
        } catch (IOException | RuntimeException e) {
            throw new CloudProviderException("CLOUD_RESPONSE_INVALID", "云 API 响应无法解析", false, e);
        }
    }

    private CloudResourceSnapshot toSnapshot(JsonNode instance) {
        Map<String, String> tags = new LinkedHashMap<>();
        JsonNode tagArray = instance.path("Tags").path("Tag");
        if (tagArray.isArray()) {
            for (JsonNode tag : tagArray) {
                String key = tag.path("TagKey").asText("");
                if (!key.isBlank()) {
                    tags.put(key, tag.path("TagValue").asText(""));
                }
            }
        }
        Map<String, String> metadata = new LinkedHashMap<>();
        putIfPresent(metadata, "instanceType", instance.path("InstanceType").asText(""));
        putIfPresent(metadata, "zoneId", instance.path("ZoneId").asText(""));
        putIfPresent(metadata, "vpcId", instance.path("VpcId").asText(""));
        putIfPresent(metadata, "status", instance.path("Status").asText(""));

        return new CloudResourceSnapshot(
                instance.path("InstanceId").asText(""),
                "HOST",
                instance.path("InstanceName").asText(instance.path("InstanceId").asText("")),
                instance.path("RegionId").asText(""),
                instance.path("Status").asText(""),
                firstIp(instance.path("PublicIpAddress").path("IpAddress")),
                firstIp(instance.path("InnerIpAddress").path("IpAddress")),
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

    private static String firstIp(JsonNode array) {
        return array.isArray() && !array.isEmpty() ? array.get(0).asText("") : null;
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

    private Map<String, String> signedHeaders(String endpoint, CloudCredentials credentials, String body, String action) {
        String host = URI.create(endpoint).getHost();
        String payloadHash = sha256Hex(body);
        String date = ACS_DATE.format(Instant.now());
        String nonce = UUID.randomUUID().toString();

        Map<String, String> canonical = new TreeMap<>();
        canonical.put("host", host);
        canonical.put("x-acs-action", action);
        canonical.put("x-acs-content-sha256", payloadHash);
        canonical.put("x-acs-date", date);
        canonical.put("x-acs-signature-nonce", nonce);
        canonical.put("x-acs-version", API_VERSION);

        StringBuilder canonicalHeaders = new StringBuilder();
        canonical.forEach((name, value) -> canonicalHeaders
                .append(name).append(':').append(value.trim()).append('\n'));
        String signedHeaders = String.join(";", canonical.keySet());

        String path = URI.create(endpoint).getPath();
        String canonicalUri = path == null || path.isBlank() ? "/" : path;
        String canonicalRequest = "POST\n" + canonicalUri + "\n\n" + canonicalHeaders + "\n"
                + signedHeaders + "\n" + payloadHash;
        String stringToSign = SIGNATURE_ALGORITHM + "\n" + sha256Hex(canonicalRequest);
        String signature = hex(hmacSha256(credentials.accessKeySecret(), stringToSign));

        Map<String, String> headers = new LinkedHashMap<>(canonical);
        headers.put("Authorization", SIGNATURE_ALGORITHM
                + " Credential=" + credentials.accessKeyId()
                + ",SignedHeaders=" + signedHeaders
                + ",Signature=" + signature);
        headers.put("Content-Type", "application/x-www-form-urlencoded");
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

    private static String form(String... pairs) {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < pairs.length; i += 2) {
            if (builder.length() > 0) {
                builder.append('&');
            }
            builder.append(urlEncode(pairs[i])).append('=').append(urlEncode(pairs[i + 1]));
        }
        return builder.toString();
    }

    private static String urlEncode(String value) {
        return java.net.URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8)
                .replace("+", "%20");
    }

    private static int parsePage(String cursor) {
        if (cursor == null || cursor.isBlank()) {
            return 1;
        }
        try {
            return Math.max(1, Integer.parseInt(cursor));
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
