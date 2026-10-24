package com.smartops.integration;

import com.smartops.SmartOpsApplication;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(classes = SmartOpsApplication.class)
@ActiveProfiles("test")
class SmartOpsApplicationIntegrationTest {

    @Test
    void contextLoads() {
    }
}