package com.smartops.controller;

import com.smartops.common.ApiResponse;
import com.smartops.config.BusinessSchemaHealthIndicator;
import com.smartops.service.HarborCatalogService;
import com.smartops.service.ObservabilityService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class AdminReadinessController {
    private final BusinessSchemaHealthIndicator schema;
    private final ObservabilityService observability;
    private final HarborCatalogService harbor;
    private final boolean internalConfigured;

    public AdminReadinessController(BusinessSchemaHealthIndicator schema, ObservabilityService observability,
            HarborCatalogService harbor, @Value("${smartops.security.internal-token:}") String internalToken) {
        this.schema = schema; this.observability = observability; this.harbor = harbor;
        this.internalConfigured = internalToken != null && !internalToken.isBlank();
    }

    @GetMapping("/api/admin/readiness")
    public ApiResponse<Map<String, Object>> readiness() {
        return ApiResponse.success(Map.of("unavailableTables", schema.missingTables(), "observability", observability.sources(),
                "harbor", harbor.status(), "internalAuthenticationConfigured", internalConfigured,
                "userAuthentication", "SERVER_SESSION", "remoteConnectivity", "NOT_VERIFIED"));
    }
}
