package com.smartops.sentinel;

import org.springframework.context.annotation.Configuration;

/**
 * 哨兵模块的调度开关。
 *
 * <p>建表/加列脚本已由 Flyway（{@code db/migration}）接管，这里只保留调度相关配置。</p>
 *
 * <p>调度用 {@code @EnableScheduling} 显式开启，因为此前项目没有任何
 * {@code @Scheduled} 使用；开启范围仅限哨兵轮询，不影响其它模块。</p>
 */
@Configuration
@org.springframework.scheduling.annotation.EnableScheduling
public class SentinelConfig {

    // 不在这里再声明 Clock：项目已由 AdminMfaConfig 提供 mfaClock，
    // 多一个同类型 bean 会让按类型注入变得有歧义（曾导致应用启动失败）。
    // SentinelService 用 @Qualifier("mfaClock") 显式引用既有 bean。
}
