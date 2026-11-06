package com.smartops.security;

import java.net.IDN;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.util.List;
import java.util.Locale;

/**
 * 服务端出站目标校验（SEC-06）。
 *
 * <p>只允许 http/https 且解析后的全部地址都是公网地址。校验覆盖：尾点域名、
 * IPv4-mapped IPv6、ULA、链路本地、CGNAT、保留网段与文档网段；解析失败按
 * fail-closed 拒绝。DNS 解析在每次调用时重新执行（每跳复检），以降低
 * DNS rebinding 的窗口，但不负责连接期 IP pin，残余风险需在部署层收敛。</p>
 */
public final class OutboundUrlPolicy {

    public enum Rule {
        OK, SCHEME_NOT_ALLOWED, HOST_MISSING, LOCAL_HOST, UNRESOLVABLE, NON_PUBLIC_ADDRESS
    }

    public record Decision(URI uri, List<InetAddress> addresses, Rule rule) {
        public boolean allowed() {
            return rule == Rule.OK;
        }
    }

    private OutboundUrlPolicy() {
    }

    public static Decision inspect(URI uri) {
        if (uri == null) return new Decision(null, List.of(), Rule.HOST_MISSING);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            return new Decision(uri, List.of(), Rule.SCHEME_NOT_ALLOWED);
        }
        String parsed = uri.getHost();
        if (parsed == null || parsed.isBlank()) {
            return new Decision(uri, List.of(), Rule.HOST_MISSING);
        }
        String host = normalizeHost(parsed);
        if (host.isEmpty() || host.equals("localhost") || host.endsWith(".localhost")) {
            return new Decision(uri, List.of(), Rule.LOCAL_HOST);
        }
        List<InetAddress> addresses;
        try {
            addresses = List.of(InetAddress.getAllByName(host));
        } catch (UnknownHostException unresolvable) {
            return new Decision(uri, List.of(), Rule.UNRESOLVABLE);
        }
        if (addresses.isEmpty() || addresses.stream().anyMatch(address -> !isPublicAddress(address))) {
            return new Decision(uri, addresses, Rule.NON_PUBLIC_ADDRESS);
        }
        return new Decision(uri, addresses, Rule.OK);
    }

    public static void assertPublic(URI uri) {
        Decision decision = inspect(uri);
        if (!decision.allowed()) throw new BlockedUrlException(decision.rule());
    }

    public static boolean isPublicHttpTarget(URI uri) {
        return inspect(uri).allowed();
    }

    static String normalizeHost(String value) {
        String host = value;
        if (host.startsWith("[") && host.endsWith("]")) host = host.substring(1, host.length() - 1);
        while (host.endsWith(".")) host = host.substring(0, host.length() - 1);
        host = host.toLowerCase(Locale.ROOT);
        if (!host.contains(":") && !host.isEmpty()) {
            try {
                host = IDN.toASCII(host, IDN.ALLOW_UNASSIGNED).toLowerCase(Locale.ROOT);
            } catch (IllegalArgumentException invalid) {
                return "";
            }
        }
        return host;
    }

    static boolean isPublicAddress(InetAddress address) {
        if (address.isAnyLocalAddress() || address.isLoopbackAddress()
                || address.isLinkLocalAddress() || address.isSiteLocalAddress()
                || address.isMulticastAddress()) {
            return false;
        }
        byte[] bytes = address.getAddress();
        if (address instanceof Inet6Address) {
            // IPv4-mapped ::ffff:a.b.c.d
            if (bytes[0] == 0 && bytes[1] == 0 && bytes[2] == 0 && bytes[3] == 0
                    && bytes[4] == 0 && bytes[5] == 0 && bytes[6] == 0 && bytes[7] == 0
                    && bytes[8] == 0 && bytes[9] == 0
                    && (bytes[10] & 0xff) == 0xff && (bytes[11] & 0xff) == 0xff) {
                return isPublicV4(bytes, 12);
            }
            // 64:ff9b::/96 NAT64
            if (bytes[0] == 0x00 && bytes[1] == 0x64 && bytes[2] == (byte) 0xff && bytes[3] == (byte) 0x9b
                    && allZero(bytes, 4, 12)) {
                return isPublicV4(bytes, 12);
            }
            // ULA fc00::/7
            if ((bytes[0] & 0xfe) == 0xfc) return false;
            // 文档网段 2001:db8::/32
            if (bytes[0] == 0x20 && bytes[1] == 0x01 && bytes[2] == 0x0d && bytes[3] == (byte) 0xb8) return false;
            return true;
        }
        if (address instanceof Inet4Address) {
            return isPublicV4(bytes, 0);
        }
        return false;
    }

    private static boolean isPublicV4(byte[] bytes, int offset) {
        int first = bytes[offset] & 0xff;
        int second = bytes[offset + 1] & 0xff;
        if (first == 0) return false;                       // 0.0.0.0/8
        if (first == 10) return false;                      // 10/8
        if (first == 100 && second >= 64 && second <= 127) return false; // 100.64/10 CGNAT
        if (first == 127) return false;                     // loopback
        if (first == 169 && second == 254) return false;    // link-local
        if (first == 172 && second >= 16 && second <= 31) return false;
        if (first == 192 && second == 168) return false;
        if (first == 192 && second == 0) return false;      // 192.0.0/24, 192.0.2/24
        if (first == 198 && (second == 18 || second == 19)) return false; // 198.18/15
        if (first == 198 && second == 51) return false;     // 198.51.100/24
        if (first == 203 && second == 0) return false;      // 203.0.113/24
        if (first >= 224) return false;                     // multicast / reserved
        return true;
    }

    private static boolean allZero(byte[] bytes, int from, int to) {
        for (int index = from; index < to; index++) {
            if (bytes[index] != 0) return false;
        }
        return true;
    }

    public static final class BlockedUrlException extends RuntimeException {
        private final Rule rule;

        public BlockedUrlException(Rule rule) {
            super(rule.name());
            this.rule = rule;
        }

        public Rule rule() {
            return rule;
        }
    }
}
