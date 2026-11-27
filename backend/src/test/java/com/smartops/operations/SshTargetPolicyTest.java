package com.smartops.operations;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SshTargetPolicyTest {

    private static SshTargetPolicy policy(String targets, String identityRoot, boolean production) {
        return new SshTargetPolicy(targets, identityRoot, production, production ? "prod" : "dev");
    }

    @Test
    void productionWithEmptyAllowlistDeniesTargetsAndIdentity() {
        SshTargetPolicy policy = policy("", null, true);

        BusinessException target = assertThrows(BusinessException.class,
                () -> policy.requireAllowedTarget("192.168.44.145", 22));
        assertTrue(target.getMessage().contains("TARGET_NOT_ALLOWED"));

        BusinessException identity = assertThrows(BusinessException.class,
                () -> policy.requireAllowedIdentity("/home/op/.ssh/id_rsa"));
        assertTrue(identity.getMessage().contains("IDENTITY_PATH_NOT_ALLOWED"));

        // 未使用私钥的密码认证不受影响
        assertDoesNotThrow(() -> policy.requireAllowedIdentity(null));
    }

    @Test
    void nonProductionWithEmptyAllowlistKeepsLegacyBehaviour() {
        SshTargetPolicy policy = policy("", null, false);
        assertDoesNotThrow(() -> policy.requireAllowedTarget("192.168.44.145", 22));
        assertDoesNotThrow(() -> policy.requireAllowedIdentity("/home/op/.ssh/id_rsa"));
    }

    @Test
    void configuredHostPortMustMatchExactly() {
        SshTargetPolicy policy = policy("192.168.44.145:22", null, true);

        assertDoesNotThrow(() -> policy.requireAllowedTarget("192.168.44.145", 22));
        assertThrows(BusinessException.class, () -> policy.requireAllowedTarget("192.168.44.145", 2222));
        assertThrows(BusinessException.class, () -> policy.requireAllowedTarget("10.0.0.9", 22));
    }

    @Test
    void cidrTargetMatchesAnyAddressInRange() {
        SshTargetPolicy policy = policy("192.168.44.0/24", null, true);

        assertDoesNotThrow(() -> policy.requireAllowedTarget("192.168.44.145", 22));
        assertThrows(BusinessException.class, () -> policy.requireAllowedTarget("192.168.45.1", 22));
    }

    @Test
    void identityMustStayInsideControlledRoot(@TempDir Path root, @TempDir Path outside) throws Exception {
        Path allowed = root.resolve("id_rsa");
        Files.writeString(allowed, "key");
        Path foreign = outside.resolve("id_rsa");
        Files.writeString(foreign, "key");

        SshTargetPolicy policy = policy("", root.toString(), true);
        assertDoesNotThrow(() -> policy.requireAllowedIdentity(allowed.toString()));
        assertThrows(BusinessException.class, () -> policy.requireAllowedIdentity(foreign.toString()));
        // 目录穿越写法同样被拒绝
        assertThrows(BusinessException.class,
                () -> policy.requireAllowedIdentity(root + "/../" + outside.getFileName() + "/id_rsa"));
    }

    @Test
    void invalidConfigurationFailsFast() {
        assertThrows(IllegalArgumentException.class, () -> policy("192.168.44.145:notaport", null, true));
        assertThrows(IllegalArgumentException.class, () -> policy("10.0.0.0/99", null, true));
    }
}
