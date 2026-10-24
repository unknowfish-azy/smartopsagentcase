package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.operations.OperationsCapabilityService;
import com.smartops.operations.OperationsProtocol;
import com.smartops.operations.ProtocolCapability;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/operations")
@RequiredArgsConstructor
public class OperationsCapabilityController {

    private final OperationsCapabilityService capabilityService;

    @GetMapping("/capabilities")
    public ApiResponse<List<ProtocolCapability>> capabilities() {
        return ApiResponse.success(
                capabilityService.list().values().stream().toList()
        );
    }
}
