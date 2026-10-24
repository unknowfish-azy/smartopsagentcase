package com.smartops.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.smartops.operations.OperationsCapabilityService;
import com.smartops.operations.OperationsProtocol;
import com.smartops.operations.ProtocolCapability;

import java.util.Map;

@WebMvcTest(OperationsCapabilityController.class)
@AutoConfigureMockMvc(addFilters = false)
class OperationsCapabilityControllerTest {
    @MockBean private com.smartops.security.UserAccountService accounts;
    @MockBean private com.smartops.security.SecurityAuditService audit;

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OperationsCapabilityService capabilityService;

    @Test
    void returns_capability_statuses_for_the_operations_workspace() throws Exception {
        given(capabilityService.list()).willReturn(Map.of(
                OperationsProtocol.SSH, new ProtocolCapability(OperationsProtocol.SSH, "SUPPORTED", "bridge"),
                OperationsProtocol.RDP, new ProtocolCapability(OperationsProtocol.RDP, "REQUIRES_NATIVE_BRIDGE", "native")
        ));

        mockMvc.perform(get("/api/operations/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].status").exists());
    }
}
