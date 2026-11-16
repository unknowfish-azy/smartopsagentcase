package com.smartops.knowledge;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 快照保留策略（T35a，D4：20 版/URL、清理默认关、可配置）。
 *
 * <p>按 (user_id,url) / (source_id,url) 分组保留最近 N 版，只删旧快照行，
 * 不动候选与正式知识条目；删除动作记录条数（可审计）。默认关闭，显式开启才由调度触发。</p>
 */
@Service
public class WebResearchRetentionService {

    private final JdbcTemplate jdbc;
    private final WebResearchMetrics metrics;
    private final boolean enabled;
    private final int maxVersions;

    public WebResearchRetentionService(JdbcTemplate jdbc,
                                       WebResearchMetrics metrics,
                                       @Value("${smartops.web-research.retention.enabled:false}") boolean enabled,
                                       @Value("${smartops.web-research.retention.max-versions:20}") int maxVersions) {
        this.jdbc = jdbc;
        this.metrics = metrics;
        this.enabled = enabled;
        this.maxVersions = Math.max(1, maxVersions);
    }

    public boolean isEnabled() {
        return enabled;
    }

    /** 手动/调度入口：清理未开启时直接返回 0，不删任何数据。 */
    public long pruneAll() {
        if (!enabled) return 0;
        long deleted = pruneWebResearchPages() + pruneCrawlPages();
        metrics.retentionDeleted(deleted);
        return deleted;
    }

    /** 每天扫一次（显式开启才真正删除）。 */
    @Scheduled(fixedDelayString = "${smartops.web-research.retention.sweep-ms:86400000}", initialDelayString = "${smartops.web-research.retention.initial-delay-ms:3600000}")
    public void scheduledPrune() {
        pruneAll();
    }

    long pruneWebResearchPages() {
        // web_research_page 主键是 task_id（一任务一快照），无 id 列
        List<Long> ids = jdbc.queryForList(
                "SELECT task_id FROM (SELECT task_id, ROW_NUMBER() OVER (PARTITION BY user_id, url ORDER BY task_id DESC) AS rn FROM web_research_page) ranked WHERE rn > ?",
                Long.class, maxVersions);
        deleteByIds("web_research_page", "task_id", ids);
        return ids.size();
    }

    long pruneCrawlPages() {
        List<Long> ids = jdbc.queryForList(
                "SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY source_id, url ORDER BY id DESC) AS rn FROM knowledge_crawl_page) ranked WHERE rn > ?",
                Long.class, maxVersions);
        deleteByIds("knowledge_crawl_page", "id", ids);
        return ids.size();
    }

    private void deleteByIds(String table, String keyColumn, List<Long> ids) {
        for (Long id : ids) {
            jdbc.update("DELETE FROM " + table + " WHERE " + keyColumn + "=?", id);
        }
    }
}
