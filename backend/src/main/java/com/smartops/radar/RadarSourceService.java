package com.smartops.radar;

import com.smartops.exception.BusinessException;
import com.smartops.security.OutboundUrlPolicy;
import com.smartops.security.SessionUser;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

/**
 * 资源雷达来源注册与维护。
 *
 * <p>来源地址在登记时就过 {@link OutboundUrlPolicy}，采集阶段每个目标再复检一次；
 * 只在登记时不校验等于把 SSRF 留给后续采集器。</p>
 */
@Service
public class RadarSourceService {

    private static final String BASE = "SELECT id,name,collector_type,url,channel,trust_level,enabled,interval_minutes,"
            + "last_run_at,next_run_at,last_status,last_error,created_by,created_at,updated_at FROM radar_source";
    private static final int MIN_INTERVAL_MINUTES = 15;
    private static final int MAX_INTERVAL_MINUTES = 10080;

    private final JdbcTemplate jdbc;

    public RadarSourceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<RadarSource> list() {
        return jdbc.query(BASE + " ORDER BY channel, name", this::read);
    }

    public RadarSource require(long id) {
        List<RadarSource> found = jdbc.query(BASE + " WHERE id=?", this::read, id);
        if (found.isEmpty()) throw new BusinessException(404, "资源来源不存在");
        return found.get(0);
    }

    @Transactional
    public RadarSource create(SessionUser actor, String name, String collectorType, String url,
                              String channel, String trustLevel, Integer intervalMinutes) {
        String cleanName = name == null ? "" : name.strip();
        if (cleanName.isEmpty() || cleanName.length() > 120) {
            throw new BusinessException(400, "来源名称长度需在 1-120 之间");
        }
        if (collectorType == null || !RadarSource.COLLECTOR_TYPES.contains(collectorType)) {
            throw new BusinessException(400, "不支持的采集器类型：" + collectorType);
        }
        if (channel == null || !RadarSource.CHANNELS.contains(channel)) {
            throw new BusinessException(400, "不支持的资源域：" + channel);
        }
        String trust = trustLevel == null || trustLevel.isBlank() ? "L4" : trustLevel;
        if (!RadarSource.TRUST_LEVELS.contains(trust)) {
            throw new BusinessException(400, "不支持的可信等级：" + trust);
        }
        int interval = intervalMinutes == null ? 360 : intervalMinutes;
        requireValidInterval(interval);
        String target = validateUrl(url);
        try {
            jdbc.update("INSERT INTO radar_source(name,collector_type,url,channel,trust_level,enabled,interval_minutes,next_run_at,created_by)"
                            + " VALUES (?,?,?,?,?,TRUE,?,?,?)",
                    cleanName, collectorType, target, channel, trust, interval, Timestamp.from(Instant.now()), actor.id());
        } catch (DuplicateKeyException duplicate) {
            throw new BusinessException(409, "该来源地址已登记");
        }
        return jdbc.query(BASE + " WHERE url=?", this::read, target).get(0);
    }

    @Transactional
    public RadarSource update(long id, Boolean enabled, Integer intervalMinutes) {
        RadarSource current = require(id);
        boolean nextEnabled = enabled == null ? current.enabled() : enabled;
        int interval = intervalMinutes == null ? current.intervalMinutes() : intervalMinutes;
        requireValidInterval(interval);
        Timestamp nextRun = nextEnabled ? Timestamp.from(Instant.now()) : null;
        jdbc.update("UPDATE radar_source SET enabled=?,interval_minutes=?,next_run_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                nextEnabled, interval, nextRun, id);
        return require(id);
    }

    /** 采集结束后回写来源状态；nextRunAt 为空表示该来源已停用。 */
    public void markResult(long id, String status, String error, Instant lastRunAt, Instant nextRunAt) {
        jdbc.update("UPDATE radar_source SET last_run_at=?,next_run_at=?,last_status=?,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                Timestamp.from(lastRunAt), nextRunAt == null ? null : Timestamp.from(nextRunAt),
                truncate(status, 24), truncate(error, 500), id);
    }

    private void requireValidInterval(int interval) {
        if (interval < MIN_INTERVAL_MINUTES || interval > MAX_INTERVAL_MINUTES) {
            throw new BusinessException(400, "采集间隔需在 15-10080 分钟之间");
        }
    }

    private String validateUrl(String url) {
        if (url == null || url.isBlank()) throw new BusinessException(400, "来源地址不能为空");
        String target = url.strip();
        if (target.length() > 512) throw new BusinessException(400, "来源地址不能超过 512 字符");
        URI parsed;
        try {
            parsed = URI.create(target);
        } catch (IllegalArgumentException invalid) {
            throw new BusinessException(400, "来源地址格式无效");
        }
        if (!OutboundUrlPolicy.inspect(parsed).allowed()) {
            throw new BusinessException(400, "来源地址不允许访问（仅支持公网 http/https）");
        }
        return target;
    }

    private RadarSource read(ResultSet result, int row) throws SQLException {
        return new RadarSource(
                result.getLong("id"),
                result.getString("name"),
                result.getString("collector_type"),
                result.getString("url"),
                result.getString("channel"),
                result.getString("trust_level"),
                result.getBoolean("enabled"),
                result.getInt("interval_minutes"),
                instant(result, "last_run_at"),
                instant(result, "next_run_at"),
                result.getString("last_status"),
                result.getString("last_error"),
                result.getLong("created_by"),
                instant(result, "created_at"),
                instant(result, "updated_at"));
    }

    private static Instant instant(ResultSet result, String column) throws SQLException {
        Timestamp value = result.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    private static String truncate(String value, int max) {
        if (value == null) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }
}
