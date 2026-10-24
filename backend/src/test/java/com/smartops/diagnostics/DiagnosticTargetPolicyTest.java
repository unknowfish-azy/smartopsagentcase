package com.smartops.diagnostics;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.assertj.core.api.Assertions.*;

class DiagnosticTargetPolicyTest {
    static SessionUser user(long id) { return new SessionUser(id, "tester", "operator", "user", false, 0); }
    static DiagnosticTargetProperties.Target target(String address) {
        return new DiagnosticTargetProperties.Target("web", "授权网站", "https", "service.example", 443,
                "/health", List.of(address), List.of(11L), 200);
    }
    static DiagnosticTargetPolicy policy(String address) {
        var config = new DiagnosticTargetProperties();
        config.setTargets(List.of(target(address)));
        return new DiagnosticTargetPolicy(config);
    }
    @Test void defaultsToNoTargets() {
        assertThat(new DiagnosticTargetPolicy(new DiagnosticTargetProperties()).list(user(11))).isEmpty();
    }
    @Test void authorizesBeforeExposingTargetAndHonorsPortal() {
        var policy = policy("203.0.113.10");
        assertThat(policy.require(user(11), "web").addresses()).hasSize(1);
        assertThat(policy.list(user(22))).isEmpty();
        assertThatThrownBy(() -> policy.require(user(22), "web")).isInstanceOf(BusinessException.class);
        var adminUser = new SessionUser(22L, "admin", "admin", "user", false, 0);
        var adminPortal = new SessionUser(22L, "admin", "admin", "admin", false, 0);
        assertThat(policy.list(adminUser)).isEmpty();
        assertThat(policy.list(adminPortal)).hasSize(1);
        assertThatThrownBy(() -> policy.require(null, "web")).isInstanceOf(BusinessException.class);
    }
    @Test void blocksMetadataLoopbackMulticastAndAmbiguousAddresses() {
        for (String address : List.of("127.0.0.1", "::1", "169.254.169.254", "100.100.100.200", "0.0.0.0",
                "224.0.0.1", "::ffff:127.0.0.1", "fe80::1", "fc00::1", "64:ff9b::7f00:1", "localhost", "127.1", "0177.0.0.1")) {
            assertThatThrownBy(() -> policy(address)).as(address).isInstanceOf(IllegalArgumentException.class);
        }
        assertThat(policy("10.20.30.40").list(user(11))).hasSize(1);
    }
    @Test void rejectsHeaderInjectionAndDuplicateIds() {
        var config = new DiagnosticTargetProperties();
        config.setTargets(List.of(target("203.0.113.10"), target("203.0.113.11")));
        assertThatThrownBy(() -> new DiagnosticTargetPolicy(config)).isInstanceOf(IllegalArgumentException.class);
        config.setTargets(List.of(new DiagnosticTargetProperties.Target("web", "web", "https", "example.com\r\nX: bad",
                443, "/", List.of("203.0.113.10"), List.of(11L), 200)));
        assertThatThrownBy(() -> new DiagnosticTargetPolicy(config)).isInstanceOf(IllegalArgumentException.class);
    }
}
