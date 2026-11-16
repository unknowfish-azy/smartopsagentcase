package com.smartops.observability;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 引擎运行时事实聚合（T38）。
 *
 * <p>只读真实表：MAX(时间列) + COUNT(时间列) + 最近一条成功列。
 * 所有表名/列名来自 {@link EngineCatalog}，禁止拼接外部输入；
 * 外部只传 catalog 白名单 id，非法 id 直接拒绝。</p>
 */
@Service
public class EngineSnapshotService {

    private final JdbcTemplate jdbc;

    public EngineSnapshotService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 汇总全部引擎的判定输入事实。training 不查库，直接空事实。 */
    public List<EngineStateClassifier.EngineFacts> collectAll() {
        List<EngineStateClassifier.EngineFacts> out = new ArrayList<>();
        for (EngineCatalog.EngineDef def : EngineCatalog.ordered()) {
            out.add(collect(def));
        }
        return out;
    }

    /** 单引擎事实。 */
    public EngineStateClassifier.EngineFacts collect(EngineCatalog.EngineDef def) {
        if (def.notRun()) {
            return new EngineStateClassifier.EngineFacts(def.id(), null, 0, true, null);
        }
        String table = def.table();
        String time = def.timeColumn();
        String success = def.successColumn();

        // 真实聚合：COUNT(时间列) 只算有真实时间标记的记录（NULL 视为未完成，不计心跳）。
        String agg = "SELECT MAX(" + time + "), COUNT(" + time + ") FROM " + table;
        Map<String, Object> row = jdbc.queryForMap(agg);
        Object maxRaw = row.values().iterator().next();
        Object cntRaw = new ArrayList<>(row.values()).get(1);
        long count = cntRaw == null ? 0L : ((Number) cntRaw).longValue();

        if (count == 0 || maxRaw == null) {
            return new EngineStateClassifier.EngineFacts(def.id(), null, 0, true, null);
        }

        Long lastEpoch = toEpochSec(maxRaw);
        // 最近一条真实记录的判定列值（用于 ERROR 与事件摘要）。
        String latestSql = "SELECT " + success + " FROM " + table
                + " WHERE " + time + " IS NOT NULL ORDER BY " + time + " DESC LIMIT 1";
        List<String> latest = jdbc.queryForList(latestSql, String.class);
        String raw = latest.isEmpty() ? null : latest.get(0);

        boolean ok = successOf(def.id(), raw);
        String summary = (raw == null || raw.isBlank()) ? "已记录" : abbreviate(def.id() + " · " + raw);
        return new EngineStateClassifier.EngineFacts(def.id(), lastEpoch, count, ok, summary);
    }

    /** 指定引擎最近 N 条真实事件（时间倒序）。 */
    public List<EngineObservabilityController.EventItem> eventStream(String engineId, int limit) {
        EngineCatalog.EngineDef def = EngineCatalog.get(engineId);
        if (def == null || def.notRun()) {
            return List.of();
        }
        int safeLimit = Math.max(1, Math.min(200, limit));
        String sql = "SELECT " + def.timeColumn() + ", " + def.successColumn()
                + " FROM " + def.table()
                + " WHERE " + def.timeColumn() + " IS NOT NULL ORDER BY " + def.timeColumn()
                + " DESC LIMIT " + safeLimit;
        List<EngineObservabilityController.EventItem> out = new ArrayList<>();
        jdbc.query(sql, rs -> {
            Timestamp ts = rs.getTimestamp(1);
            String raw = rs.getString(2);
            out.add(new EngineObservabilityController.EventItem(
                    ts == null ? null : ts.toInstant().getEpochSecond(),
                    raw == null ? "OK" : abbreviate(raw),
                    raw == null ? "—" : abbreviate(def.id() + " · " + raw)));
        });
        return out;
    }

    /** 成功判定：错误码/状态列的真实语义，不臆造。 */
    private boolean successOf(String engineId, String raw) {
        if (raw == null || raw.isBlank()) {
            // 错误码为空 = 成功；其余表空值按"无失败信号"处理。
            return true;
        }
        String v = raw.toUpperCase();
        return switch (engineId) {
            case "web-research" -> false;              // error_code 非空即失败
            case "sentinel-poll", "operation-run" ->
                    !(v.contains("FAIL") || v.contains("ERROR") || v.contains("TIMEOUT"));
            default -> true;                            // 事件存在即引擎活跃，非失败信号
        };
    }

    private static Long toEpochSec(Object raw) {
        if (raw instanceof Timestamp ts) return ts.toInstant().getEpochSecond();
        if (raw instanceof java.sql.Date d) return d.toLocalDate().atStartOfDay(java.time.ZoneId.systemDefault()).toEpochSecond();
        if (raw instanceof java.util.Date d) return d.toInstant().getEpochSecond();
        if (raw instanceof Number n) return n.longValue();
        return null;
    }

    private static String abbreviate(String s) {
        if (s == null) return null;
        return s.length() <= 120 ? s : s.substring(0, 117) + "...";
    }
}
