package com.smartops.incident;

import com.smartops.service.IncidentService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 事件中心常驻任务：告警桥接 + SLA 超时扫描。
 *
 * <p>两类动作分开调度、互不影响；任一条抛异常只记日志，绝不让调度线程退出。</p>
 *
 * <p><b>告警自动建单默认关闭</b>（initial-delay 取极大值）。这是有意的：
 * 自动建单属于"会自己发生"的行为，应由部署方显式打开，
 * 也可以随时通过 {@code POST /api/incidents/from-alert/{alertId}} 手动触发。</p>
 */
@Component
public class IncidentBridgePoller {

    private static final Logger log = LoggerFactory.getLogger(IncidentBridgePoller.class);

    private final IncidentService incidentService;
    private final boolean autoBridgeEnabled;

    public IncidentBridgePoller(IncidentService incidentService,
                                @Value("${smartops.incident.autobridge.enabled:false}") boolean autoBridgeEnabled) {
        this.incidentService = incidentService;
        this.autoBridgeEnabled = autoBridgeEnabled;
    }

    /**
     * 把尚未关联事件的活动告警桥接成事件。
     *
     * <p>默认关闭：{@code smartops.incident.autobridge.enabled=false}。</p>
     */
    @Scheduled(
            initialDelayString = "${smartops.incident.autobridge.initial-delay-ms:9223372036854775807}",
            fixedDelayString = "${smartops.incident.autobridge.interval-ms:60000}")
    public void bridgeAlerts() {
        if (!autoBridgeEnabled) return;
        try {
            int created = incidentService.bridgeUnlinkedAlerts(200);
            if (created > 0) log.info("incident bridge created {} incident(s) from alerts", created);
        } catch (Exception failure) {
            log.warn("incident bridge failed: {}", failure.getMessage());
        }
    }

    /** SLA 超时扫描：只写时间线，不自动关单（关单必须人工填写根因与复盘）。 */
    @Scheduled(
            initialDelayString = "${smartops.incident.sla.initial-delay-ms:60000}",
            fixedDelayString = "${smartops.incident.sla.interval-ms:300000}")
    public void scanSla() {
        try {
            int recorded = incidentService.scanSlaBreaches(200);
            if (recorded > 0) log.info("incident SLA scan recorded {} breach(es)", recorded);
        } catch (Exception failure) {
            log.warn("incident SLA scan failed: {}", failure.getMessage());
        }
    }
}
