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
 * 腾讯云 CVM 只读清单适配器（OPS-02）。
 *
 * 只调用 DescribeInstances，不调用任何写接口：
 *   - 分页：Offset / Limit，按 TotalCount 判断是否还有下一页；
 *   - 限流：HTTP 429 / 5xx 按 Retry-After 或指数退避 + 抖动重试，次数有上限；
 *   - 权限：401/403 与响应体 AuthFailure/UnauthorizedOperation 归类 CLOUD_PERMISSION_DENIED，
 *     不重试、不伪装成"空账号"；
 *   - 签名：TC3-HMAC-SHA256（AccessKeySecret 只在内存中参与 HMAC，不出现在请求头与异常文本）。
 *
 * 说明：签名与错误映射由单元测试用替身传输验证；"真实云端调用已通过"
 * 必须由部署环境用只读 SecretId/SecretKey 另行验收。
 */
@Component
public class TencentCvmInventoryProvider implements CloudInventoryProvider {

    private static final String API_VERSION = "2017-03-12";
    private static final String SERVICE = "cvm";
    private static final String SIGNATURE_ALGORITHM = "TC3-HMAC-SHA256";
    private static final String CONTENT_TYPE = "application/json; charset=utf-8";
    private static final DateTimeFormatter DATE =
            DateTimeFormatter.ofPattern("yyyy-MM-dd").withZone(ZoneOffset.UTC);
    private static final Set<Integer> RETRYABLE_STATUS = Set.of(429, 500, 502, 503, 504);

    private final CloudHttpTransport transport;
    private final ObjectMapper mapper;
    private final int maxAttempts;
    private final long baseBackoffMs;
    private final long maxBackoffMs;
    private final LongConsumer sleeper;

    @Autowired
    public TencentCvmInventoryProvider(
            CloudHttpTransport transport,
            ObjectMapper mapper,
            @Value("${smartops.cloud.sync.max-attempts:3}") int maxAttempts,
            @Value("${smartops.cloud.sync.backoff-base-ms:500}") long baseBackoffMs,
            @Value("${smartops.cloud.sync.backoff-max-ms:4000}") long maxBackoffMs) {
        this(transport, mapper, maxAttempts, baseBackoffMs, maxBackoffMs,
                ms -> { try { Thread.sleep(ms); } catch (InterruptedException e) { Thread.currentThread().interrupt(); } });
    }

    TencentCvmInventoryProvider(
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
        return CloudProvider.TENCENT;
    }

    @Override
    public CloudPage listInstances(CloudAccount account, CloudCredentials credentials, String cursor, int pageSize) {
        int offset = parseOffset(cursor);
        int limit = Math.max(1, pageSize);
        String endpoint = account.endpointOrDefault();

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("Region", account.region());
        payload.put("Offset", offset);
        payload.put("Limit", limit);
        String body;
        try {
            body = mapper.writeValueAsString(payload);
        } catch (IOException e) {
            throw new CloudProviderException("CLOUD_REQUEST_BUILD_FAILED", "云 API 请求构造失败");
        }

        CloudHttpTransport.Response response = send(endpoint, account.region(), credentials, body, "DescribeInstances");
        return parsePage(response.body(), offset, limit);
    }

    private CloudHttpTransport.Response send(String endpoint, String region, CloudCredentials credentials,
                                             String body, String action) {
        CloudProviderException lastError = null;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            CloudHttpTransport.Response response;
            try {
                response = transport.post(endpoint, signedHeaders(endpoint, region, credentials, body, action), body);
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
                throw new CloudProviderException("CLOUD_PERMISSION_DENIED",
                        "云账号无权调用 " + action + "，请检查只读子账号策略", true, null);
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
            JsonNode response = root.path("Response");
            JsonNode error = response.path("Error");
            if (error.isObject()) {
                throw errorFor(error.path("Code").asText(""), error.path("Message").asText(""));
            }

            List<CloudResourceSnapshot> items = new ArrayList<>();
            JsonNode instances = response.path("InstanceSet");
            if (instances.isArray()) {
                for (JsonNode instance : instances) {
                    items.add(toSnapshot(instance));
                }
            }
            long total = response.path("TotalCount").asLong(-1);
            boolean hasMore = total >= 0
                    ? (long) offset + limit < total
                    : items.size() >= limit;
            return new CloudPage(items, hasMore ? String.valueOf(offset + limit) : null, hasMore);
        } catch (CloudProviderException e) {
            throw e;
        } catch (IOException | RuntimeException e) {
            throw new CloudProviderException("CLOUD_RESPONSE_INVALID", "云 API 响应无法解析", false, e);
        }
    }

    private CloudResourceSnapshot toSnapshot(JsonNode instance) {
        Map<String, String> tags = new LinkedHashMap<>();
        JsonNode tagArray = instance.path("Tags");
        if (tagArray.isArray()) {
            for (JsonNode tag : tagArray) {
                String key = tag.path("Key").asText("");
                if (!key.isBlank()) {
                    tags.put(key, tag.path("Value").asText(""));
                }
            }
        }
        String zone = instance.path("Placement").path("ZoneName").asText("");
        Map<String, String> metadata = new LinkedHashMap<>();
        putIfPresent(metadata, "instanceType", instance.path("InstanceType").asText(""));
        putIfPresent(metadata, "zoneName", zone);
        putIfPresent(metadata, "state", instance.path("InstanceState").asText(""));

        String id = instance.path("InstanceId").asText("");
        return new CloudResourceSnapshot(
                id,
                "HOST",
                instance.path("InstanceName").asText(id),
                // 地域用账号绑定值（uid 稳定），可用区只进 metadata，避免同一资源因可用区变化换身份
                "",
                instance.path("InstanceState").asText(""),
                firstIp(instance.path("PublicIpAddresses")),
                firstIp(instance.path("PrivateIpAddresses")),
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

    private CloudProviderException errorFor(String code, String message) {
        String normalized = code == null ? "" : code.toLowerCase(Locale.ROOT);
        String text = message == null || message.isBlank() ? "云 API 返回错误" : message;
        if (normalized.startsWith("authfailure") || normalized.contains("unauthorizedoperation")
                || normalized.contains("forbidden")) {
            return new CloudProviderException("CLOUD_PERMISSION_DENIED", "云账号无权限调用 DescribeInstances：" + text, true, null);
        }
        if (normalized.contains("requestlimitexceeded") || normalized.contains("throttling")) {
            return new CloudProviderException("CLOUD_RATE_LIMITED", "云 API 限流：" + text);
        }
        return new CloudProviderException("CLOUD_PROVIDER_ERROR", "云 API 返回错误：" + text);
    }

    private Map<String, String> signedHeaders(String endpoint, String region, CloudCredentials credentials,
                                              String body, String action) {
        String host = URI.create(endpoint).getHost();
        long timestamp = Instant.now().getEpochSecond();
        String date = DATE.format(Instant.ofEpochSecond(timestamp));
        String payloadHash = sha256Hex(body);

        // 1) 规范请求：固定 content-type 与 host 两个头，签名覆盖方法/URI/头/载荷
        String canonicalHeaders = "content-type:" + CONTENT_TYPE + "\nhost:" + host + "\n";
        String signedHeaders = "content-type;host";
        String canonicalRequest = "POST\n/\n\n" + canonicalHeaders + "\n" + signedHeaders + "\n" + payloadHash;

        // 2) 待签字符串与派生签名密钥
        String credentialScope = date + "/" + SERVICE + "/tc3_request";
        String stringToSign = SIGNATURE_ALGORITHM + "\n" + timestamp + "\n" + credentialScope + "\n"
                + sha256Hex(canonicalRequest);
        byte[] signingKey = hmacSha256(hmacSha256(hmacSha256(
                credentials.accessKeySecret(), date), SERVICE), "tc3_request");
        String signature = hex(hmacSha256(signingKey, stringToSign));

        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Authorization", SIGNATURE_ALGORITHM
                + " Credential=" + credentials.accessKeyId() + "/" + credentialScope
                + ",SignedHeaders=" + signedHeaders
                + ",Signature=" + signature);
        headers.put("Content-Type", CONTENT_TYPE);
        headers.put("Host", host);
        headers.put("X-TC-Action", action);
        headers.put("X-TC-Version", API_VERSION);
        headers.put("X-TC-Timestamp", String.valueOf(timestamp));
        if (region != null && !region.isBlank()) {
            headers.put("X-TC-Region", region);
        }
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

    static byte[] hmacSha256(byte[] key, String content) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(content.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException("云 API 签名失败", e);
        }
    }

    private static byte[] hmacSha256(String secret, String content) {
        return hmacSha256(secret.getBytes(StandardCharsets.UTF_8), content);
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
