package com.smartops.operations;

import com.smartops.exception.BusinessException;
import com.smartops.security.SecurityAssertions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/**
 * SSH/SFTP 连接目标与身份文件收口策略（批次一 #3）。
 *
 * <p>连接中心默认允许任意主机/端口，可被当成任意目标的跳板；identityPath 也能指向
 * 后端主机上的任意文件。这里改为：生产环境必须显式配置目标白名单（主机或 CIDR，
 * 可带端口），且私钥只能取自受控目录；未配置即拒绝（fail-closed）。
 * 非生产环境未配置时沿用旧行为并告警，避免本地联调被一刀切。</p>
 */
@Component
public class SshTargetPolicy {

    private static final Logger log = LoggerFactory.getLogger(SshTargetPolicy.class);

    private final List<String> allowedTargets;
    private final Path identityRoot;
    private final boolean enforced;

    public SshTargetPolicy(
            @Value("${smartops.operations.ssh.allowed-targets:}") String allowedTargets,
            @Value("${smartops.operations.ssh.identity-root:}") String identityRoot,
            @Value("${smartops.security.production:false}") boolean explicitProduction,
            @Value("${spring.profiles.active:}") String activeProfiles) {
        this.allowedTargets = parseTargets(allowedTargets);
        this.identityRoot = identityRoot == null || identityRoot.isBlank()
                ? null : Path.of(identityRoot).toAbsolutePath().normalize();
        this.enforced = SecurityAssertions.isProduction(splitProfiles(activeProfiles), explicitProduction);
        if (!enforced && this.allowedTargets.isEmpty()) {
            log.warn("SECURITY: smartops.operations.ssh.allowed-targets 未配置——仅非生产环境放行，生产上线前必须配置");
        }
    }

    /** 目标白名单为空时：生产拒绝（fail-closed），非生产沿用旧行为。 */
    public void requireAllowedTarget(String host, int port) {
        if (allowedTargets.isEmpty()) {
            if (!enforced) return;
            throw new BusinessException(403, "TARGET_NOT_ALLOWED");
        }
        if (!matches(host, port)) throw new BusinessException(403, "TARGET_NOT_ALLOWED");
    }

    /** 私钥路径必须落在受控目录内；未配置目录时生产拒绝任何私钥。 */
    public void requireAllowedIdentity(String identityPath) {
        if (identityPath == null || identityPath.isBlank()) return;
        if (identityRoot == null) {
            if (!enforced) return;
            throw new BusinessException(403, "IDENTITY_PATH_NOT_ALLOWED");
        }
        Path normalized;
        try {
            normalized = Path.of(identityPath).toAbsolutePath().normalize();
        } catch (RuntimeException ex) {
            throw new BusinessException(400, "IDENTITY_PATH_NOT_ALLOWED");
        }
        if (!normalized.startsWith(identityRoot)) throw new BusinessException(403, "IDENTITY_PATH_NOT_ALLOWED");
        if (!Files.isRegularFile(normalized) || !Files.isReadable(normalized)) {
            throw new BusinessException(400, "IDENTITY_FILE_UNREADABLE");
        }
    }

    private boolean matches(String host, int port) {
        String normalized = host == null ? "" : host.trim().toLowerCase(Locale.ROOT);
        if (normalized.startsWith("[") && normalized.endsWith("]")) {
            normalized = normalized.substring(1, normalized.length() - 1);
        }
        for (String target : allowedTargets) {
            if (target.contains("/")) {
                if (matchesCidr(normalized, target)) return true;
                continue;
            }
            int idx = target.lastIndexOf(':');
            boolean hasPort = idx >= 0 && target.indexOf(':') == idx;
            String targetHost = hasPort ? target.substring(0, idx) : target;
            if (!targetHost.equals(normalized)) continue;
            if (!hasPort) return true;
            try {
                if (Integer.parseInt(target.substring(idx + 1)) == port) return true;
            } catch (NumberFormatException ignored) {
                // 构造期已校验格式，这里不会发生
            }
        }
        return false;
    }

    private static boolean matchesCidr(String host, String cidr) {
        String[] parts = cidr.split("/");
        try {
            byte[] network = InetAddress.getByName(parts[0]).getAddress();
            int prefix = Integer.parseInt(parts[1].trim());
            for (InetAddress resolved : InetAddress.getAllByName(host)) {
                if (inRange(resolved.getAddress(), network, prefix)) return true;
            }
        } catch (UnknownHostException | NumberFormatException ex) {
            return false;
        }
        return false;
    }

    private static boolean inRange(byte[] address, byte[] network, int prefix) {
        if (address.length != network.length) return false;
        int fullBytes = prefix / 8;
        int restBits = prefix % 8;
        for (int i = 0; i < fullBytes; i++) {
            if (address[i] != network[i]) return false;
        }
        if (restBits == 0) return true;
        int mask = (0xff << (8 - restBits)) & 0xff;
        return (address[fullBytes] & mask) == (network[fullBytes] & mask);
    }

    private static List<String> parseTargets(String raw) {
        List<String> parsed = new ArrayList<>();
        if (raw == null || raw.isBlank()) return parsed;
        for (String item : raw.split(",")) {
            String value = item.trim();
            if (value.isEmpty()) continue;
            validateTarget(value);
            parsed.add(value.toLowerCase(Locale.ROOT));
        }
        return List.copyOf(parsed);
    }

    private static void validateTarget(String value) {
        if (value.contains("/")) {
            String[] parts = value.split("/", -1);
            if (parts.length != 2) throw new IllegalArgumentException("Invalid SSH target: " + value);
            parseAddress(parts[0], value);
            int maxBits = parts[0].contains(":") ? 128 : 32;
            try {
                int prefix = Integer.parseInt(parts[1].trim());
                if (prefix < 0 || prefix > maxBits) throw new NumberFormatException();
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException("Invalid SSH target prefix: " + value);
            }
            return;
        }
        String host = value;
        int idx = value.lastIndexOf(':');
        if (idx >= 0 && value.indexOf(':') == idx) {
            host = value.substring(0, idx);
            try {
                int port = Integer.parseInt(value.substring(idx + 1));
                if (port <= 0 || port > 65535) throw new NumberFormatException();
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException("Invalid SSH target: " + value);
            }
        }
        if (host.isBlank() || host.length() > 253) throw new IllegalArgumentException("Invalid SSH target: " + value);
    }

    private static void parseAddress(String address, String value) {
        try {
            InetAddress.getByName(address);
        } catch (UnknownHostException ex) {
            throw new IllegalArgumentException("Invalid SSH target: " + value);
        }
    }

    private static List<String> splitProfiles(String activeProfiles) {
        if (activeProfiles == null || activeProfiles.isBlank()) return List.of();
        return Arrays.stream(activeProfiles.split(","))
                .map(String::trim)
                .filter(profile -> !profile.isEmpty())
                .toList();
    }
}
