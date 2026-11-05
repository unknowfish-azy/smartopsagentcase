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
 * 无真实云账号环境下的适配器验证：
 * 用替身传输覆盖分页、429 退避、权限不足、签名脱敏与响应解析。
 * 真实云端往返验证不在本测试范围，需部署环境用只读 AK 另行验收。
 */
class AliyunEcsInventoryProviderTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void paginatesUntilTotalCountIsReached() {
        StubTransport transport = new StubTransport(
                json(3, instance("i-1", "web-1", "Running", "1.1.1.1", "10.0.0.1", "prod", "checkout"),
                        instance("i-2", "web-2", "Running", "1.1.1.2", "10.0.0.2", "prod", "checkout")),
                json(3, instance("i-3", "db-1", "Stopped", null, "10.0.0.3", "prod", "checkout")));
        AliyunEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        CloudPage first = provider.listInstances(account(), credentials(), null, 2);
        assertThat(first.items()).hasSize(2);
        assertThat(first.hasMore()).isTrue();
        assertThat(first.nextCursor()).isEqualTo("2");
        assertThat(first.items().get(0).business()).isEqualTo("checkout");
        assertThat(first.items().get(0).environment()).isEqualTo("prod");

        CloudPage second = provider.listInstances(account(), credentials(), first.nextCursor(), 2);
        assertThat(second.items()).hasSize(1);
        assertThat(second.hasMore()).isFalse();
        assertThat(second.nextCursor()).isNull();

        assertThat(transport.bodies.get(0)).contains("PageNumber=1").contains("PageSize=2");
        assertThat(transport.bodies.get(1)).contains("PageNumber=2");
    }

    @Test
    void retriesRateLimitedResponseWithRetryAfter() {
        StubTransport transport = new StubTransport(
                new CloudHttpTransport.Response(429,
                        Map.of("Retry-After", List.of("1")), "{\"Code\":\"Throttling\"}"),
                json(0));
        List<Long> sleeps = new ArrayList<>();
        AliyunEcsInventoryProvider provider = provider(transport, 3, 500, 2000, sleeps::add);

        CloudPage page = provider.listInstances(account(), credentials(), null, 2);

        assertThat(page.items()).isEmpty();
        assertThat(transport.requests).hasSize(2);
        assertThat(sleeps).containsExactly(1000L);
    }

    @Test
    void permissionDeniedIsReportedOnceAndNeverEchoesTheSecret() {
        StubTransport transport = new StubTransport(
                new CloudHttpTransport.Response(403, Map.of(), "{\"Code\":\"Forbidden.RAM\"}"));
        AliyunEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        assertThatThrownBy(() -> provider.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class, error -> {
                    assertThat(error.code()).isEqualTo("CLOUD_PERMISSION_DENIED");
                    assertThat(error.permissionDenied()).isTrue();
                    assertThat(error.getMessage()).doesNotContain(credentials().accessKeySecret());
                });
        assertThat(transport.requests).hasSize(1);
        assertThat(credentials().toString()).doesNotContain(credentials().accessKeySecret());
    }

    @Test
    void signsWithAccessKeyIdButNeverExposesSecret() {
        StubTransport transport = new StubTransport(json(0));
        AliyunEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        provider.listInstances(account(), credentials(), null, 2);

        Map<String, String> headers = transport.requests.get(0);
        assertThat(headers.get("Authorization"))
                .startsWith("ACS3-HMAC-SHA256 Credential=AKIDTEST")
                .contains("SignedHeaders=host;x-acs-action;x-acs-content-sha256;x-acs-date;x-acs-signature-nonce;x-acs-version")
                .doesNotContain(credentials().accessKeySecret());
        assertThat(headers.get("x-acs-action")).isEqualTo("DescribeInstances");
        assertThat(headers.get("x-acs-content-sha256")).hasSize(64);
        assertThat(headers.get("x-acs-signature-nonce")).isNotBlank();
    }

    @Test
    void invalidResponseIsReportedAsParseFailure() {
        StubTransport transport = new StubTransport(
                new CloudHttpTransport.Response(200, Map.of(), "not-json"));
        AliyunEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        assertThatThrownBy(() -> provider.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class,
                        error -> assertThat(error.code()).isEqualTo("CLOUD_RESPONSE_INVALID"));
    }

    private AliyunEcsInventoryProvider provider(StubTransport transport, int attempts, long base,
                                                long max, LongConsumer sleeper) {
        return new AliyunEcsInventoryProvider(transport, mapper, attempts, base, max, sleeper);
    }

    private CloudAccount account() {
        return new CloudAccount(1L, CloudProvider.ALIYUN, "1234567890", "生产只读", "cn-hangzhou",
                "https://ecs.cn-hangzhou.aliyuncs.com", null, null, 7L, "credential:1", "READ_ONLY",
                true, null, null, LocalDateTime.now());
    }

    private CloudCredentials credentials() {
        return new CloudCredentials("AKIDTEST", "SECRET");
    }

    private String json(int totalCount, String... instances) {
        return "{\"TotalCount\":" + totalCount + ",\"Instances\":{\"Instance\":["
                + String.join(",", instances) + "]}}";
    }

    private String instance(String id, String name, String status, String publicIp, String privateIp,
                            String environment, String business) {
        String publicBlock = publicIp == null ? "{}"
                : "{\"IpAddress\":[\"" + publicIp + "\"]}";
        return "{\"InstanceId\":\"" + id + "\",\"InstanceName\":\"" + name + "\",\"Status\":\"" + status
                + "\",\"RegionId\":\"cn-hangzhou\",\"PublicIpAddress\":" + publicBlock
                + ",\"InnerIpAddress\":{\"IpAddress\":[\"" + privateIp + "\"]}"
                + ",\"InstanceType\":\"ecs.g7.large\",\"ZoneId\":\"cn-hangzhou-h\""
                + ",\"Tags\":{\"Tag\":[{\"TagKey\":\"environment\",\"TagValue\":\"" + environment + "\"}"
                + ",{\"TagKey\":\"business\",\"TagValue\":\"" + business + "\"}]}}";
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
