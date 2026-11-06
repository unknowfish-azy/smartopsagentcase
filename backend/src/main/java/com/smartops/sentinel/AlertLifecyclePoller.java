package com.smartops.sentinel;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 告警生命周期的常驻任务：自动恢复 + 通知死信。
 *
 * <p>延迟起步（默认 5/10 分钟）是刻意的：这两件事都在改别人的告警状态，
 * 进程刚启动时不应该立刻动手；同时也能避免集成测试被后台线程干扰。</p>
 */
@Component
public class AlertLifecyclePoller {

    private static final Logger log = LoggerFactory.getLogger(AlertLifecyclePoller.class);

    private final AlertLifecycleService lifecycle;
    private final int deadLetterMaxAttempts;

    public AlertLifecyclePoller(AlertLifecycleService lifecycle,
                                @Value("${smartops.sentinel.dead-letter.max-attempts:3}") int deadLetterMaxAttempts) {
        this.lifecycle = lifecycle;
        this.deadLetterMaxAttempts = deadLetterMaxAttempts;
    }

    /** 指标恢复后把告警推进到待关闭。 */
    @Scheduled(
            initialDelayString = "${smartops.sentinel.recovery.initial-delay-ms:300000}",
            fixedDelayString = "${smartops.sentinel.recovery.interval-ms:60000}")
    public void recover() {
        try {
            lifecycle.resolveRecoveredAlerts(100);
        } catch (Exception failure) {
            log.warn("alert recovery failed: {}", failure.getMessage());
        }
    }

    /** 重试耗尽的投递进入死信。 */
    @Scheduled(
            initialDelayString = "${smartops.sentinel.dead-letter.initial-delay-ms:600000}",
            fixedDelayString = "${smartops.sentinel.dead-letter.interval-ms:300000}")
    public void deadLetter() {
        try {
            lifecycle.sweepDeadLetters(deadLetterMaxAttempts);
        } catch (Exception failure) {
            log.warn("alert dead-letter sweep failed: {}", failure.getMessage());
        }
    }
}
