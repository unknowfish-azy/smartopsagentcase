package com.smartops.security;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 连接期 DNS pin（SEC-06 残余收口：DNS rebinding 防护）。
 *
 * <p>思路：出站校验（{@link OutboundUrlPolicy#inspect}）通过 DNS 解析拿到并校验了
 * 全部公网地址；连接期必须使用<b>同一批地址</b>，否则攻击者可在"校验"与"连接"
 * 之间切换 DNS 应答（rebinding），让真实连接落进内网。</p>
 *
 * <p>本类把校验过的地址登记为该主机的 pin，供 Apache HttpClient 5 的
 * {@code DnsResolver} 在建连时取用；<b>未登记的主机一律拒绝解析（fail-closed）</b>，
 * 保证挂在本 resolver 上的客户端不可能连接任何未经校验的地址。</p>
 *
 * <p>并发说明：pin 按主机覆盖（后写赢）。所有 pin 都来自 OutboundUrlPolicy 校验
 * 通过的公网地址集，因此并发下"用了别人的 pin"仍是已校验地址，不构成绕过。</p>
 */
public final class PinnedDns {

    private static final Map<String, List<InetAddress>> PINS = new ConcurrentHashMap<>();

    private PinnedDns() {
    }

    /** 登记一次连接要用的已校验地址（调用方必须先通过 OutboundUrlPolicy 校验）。 */
    public static void pin(String host, List<InetAddress> addresses) {
        if (host == null || host.isBlank() || addresses == null || addresses.isEmpty()) return;
        PINS.put(key(host), List.copyOf(addresses));
    }

    /** 连接完成后清除该主机的 pin；未清除的条目也不会被未校验客户端复用。 */
    public static void clear(String host) {
        if (host == null || host.isBlank()) return;
        PINS.remove(key(host));
    }

    /**
     * fail-closed 解析：只返回已 pin 的地址；未登记的主机抛 {@link UnknownHostException}。
     * 本方法只应被挂在受限出站客户端（知识爬取）的 DnsResolver 调用。
     */
    public static InetAddress[] resolve(String host) throws UnknownHostException {
        List<InetAddress> pinned = host == null ? null : PINS.get(key(host));
        if (pinned == null || pinned.isEmpty()) {
            throw new UnknownHostException("host is not pinned (fail-closed): " + host);
        }
        return pinned.toArray(InetAddress[]::new);
    }

    /** 是否已登记（测试与诊断用）。 */
    public static boolean isPinned(String host) {
        return host != null && PINS.containsKey(key(host));
    }

    private static String key(String host) {
        return OutboundUrlPolicy.normalizeHost(host.trim().toLowerCase(Locale.ROOT));
    }
}
