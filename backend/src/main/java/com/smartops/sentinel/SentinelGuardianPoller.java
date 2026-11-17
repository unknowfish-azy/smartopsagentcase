package com.smartops.sentinel;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 守护 Agent 的常驻调度：取证每 30 秒补齐新告警，基线学习每 10 分钟跑一次。
 *
 * <p>与采信轮询同一条纪律：任何异常只记日志，绝不让调度线程退出。</p>
 */
@Component
public class SentinelGuardianPoller {

    private static final Logger log = LoggerFactory.getLogger(SentinelGuardianPoller.class);

    private final SentinelGuardianService guardian;
    private final Plan1ModelingRunner plan1Runner;

    public SentinelGuardianPoller(SentinelGuardianService guardian, Plan1ModelingRunner plan1Runner) {
        this.guardian = guardian;
        this.plan1Runner = plan1Runner;
    }

    @Scheduled(
            initialDelayString = "${smartops.sentinel.guardian.collect.initial-delay-ms:45000}",
            fixedDelayString = "${smartops.sentinel.guardian.collect.interval-ms:30000}")
    public void collectEvidence() {
        try {
            int enriched = guardian.enrichPending(20);
            if (enriched > 0) log.info("sentinel guardian collected evidence for {} alert(s)", enriched);
        } catch (Exception failure) {
            log.warn("sentinel guardian collect failed: {}", failure.getMessage());
        }
    }

    @Scheduled(
            initialDelayString = "${smartops.sentinel.guardian.learn.initial-delay-ms:120000}",
            fixedDelayString = "${smartops.sentinel.guardian.learn.interval-ms:600000}")
    public void learnBaselines() {
        try {
            int learned = guardian.learnAll();
            if (learned > 0) log.info("sentinel guardian refreshed {} baseline profile(s)", learned);
        } catch (Exception failure) {
            log.warn("sentinel guardian learning failed: {}", failure.getMessage());
        }

        // ── Java 基线学习完成后，跑 Python 建模脚本 ──
        // 注意顺序：Java learnAll 有 @Transactional，必须等它提交完 Python 再启动
        // （Python 用独立 JDBC 连接写 DB，和 Java 事务边界无关）。
        try {
            int scanned = plan1Runner.run();
            if (scanned > 0) log.info("sentinel plan1 modeling scanned {} samples", scanned);
        } catch (Exception failure) {
            log.warn("sentinel plan1 modeling runner failed: {}", failure.getMessage());
        }
    }
}
