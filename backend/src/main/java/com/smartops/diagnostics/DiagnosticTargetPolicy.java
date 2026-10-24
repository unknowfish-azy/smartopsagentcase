package com.smartops.diagnostics;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.springframework.stereotype.Service;
import java.net.InetAddress;
import java.net.URI;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class DiagnosticTargetPolicy {
    private final Map<String, ApprovedTarget> targets = new LinkedHashMap<>();

    public DiagnosticTargetPolicy(DiagnosticTargetProperties properties) {
        for (var target : properties.getTargets()) {
            requireConfig(target.id() != null && target.id().matches("[a-zA-Z0-9_-]{1,64}"));
            requireConfig(target.displayName() != null && target.displayName().length() <= 80 && !target.displayName().isBlank());
            requireConfig("https".equals(target.scheme()) || "http".equals(target.scheme()));
            requireConfig(target.hostname() != null && target.hostname().length() <= 253
                    && target.hostname().matches("[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?"));
            requireConfig(target.port() != null && target.port() > 0 && target.port() <= 65535);
            requireConfig(target.path() != null && target.path().length() <= 1024 && target.path().matches("/[a-zA-Z0-9/._~%+-]*")
                    && !target.path().toLowerCase().matches(".*%(?:0d|0a|00).*"));
            requireConfig(target.expectedStatus() != null && target.expectedStatus() >= 100 && target.expectedStatus() <= 599);
            requireConfig(target.pinnedAddresses() != null && !target.pinnedAddresses().isEmpty() && target.pinnedAddresses().size() <= 4);
            var addresses = new ArrayList<InetAddress>();
            for (String address : target.pinnedAddresses()) addresses.add(parseAddress(target.hostname(), address));
            var users = target.allowedUserIds() == null ? List.<Long>of() : List.copyOf(target.allowedUserIds());
            requireConfig(users.stream().allMatch(id -> id != null && id > 0));
            URI uri = URI.create(target.scheme() + "://" + target.hostname() + ":" + target.port() + target.path());
            requireConfig(uri.getHost() != null && uri.getUserInfo() == null && uri.getQuery() == null && uri.getFragment() == null);
            var approved = new ApprovedTarget(target.id(), target.displayName(), uri, List.copyOf(addresses), users, target.expectedStatus());
            requireConfig(targets.putIfAbsent(target.id(), approved) == null);
        }
    }

    private static InetAddress parseAddress(String hostname, String value) {
        try {
            requireConfig(value != null && (value.matches("(?:0|[1-9][0-9]{0,2})(?:\\.(?:0|[1-9][0-9]{0,2})){3}")
                    || value.contains(":") && value.matches("[a-fA-F0-9:.]+")));
            InetAddress parsed = InetAddress.getByName(value);
            requireConfig(!parsed.isAnyLocalAddress() && !parsed.isLoopbackAddress() && !parsed.isLinkLocalAddress() && !parsed.isMulticastAddress());
            byte[] bytes = parsed.getAddress();
            int first = bytes[0] & 255;
            if (bytes.length == 4) {
                int second = bytes[1] & 255;
                requireConfig(first != 0 && first < 224 && !(first == 100 && second >= 64 && second <= 127));
                requireConfig(!(first == 192 && second == 0 && bytes[2] == 0));
                requireConfig(!parsed.getHostAddress().equals("168.63.129.16"));
            } else {
                requireConfig((first & 0xe0) == 0x20);
            }
            return InetAddress.getByAddress(hostname, bytes);
        } catch (java.net.UnknownHostException exception) {
            throw new IllegalArgumentException("Invalid diagnostic target address");
        }
    }

    private static void requireConfig(boolean valid) {
        if (!valid) throw new IllegalArgumentException("Invalid diagnostic target configuration");
    }
    public static boolean administrator(SessionUser user) {
        return user != null && "admin".equals(user.role()) && "admin".equals(user.portal());
    }
    private boolean allowed(SessionUser user, ApprovedTarget target) {
        return user != null && !user.mustChangePassword() && (administrator(user) || target.users().contains(user.id()));
    }
    public int count(SessionUser user) {
        return list(user).size();
    }

    public List<TargetSummary> list(SessionUser user) {
        requireUser(user);
        return targets.values().stream().filter(target -> allowed(user, target))
                .map(target -> new TargetSummary(target.id(), target.label(), target.uri().getScheme(), target.expectedStatus())).toList();
    }
    public ApprovedTarget require(SessionUser user, String id) {
        requireUser(user);
        var target = targets.get(id);
        if (target == null || !allowed(user, target)) throw new BusinessException(403, "目标未配置或未授权");
        return target;
    }
    public static void requireUser(SessionUser user) {
        if (user == null || user.id() == null) throw new BusinessException(401, "请先登录");
        if (user.mustChangePassword()) throw new BusinessException(403, "请先修改初始密码");
    }
    public record TargetSummary(String id, String label, String scheme, int expectedStatus) {}
    public record ApprovedTarget(String id, String label, URI uri, List<InetAddress> addresses, List<Long> users, int expectedStatus) {}
}
