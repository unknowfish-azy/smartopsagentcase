package com.smartops.operations;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class OperationsCapabilityServiceTest {

    private final OperationsCapabilityService service =
            new OperationsCapabilityService();

    @Test
    void reports_only_ssh_and_sftp_as_connectable_in_first_release() {
        Map<OperationsProtocol, ProtocolCapability> capabilities =
                service.list();

        assertThat(capabilities.get(OperationsProtocol.SSH).status())
                .isEqualTo("SUPPORTED");
        assertThat(capabilities.get(OperationsProtocol.SFTP).status())
                .isEqualTo("SUPPORTED");
        assertThat(capabilities.get(OperationsProtocol.RDP).status())
                .isEqualTo("REQUIRES_NATIVE_BRIDGE");
    }
}
