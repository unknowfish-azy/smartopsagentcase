package com.smartops.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Clock;

@Configuration
public class AdminMfaConfig {
    @Bean Clock mfaClock() { return Clock.systemUTC(); }
}
