package com.smartops.runbook;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 定时执行 / 事件触发的后台扫描。
 *
 * <p>默认延迟很大且可由配置关闭式启动（与 SentinelPoller、AlertLifecyclePoller 同口径），
 * 避免后台线程干扰集成测试；真实触发同时提供手动端点
 * {@code POST /api/runbooks/automation/fire} 便于运维核验。</p>
 *
 * <p>扫描只负责"生成待绑定目标的作业"，绝不代替人工选定目标后执行。</p>
 */
@Component
public class RunbookPoller {

    private static final Logger LOG = LoggerFactory.getLogger(RunbookPoller.class);

    private final RunbookExecutionService execution;

    public RunbookPoller(RunbookExecutionService execution) {
        this.execution = execution;
    }

    @Scheduled(initialDelayString = "${smartops.runbook.schedule.initial-delay-ms:600000}",
            fixedDelayString = "${smartops.runbook.schedule.interval-ms:60000}")
    public void fireSchedules() {
        try {
            execution.fireDueSchedules();
        } catch (RuntimeException failure) {
            LOG.warn("runbook schedule scan failed: {}", failure.getMessage());
        }
    }

    @Scheduled(initialDelayString = "${smartops.runbook.alert.initial-delay-ms:600000}",
            fixedDelayString = "${smartops.runbook.alert.interval-ms:60000}")
    public void fireAlertTriggers() {
        try {
            execution.fireAlertTriggers(30, 100);
        } catch (RuntimeException failure) {
            LOG.warn("runbook alert trigger scan failed: {}", failure.getMessage());
        }
    }
}
