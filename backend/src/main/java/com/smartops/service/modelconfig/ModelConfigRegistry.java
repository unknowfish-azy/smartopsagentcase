package com.smartops.service.modelconfig;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 生效配置的只读快照持有者，同时支持全量与按比例灰度。
 *
 * <p>同一时刻最多两份快照：stable（全量版本）与 canary（灰度版本）。
 * 请求按 "用户 + 模型组" 做稳定分桶，桶号小于灰度比例时走 canary，
 * 因此同一用户在同一模型组上的路由不会来回跳。</p>
 *
 * <p>请求链路只读内存，不查配置表；控制面不可用时继续使用上一份快照。</p>
 */
@Slf4j
@Component
public class ModelConfigRegistry {

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    private volatile Loaded stable;
    private volatile Loaded canary;

    public ModelConfigRegistry(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public record Loaded(int version, int percent, ModelConfigSnapshot snapshot) {}

    @EventListener(ApplicationReadyEvent.class)
    public void loadOnStartup() {
        refreshIfChanged();
    }

    @Scheduled(
            fixedDelayString = "${smartops.model.control-plane.refresh-ms:15000}",
            initialDelayString = "${smartops.model.control-plane.initial-delay-ms:5000}"
    )
    public void refreshIfChanged() {
        try {
            var rows = jdbc.query(
                    "SELECT version_no,rollout_percent,snapshot_json FROM model_gateway_config_version "
                            + "WHERE status='ACTIVE' ORDER BY version_no DESC",
                    (rs, n) -> new Object[]{
                            rs.getInt("version_no"), rs.getInt("rollout_percent"), rs.getString("snapshot_json")});
            Loaded nextStable = null;
            Loaded nextCanary = null;
            for (Object[] row : rows) {
                int version = (Integer) row[0];
                int percent = (Integer) row[1];
                if (percent < 100 && nextCanary == null) {
                    nextCanary = new Loaded(version, percent, null);
                } else if (percent >= 100 && nextStable == null) {
                    nextStable = new Loaded(version, 100, null);
                }
            }
            if (same(stable, nextStable) && same(canary, nextCanary)) {
                return;
            }
            stable = parse(nextStable, "stable");
            canary = parse(nextCanary, "canary");
            if (stable == null && canary == null) {
                log.warn("模型网关配置版本已全部移除，路由回退到工作区直读");
            } else {
                log.info("模型网关配置快照已加载：stable=v{}，canary={}",
                        stable == null ? "-" : stable.version(),
                        canary == null ? "-" : "v" + canary.version() + "(" + canary.percent() + "%)");
            }
        } catch (Exception ex) {
            log.warn("模型网关配置快照加载失败，继续使用上一份快照", ex);
        }
    }

    /**
     * 按请求归属选出生效快照；未发布任何版本时返回 null，
     * 调用方回退到工作区直读。
     */
    public ModelConfigSnapshot resolve(Long ownerUserId, String groupSlug) {
        Loaded loaded = pick(ownerUserId, groupSlug);
        return loaded == null ? null : loaded.snapshot();
    }

    /**
     * 与 {@link #resolve} 同一套分桶规则的版本号。
     *
     * <p>审计写入用它记录"这次调用实际由哪个配置版本服务"，
     * 灰度期间 canary 流量不会被记成 stable 版本。</p>
     */
    public Integer resolveVersion(Long ownerUserId, String groupSlug) {
        Loaded loaded = pick(ownerUserId, groupSlug);
        return loaded == null ? null : loaded.version();
    }

    private Loaded pick(Long ownerUserId, String groupSlug) {
        Loaded gray = canary;
        if (gray != null && bucket(ownerUserId, groupSlug) < gray.percent()) {
            return gray;
        }
        Loaded full = stable;
        return full != null ? full : gray;
    }

    /** 全量快照；仅灰度时返回灰度快照，便于监控与审计。 */
    public ModelConfigSnapshot current() {
        Loaded full = stable;
        if (full != null) {
            return full.snapshot();
        }
        Loaded gray = canary;
        return gray == null ? null : gray.snapshot();
    }

    public Integer currentVersion() {
        Loaded full = stable;
        if (full != null) {
            return full.version();
        }
        Loaded gray = canary;
        return gray == null ? null : gray.version();
    }

    public Integer canaryVersion() {
        Loaded gray = canary;
        return gray == null ? null : gray.version();
    }

    public Integer canaryPercent() {
        Loaded gray = canary;
        return gray == null ? null : gray.percent();
    }

    /** 稳定分桶：同一用户在同一模型组上的灰度结果固定。 */
    static int bucket(Long ownerUserId, String groupSlug) {
        String key = ownerUserId + ":" + (groupSlug == null ? "" : groupSlug);
        return Math.floorMod(key.hashCode(), 100);
    }

    private Loaded parse(Loaded template, String role) throws Exception {
        if (template == null) {
            return null;
        }
        String json = jdbc.queryForObject(
                "SELECT snapshot_json FROM model_gateway_config_version WHERE version_no=? AND status='ACTIVE'",
                String.class, template.version());
        if (json == null) {
            return null;
        }
        ModelConfigSnapshot snapshot = mapper.readValue(json, ModelConfigSnapshot.class);
        log.debug("模型网关 {} 快照已解析：v{}", role, template.version());
        return new Loaded(template.version(), template.percent(), snapshot);
    }

    private static boolean same(Loaded left, Loaded right) {
        if (left == null || right == null) {
            return left == right;
        }
        return left.version() == right.version() && left.percent() == right.percent();
    }
}
