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
 * 华为云适配器的无账号验证：projectId 绑定、offset 分页、401 权限、签名脱敏、解析失败。
 * 真实云端往返需部署环境用只读 AK/SK 与项目 ID 另行验收。
 */
class HuaweiEcsInventoryProviderTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void requiresProjectIdInsteadOfBuildingAnInvalidUrl() {
        StubTransport transport = new StubTransport(json(0));
        HuaweiEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });
        CloudAccount account = new CloudAccount(3L, CloudProvider.HUAWEI, "hw-1", "华为云只读", "cn-north-4",
                null, null, null, 7L, "credential:3", "READ_ONLY", true, null, null, LocalDateTime.now());

        assertThatThrownBy(() -> provider.listInstances(account, credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class, error -> {
                    assertThat(error.code()).isEqualTo("CLOUD_PROJECT_ID_REQUIRED");
                    assertThat(error.permissionDenied()).isFalse();
                });
        assertThat(transport.requests).isEmpty();
    }

    @Test
    void paginatesByOffsetAndMapsAddressesAndTags() {
        StubTransport transport = new StubTransport(
                json(3, server("srv-1", "web-1"), server("srv-2", "web-2")),
                json(3, server("srv-3", "db-1")));
        HuaweiEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        CloudPage first = provider.listInstances(account(), credentials(), null, 2);
        assertThat(first.items()).hasSize(2);
        assertThat(first.hasMore()).isTrue();
        assertThat(first.nextCursor()).isEqualTo("2");
        assertThat(first.items().get(0).publicIp()).isEqualTo("1.2.3.4");
        assertThat(first.items().get(0).privateIp()).isEqualTo("192.168.0.10");
        assertThat(first.items().get(0).environment()).isEqualTo("prod");
        assertThat(first.items().get(0).business()).isEqualTo("checkout");

        CloudPage second = provider.listInstances(account(), credentials(), first.nextCursor(), 2);
        assertThat(second.items()).hasSize(1);
        assertThat(second.hasMore()).isFalse();

        assertThat(transport.uris.get(0))
                .isEqualTo("https://ecs.cn-north-4.myhuaweicloud.com/v1/project-1/cloudservers/detail"
                        + "?limit=2&offset=0");
        assertThat(transport.uris.get(1)).endsWith("?limit=2&offset=2");
    }

    @Test
    void permissionDeniedIsReportedOnceAndNeverEchoesTheSecret() {
        StubTransport transport = new StubTransport(new CloudHttpTransport.Response(401, Map.of(), "{}"));
        HuaweiEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        assertThatThrownBy(() -> provider.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class, error -> {
                    assertThat(error.code()).isEqualTo("CLOUD_PERMISSION_DENIED");
                    assertThat(error.permissionDenied()).isTrue();
                    assertThat(error.getMessage()).doesNotContain(credentials().accessKeySecret());
                });
        assertThat(transport.requests).hasSize(1);
    }

    @Test
    void signsGetWithSdkHmacButNeverExposesSecretKey() {
        StubTransport transport = new StubTransport(json(0));
        HuaweiEcsInventoryProvider provider = provider(transport, 3, 100, 2000, millis -> { });

        provider.listInstances(account(), credentials(), null, 2);

        Map<String, String> headers = transport.requests.get(0);
        assertThat(headers.get("Authorization"))
                .startsWith("SDK-HMAC-SHA256 Access=AKIDTEST, SignedHeaders=host;x-sdk-date")
                .doesNotContain(credentials().accessKeySecret());
        assertThat(headers.get("X-Sdk-Date")).isNotBlank();
        assertThat(headers.get("Host")).isEqualTo("ecs.cn-north-4.myhuaweicloud.com");
    }

    @Test
    void retriesRateLimitedResponse() {
        StubTransport transport = new StubTransport(
                new CloudHttpTransport.Response(429, Map.of("Retry-After", List.of("1")), "{}"),
                json(0));
        List<Long> sleeps = new ArrayList<>();
        HuaweiEcsInventoryProvider provider = provider(transport, 3, 500, 2000, sleeps::add);

        CloudPage page = provider.listInstances(account(), credentials(), null, 2);

        assertThat(page.items()).isEmpty();
        assertThat(transport.requests).hasSize(2);
        assertThat(sleeps).containsExactly(1000L);
    }

    @Test
    void invalidResponseIsReportedAsParseFailure() {
        HuaweiEcsInventoryProvider provider =
                provider(new StubTransport(new CloudHttpTransport.Response(200, Map.of(), "not-json")),
                        3, 100, 2000, millis -> { });

        assertThatThrownBy(() -> provider.listInstances(account(), credentials(), null, 2))
                .isInstanceOfSatisfying(CloudProviderException.class,
                        error -> assertThat(error.code()).isEqualTo("CLOUD_RESPONSE_INVALID"));
    }

    private HuaweiEcsInventoryProvider provider(StubTransport transport, int attempts, long base,
                                                long max, LongConsumer sleeper) {
        return new HuaweiEcsInventoryProvider(transport, mapper, attempts, base, max, sleeper);
    }

    private CloudAccount account() {
        return new CloudAccount(3L, CloudProvider.HUAWEI, "hw-1", "华为云只读", "cn-north-4",
                null, "project-1", null, 7L, "credential:3", "READ_ONLY", true, null, null, LocalDateTime.now());
    }

    private CloudCredentials credentials() {
        return new CloudCredentials("AKIDTEST", "SECRETKEY");
    }

    private String json(int count, String... servers) {
        return "{\"count\":" + count + ",\"servers\":[" + String.join(",", servers) + "]}";
    }

    private String server(String id, String name) {
        return "{\"id\":\"" + id + "\",\"name\":\"" + name + "\",\"status\":\"ACTIVE\""
                + ",\"availability_zone\":\"cn-north-4a\""
                + ",\"addresses\":[{\"addr\":\"192.168.0.10\",\"OS-EXT-IPS:type\":\"fixed\"}"
                + ",{\"addr\":\"1.2.3.4\",\"OS-EXT-IPS:type\":\"floating\"}]"
                + ",\"tags\":[{\"key\":\"environment\",\"value\":\"prod\"}"
                + ",{\"key\":\"business\",\"value\":\"checkout\"}]}";
    }

    private static final class StubTransport implements CloudHttpTransport {

        private final List<Response> responses;
        private final List<Map<String, String>> requests = new ArrayList<>();
        private final List<String> uris = new ArrayList<>();

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
            throw new UnsupportedOperationException("本测试不使用 POST");
        }

        @Override
        public Response get(String uri, Map<String, String> headers) {
            requests.add(new LinkedHashMap<>(headers));
            uris.add(uri);
            return responses.get(Math.min(requests.size() - 1, responses.size() - 1));
        }
    }
}
