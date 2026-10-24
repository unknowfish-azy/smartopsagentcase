package com.smartops.sentinel;

import java.net.InetAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.util.Locale;
import java.util.Set;

/**
 * Webhook 地址校验（SSRF 防护）。
 *
 * <p><b>为什么必须做</b>：Webhook URL 由用户填写，服务端会主动向它发起请求。
 * 如果不校验，用户可以让服务器去访问 {@code http://127.0.0.1:8080/actuator}
 * 或云厂商元数据地址 {@code http://169.254.169.254/}，把"通知"变成探测内网的工具。</p>
 *
 * <p><b>策略</b>：只允许 http/https；解析出的**所有**地址都不能是环回、私有、
 * 链路本地、组播或保留地址。允许内网 WebHook（企业微信/钉钉常见内网网关）会很方便，
 * 但那等于把 SSRF 防护关掉了 —— 因此这里选择默认拒绝，需要内网投递请显式开白名单。</p>
 *
 * <p><b>已知局限</b>：这里做的是"解析时校验"，无法阻止 DNS 重绑定（解析后改指向内网）。
 * 彻底解法是固定解析结果直连。这是有意识接受的残余风险，不假装已完全解决。</p>
 */
public final class SentinelWebhookPolicy {

    private SentinelWebhookPolicy() {}

    /** 拒绝原因（可读中文，直接用于 400 响应）。 */
    public static String rejectionReason(String url, Set<String> allowedHosts) {
        if (url == null || url.isBlank()) return "Webhook 地址不能为空";
        URI uri;
        try {
            uri = URI.create(url.trim());
        } catch (IllegalArgumentException malformed) {
            return "Webhook 地址格式不正确";
        }
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!"http".equals(scheme) && !"https".equals(scheme)) return "Webhook 只支持 http 或 https";
        String host = uri.getHost();
        if (host == null || host.isBlank()) return "Webhook 地址缺少主机名";

        Set<String> allowed = allowedHosts == null ? Set.of() : allowedHosts;
        if (allowed.contains(host.toLowerCase(Locale.ROOT))) return null; // 显式白名单放行

        InetAddress[] addresses;
        try {
            addresses = InetAddress.getAllByName(host);
        } catch (UnknownHostException unresolved) {
            return "Webhook 主机无法解析";
        }
        for (InetAddress address : addresses) {
            if (!isPublic(address)) {
                return "Webhook 主机指向内网或保留地址（" + address.getHostAddress() + "），已拒绝，避免被用来探测内网";
            }
        }
        return null;
    }

    static boolean isPublic(InetAddress address) {
        if (address.isLoopbackAddress() || address.isAnyLocalAddress() || address.isLinkLocalAddress()
                || address.isSiteLocalAddress() || address.isMulticastAddress()) {
            return false;
        }
        byte[] raw = address.getAddress();
        if (raw.length == 4) {
            int first = raw[0] & 0xff;
            int second = raw[1] & 0xff;
            // 100.64.0.0/10 运营商级 NAT、192.0.0.0/24 IETF 保留
            if (first == 100 && second >= 64 && second <= 127) return false;
            if (first == 192 && second == 0) return false;
            // 198.18.0.0/15 基准测试、198.51.100.0/24 文档地址
            if (first == 198 && (second == 18 || second == 19) ) return false;
            if (first == 198 && second == 51) return false;
            // 203.0.113.0/24 文档地址
            if (first == 203 && second == 0) return false;
            // 240.0.0.0/4 保留
            if (first >= 240) return false;
            return true;
        }
        // IPv6：拒绝未指定、环回、ULA(fc00::/7)、链路本地(fe80::/10)
        int firstByte = raw[0] & 0xff;
        int secondByte = raw[1] & 0xff;
        if ((firstByte & 0xfe) == 0xfc) return false;
        if (firstByte == 0xfe && (secondByte & 0xc0) == 0x80) return false;
        return true;
    }

    /** 允许配置的内网 WebHook 主机白名单（逗号分隔）。 */
    public static Set<String> parseAllowedHosts(String value) {
        if (value == null || value.isBlank()) return Set.of();
        return java.util.Arrays.stream(value.split(","))
                .map(String::trim)
                .map(item -> item.toLowerCase(Locale.ROOT))
                .filter(item -> !item.isEmpty())
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }
}
