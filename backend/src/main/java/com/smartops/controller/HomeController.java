package com.smartops.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/** Public service landing endpoint for local deployment diagnostics. */
@RestController
public class HomeController {

    @Value("${spring.profiles.active:default}")
    private String profile;

    @GetMapping("/")
    public Map<String, Object> home() {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("service", "SmartOpsAgent Backend");
        response.put("status", "RUNNING");
        response.put("profile", profile);
        response.put("api_base", "/api");
        response.put("health", "/actuator/health");
        response.put("frontend", "http://localhost:5173/");
        return response;
    }
}
