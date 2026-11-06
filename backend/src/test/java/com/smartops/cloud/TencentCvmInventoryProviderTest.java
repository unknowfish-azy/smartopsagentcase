package com.smartops.cloud;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.LongConsumer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * 腾讯云适配器的无账号验证：分页、429 退避、权限不足、响应体错误分类、签名脱敏。
 * 真实云端往返需部署环境用只读凭据另行验收。
 */
class TencentCvmInventoryProviderTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void paginatesByOffsetUntilTotalCountIsReached() {
        StubTransport transport = new StubTransport(
                json(3, instance("ins-1", "web-1", "1.1.1.1", "10.0.0.1"),
                        instance("ins-2", "web-2", "1.1.1.2", "10.0.0.2")),
                json(3, instance("ins-3", "db-1", null, "10.0.0.3")));
        TencentCvmInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        CloudPage first = provider.listInstances(account(), credentials(), null, 2);
        assertThat(first.items()).hasSize(2);
        assertThat(first.hasMore()).isTrue();
        assertThat(first.nextCursor()).isEqualTo("2");
        assertThat(first.items().get(0).environment()).isEqualTo("prod");
        assertThat(first.items().get(0).business()).isEqualTo("checkout");
        assertThat(first.items().get(0).publicIp()).isEqualTo("1.1.1.1");

        CloudPage second = provider.listInstances(account(), credentials(), first.nextCursor(), 2);
        assertThat(second.items()).hasSize(1);
        assertThat(second.hasMore()).isFalse();
        assertThat(second.nextCursor()).isNull();

        assertThat(transport.bodies.get(0)).contains("\"Offset\":0").contains("\"Limit\":2");
        assertThat(transport.bodies.get(1)).contains("\"Offset\":2");
    }

    @Test
    void retriesRateLimitedResponseWithRetryAfter() {
        StubTransport transport = new StubTransport(
                new CloudHttpTransport.Response(429, Map.of("Retry-After", List.of("1")), "{}"),
                json(0));
        List<Long> sleeps = new ArrayList<>();
        TencentCvmInventoryProvider provider = provider(transport, 3, 500, 2000, sleeps::add);

        CloudPage page = provider.listInstances(account(), credentials(), null, 2);

        assertThat(page.items()).isEmpty();
        assertThat(transport.requests).hasSize(2);
        assertThat(sleeps).containsExactly(1000L);
    }

    @Test
    void permissionDeniedIsReportedOnceAndNeverEchoesTheSecret() {
        StubTransport transport = new StubTransport(new CloudHttpTransport.Response(403, Map.of(), "{}"));
        TencentCvmInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        assertThatThrownBy(() -> provider.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class, error -> {
                    assertThat(error.code()).isEqualTo("CLOUD_PERMISSION_DENIED");
                    assertThat(error.permissionDenied()).isTrue();
                    assertThat(error.getMessage()).doesNotContain(credentials().accessKeySecret());
                });
        assertThat(transport.requests).hasSize(1);
    }

    @Test
    void bodyLevelAuthFailureAndThrottlingAreClassified() {
        TencentCvmInventoryProvider authFailure = provider(
                new StubTransport("{\"Response\":{\"Error\":{\"Code\":\"AuthFailure.UnauthorizedOperation\","
                        + "\"Message\":\"no permission\"}}}"), 3, 100, 2000, millis -> { });
        assertThatThrownBy(() -> authFailure.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class, error -> {
                    assertThat(error.code()).isEqualTo("CLOUD_PERMISSION_DENIED");
                    assertThat(error.permissionDenied()).isTrue();
                });

        TencentCvmInventoryProvider throttling = provider(
                new StubTransport("{\"Response\":{\"Error\":{\"Code\":\"RequestLimitExceeded\","
                        + "\"Message\":\"too many requests\"}}}"), 3, 100, 2000, millis -> { });
        assertThatThrownBy(() -> throttling.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class,
                        error -> assertThat(error.code()).isEqualTo("CLOUD_RATE_LIMITED"));
    }

    @Test
    void signsWithSecretIdButNeverExposesSecretKey() {
        StubTransport transport = new StubTransport(json(0));
        TencentCvmInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        provider.listInstances(account(), credentials(), null, 2);

        Map<String, String> headers = transport.requests.get(0);
        assertThat(headers.get("Authorization"))
                .startsWith("TC3-HMAC-SHA256 Credential=AKIDTEST/")
                .contains("/cvm/tc3_request")
                .contains("SignedHeaders=content-type;host")
                .doesNotContain(credentials().accessKeySecret());
        assertThat(headers.get("X-TC-Action")).isEqualTo("DescribeInstances");
        assertThat(headers.get("X-TC-Region")).isEqualTo("ap-guangzhou");
        assertThat(headers.get("X-TC-Version")).isEqualTo("2017-03-12");
        assertThat(headers.get("X-TC-Timestamp")).isNotBlank();
        assertThat(headers.get("Host")).isEqualTo("cvm.tencentcloudapi.com");
    }

    @Test
    void invalidResponseIsReportedAsParseFailure() {
        TencentCvmInventoryProvider provider =
                provider(new StubTransport(new CloudHttpTransport.Response(200, Map.of(), "not-json")),
                        3, 100, 2000, millis -> { });

        assertThatThrownBy(() -> provider.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class,
                        error -> assertThat(error.code()).isEqualTo("CLOUD_RESPONSE_INVALID"));
    }

    private TencentCvmInventoryProvider provider(StubTransport transport, int attempts, long base,
                                                 long max, LongConsumer sleeper) {
        return new TencentCvmInventoryProvider(transport, mapper, attempts, base, max, sleeper);
    }

    private CloudAccount account() {
        return new CloudAccount(2L, CloudProvider.TENCENT, "1250000000", "腾讯云只读", "ap-guangzhou",
                null, null, null, 7L, "credential:2", "READ_ONLY", true, null, null, LocalDateTime.now());
    }

    private CloudCredentials credentials() {
        return new CloudCredentials("AKIDTEST", "SECRETKEY");
    }

    private String json(int totalCount, String... instances) {
        return "{\"Response\":{\"TotalCount\":" + totalCount + ",\"InstanceSet\":["
                + String.join(",", instances) + "],\"RequestId\":\"req-1\"}}";
    }

    private String instance(String id, String name, String publicIp, String privateIp) {
        String publicBlock = publicIp == null ? "[]" : "[\"" + publicIp + "\"]";
        return "{\"InstanceId\":\"" + id + "\",\"InstanceName\":\"" + name
                + "\",\"InstanceState\":\"RUNNING\",\"InstanceType\":\"S5.MEDIUM4\""
                + ",\"Placement\":{\"ZoneName\":\"ap-guangzhou-3\"}"
                + ",\"PublicIpAddresses\":" + publicBlock
                + ",\"PrivateIpAddresses\":[\"" + privateIp + "\"]"
                + ",\"Tags\":[{\"Key\":\"environment\",\"Value\":\"prod\"}"
                + ",{\"Key\":\"business\",\"Value\":\"checkout\"}]}";
    }

    private static final class StubTransport implements CloudHttpTransport {

        private final List<Response> responses;
        private final List<Map<String, String>> requests = new ArrayList<>();
        private final List<String> bodies = new ArrayList<>();

        StubTransport(Object... responses) {
            List<Response> values = new ArrayList<>();
            for (Object response : responses) {
                if (response instanceof Response) {
                    values.add((Response) response);
                } else {
                    values.add(new Response(200, Map.of(), String.valueOf(response)));
                }
            }
            this.responses = List.copyOf(values);
        }

        @Override
        public Response post(String uri, Map<String, String> headers, String body) {
            requests.add(new LinkedHashMap<>(headers));
            bodies.add(body);
            return responses.get(Math.min(requests.size() - 1, responses.size() - 1));
        }
    }
}
