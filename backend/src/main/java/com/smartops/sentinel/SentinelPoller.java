package com.smartops.sentinel;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 哨兵常驻轮询与定时脚本触发。
 *
 * <p>两件事分开调度、互不影响：采集失败不应该拖累定时计划，反之亦然。
 * 任一条抛异常都只记日志，绝不让调度线程退出。</p>
 */
@Component
public class SentinelPoller {

    private static final Logger log = LoggerFactory.getLogger(SentinelPoller.class);

    private final SentinelService service;
    private final SentinelScriptRunner runner;

    public SentinelPoller(SentinelService service, SentinelScriptRunner runner) {
        this.service = service;
        this.runner = runner;
    }

    @Scheduled(
            initialDelayString = "${smartops.sentinel.poll.initial-delay-ms:20000}",
            fixedDelayString = "${smartops.sentinel.poll.interval-ms:30000}")
    public void poll() {
        try {
            int sampled = service.pollDueTasks();
            if (sampled > 0) log.debug("sentinel polled {} due task(s)", sampled);
        } catch (Exception failure) {
            // 轮询失败绝不能让调度线程退出，也不能把异常抛给无关模块。
            log.warn("sentinel poll failed: {}", failure.getMessage());
        }
    }

    /**
     * 到点的定时脚本：**只生成待审批的预览**，不执行命令。
     *
     * <p>可用 {@code smartops.sentinel.schedule.enabled=false} 关闭。
     * 默认不开启（initial-delay 极大）是有意的：定时触发属于"会自己发生"的行为，
     * 应该由部署方显式打开，而不是默认就替人发起处置。</p>
     */
    @Scheduled(
            initialDelayString = "${smartops.sentinel.schedule.initial-delay-ms:9223372036854775807}",
            fixedDelayString = "${smartops.sentinel.schedule.interval-ms:60000}")
    public void fireSchedules() {
        try {
            int fired = runner.fireDueSchedules();
            if (fired > 0) log.info("sentinel fired {} scheduled script preparation(s) — awaiting approval", fired);
        } catch (Exception failure) {
            log.warn("sentinel schedule dispatch failed: {}", failure.getMessage());
        }
    }
}
