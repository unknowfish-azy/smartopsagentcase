package com.smartops.radar;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;

import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 采集编排：调用采集器 → 去重 → 评分 → 以 DRAFT 入库 → 回写运行日志与来源状态。
 *
 * <p>网络请求不包事务；单条失败只计入 failed，不中断整轮。没有对应采集器时
 * 如实返回 UNSUPPORTED，不伪造“采集成功但 0 条”。</p>
 */
@Service
public class RadarCollectionService {

    private static final Logger log = LoggerFactory.getLogger(RadarCollectionService.class);
    private static final int MAX_TITLE = 512;
    private static final int MAX_SUMMARY = 8000;
    private static final int MAX_EXTERNAL_ID = 255;
    private static final int MAX_URL = 512;

    private final JdbcTemplate jdbc;
    private final RadarSourceService sources;
    private final RadarScoreService scoring;
    private final Map<String, RadarCollector> collectors;

    public RadarCollectionService(JdbcTemplate jdbc, RadarSourceService sources, RadarScoreService scoring,
                                  List<RadarCollector> collectors) {
        this.jdbc = jdbc;
        this.sources = sources;
        this.scoring = scoring;
        this.collectors = collectors.stream()
                .collect(Collectors.toMap(RadarCollector::type, collector -> collector, (first, second) -> first));
    }

    public record CollectionResult(long sourceId, String status, int fetched, int kept, int skipped, int failed, String error) {
    }

    public CollectionResult collect(long sourceId, String trigger) {
        RadarSource source = sources.require(sourceId);
        Instant startedAt = Instant.now();
        long runId = startRun(sourceId, trigger);
        List<CollectedResource> resources = List.of();
        String status = "SUCCESS";
        String error = null;

        RadarCollector collector = collectors.get(source.collectorType());
        if (collector == null) {
            status = "UNSUPPORTED";
            error = "采集器未实现：" + source.collectorType();
        } else {
            try {
                resources = collector.collect(source);
            } catch (RuntimeException failure) {
                status = "FAILED";
                error = failure.getMessage();
                log.warn("资源雷达采集失败 sourceId={} type={}", sourceId, source.collectorType(), failure);
            }
        }

        int kept = 0;
        int skipped = 0;
        int failed = 0;
        for (CollectedResource resource : resources) {
            try {
                if (persist(resource, source)) {
                    kept++;
                } else {
                    skipped++;
                }
            } catch (RuntimeException failure) {
                failed++;
                log.warn("资源雷达条目入库失败 sourceId={} url={}", sourceId,
                        resource == null ? null : resource.url(), failure);
            }
        }
        if ("SUCCESS".equals(status) && failed > 0) status = "PARTIAL";

        int fetched = resources.size();
        finishRun(runId, fetched, kept, skipped, failed, error);
        sources.markResult(sourceId, status, error, startedAt, nextRun(source));
        return new CollectionResult(sourceId, status, fetched, kept, skipped, failed, error);
    }

    private boolean persist(CollectedResource resource, RadarSource source) {
        if (resource == null || !hasText(resource.url()) || !hasText(resource.title())) {
            throw new IllegalArgumentException("条目缺少标题或地址");
        }
        String url = resource.url().strip();
        if (url.length() > MAX_URL) throw new IllegalArgumentException("条目地址超过 " + MAX_URL + " 字符");
        RadarScoreService.Grade grade = scoring.grade(resource, source, Instant.now());
        try {
            jdbc.update("INSERT INTO radar_item(source_id,channel,external_id,title,summary,url,url_hash,kind,category,"
                            + "obtain,quality,trust_level,freshness,score,risk_flags,status,published_at,expires_at)"
                            + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?,?)",
                    source.id(), source.channel(),
                    truncate(resource.externalId(), MAX_EXTERNAL_ID),
                    truncate(resource.title().strip(), MAX_TITLE),
                    truncate(resource.summary(), MAX_SUMMARY),
                    url, grade.urlHash(), grade.kind(), grade.category(), grade.obtain(),
                    grade.quality(), grade.trustLevel(), grade.freshness(), grade.score(),
                    String.join(",", grade.riskFlags()),
                    resource.publishedAt() == null ? null : Timestamp.from(resource.publishedAt()),
                    resource.expiresAt() == null ? null : Timestamp.from(resource.expiresAt()));
            return true;
        } catch (DuplicateKeyException duplicate) {
            return false;
        }
    }

    private long startRun(long sourceId, String trigger) {
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO radar_run_log(source_id,trigger_type) VALUES (?,?)", new String[]{"id"});
            statement.setLong(1, sourceId);
            statement.setString(2, hasText(trigger) ? trigger : "MANUAL");
            return statement;
        }, keys);
        Number key = keys.getKey();
        return key == null ? 0L : key.longValue();
    }

    private void finishRun(long runId, int fetched, int kept, int skipped, int failed, String error) {
        if (runId <= 0) return;
        jdbc.update("UPDATE radar_run_log SET finished_at=CURRENT_TIMESTAMP,fetched=?,kept=?,skipped=?,failed=?,error=? WHERE id=?",
                fetched, kept, skipped, failed, truncate(error, 500), runId);
    }

    private Instant nextRun(RadarSource source) {
        return source.enabled() ? Instant.now().plus(Duration.ofMinutes(source.intervalMinutes())) : null;
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private static String truncate(String value, int max) {
        if (value == null) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }
}
