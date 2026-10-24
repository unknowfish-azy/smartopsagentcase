package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.net.InetAddress;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Webhook SSRF 防护测试。
 *
 * <p>Webhook URL 由用户填写、服务端主动请求。不校验就等于把服务器变成内网探测器。
 * 这组用例覆盖最常被利用的目标：环回、云元数据、私有网段、IPv6 ULA。</p>
 */
class SentinelWebhookPolicyTest {

    @Test
    @DisplayName("只允许 http/https，其它协议一律拒绝")
    void rejectsNonHttpSchemes() {
        for (String url : new String[] { "file:///etc/passwd", "gopher://x", "ftp://example.test/x", "javascript:alert(1)" }) {
            assertNotNull(SentinelWebhookPolicy.rejectionReason(url, Set.of()), "must reject: " + url);
        }
    }

    @Test
    @DisplayName("拒绝环回与云元数据地址")
    void rejectsLoopbackAndMetadata() {
        for (String url : new String[] {
                "http://127.0.0.1:8080/actuator/health",
                "http://localhost:8080/x",
                "http://169.254.169.254/latest/meta-data/",
                "http://[::1]/x" }) {
            String reason = SentinelWebhookPolicy.rejectionReason(url, Set.of());
            assertNotNull(reason, "must reject: " + url);
            assertTrue(reason.contains("内网") || reason.contains("保留") || reason.contains("解析"),
                    "reason should explain why: " + reason);
        }
    }

    @Test
    @DisplayName("拒绝私有网段")
    void rejectsPrivateRanges() {
        for (String host : new String[] { "10.0.0.1", "192.168.1.1", "172.16.0.1", "100.64.0.1", "198.18.0.1", "240.0.0.1" }) {
            assertNotNull(SentinelWebhookPolicy.rejectionReason("http://" + host + "/hook", Set.of()),
                    "must reject private/reserved: " + host);
        }
    }

    @Test
    @DisplayName("显式白名单可以放行内网 WebHook（企业微信/钉钉常见）")
    void allowListBypassesPrivateCheck() {
        // 企业内网网关是真实需求，但不能默认放开：必须由部署方显式配置
        assertNull(SentinelWebhookPolicy.rejectionReason("http://10.0.0.9/hook", Set.of("10.0.0.9")));
        assertNotNull(SentinelWebhookPolicy.rejectionReason("http://10.0.0.9/hook", Set.of()),
                "未配置白名单时必须拒绝");
    }

    @Test
    @DisplayName("空地址与格式错误给出可读原因，而不是抛异常")
    void handlesMalformedInput() {
        assertNotNull(SentinelWebhookPolicy.rejectionReason(null, Set.of()));
        assertNotNull(SentinelWebhookPolicy.rejectionReason("   ", Set.of()));
        assertNotNull(SentinelWebhookPolicy.rejectionReason("not a url", Set.of()));
        assertNotNull(SentinelWebhookPolicy.rejectionReason("http://", Set.of()));
    }

    @Test
    @DisplayName("公网地址被放行（否则功能不可用）")
    void allowsPublicAddresses() throws Exception {
        InetAddress publicAddress = InetAddress.getByName("93.184.216.34"); // example.com 的地址
        assertTrue(SentinelWebhookPolicy.isPublic(publicAddress));
    }

    @Test
    @DisplayName("IPv6 ULA 与链路本地被视为非公网")
    void rejectsIpv6Private() throws Exception {
        assertFalse(SentinelWebhookPolicy.isPublic(InetAddress.getByName("fd00::1")), "ULA must be private");
        assertFalse(SentinelWebhookPolicy.isPublic(InetAddress.getByName("fe80::1")), "link-local must be private");
    }

    @Test
    @DisplayName("白名单解析忽略空白项并统一小写")
    void parsesAllowList() {
        assertEquals(Set.of("a.test", "b.test"), SentinelWebhookPolicy.parseAllowedHosts(" A.TEST , , b.test "));
        assertTrue(SentinelWebhookPolicy.parseAllowedHosts(null).isEmpty());
        assertTrue(SentinelWebhookPolicy.parseAllowedHosts("  ").isEmpty());
    }
}
