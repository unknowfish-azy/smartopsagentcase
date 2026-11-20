package com.smartops.radar;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 资源条目查询。所有过滤条件都走参数绑定；状态只接受 {@link RadarItem#STATUSES} 白名单。
 */
@Service
public class RadarItemService {

    private static final String BASE = "SELECT i.id,i.source_id,s.name AS source_name,i.channel,i.external_id,"
            + "i.title,i.summary,i.url,i.kind,i.category,i.obtain,i.quality,i.trust_level,i.freshness,i.score,"
            + "i.risk_flags,i.status,i.published_at,i.expires_at,i.created_at "
            + "FROM radar_item i LEFT JOIN radar_source s ON s.id=i.source_id";

    private final JdbcTemplate jdbc;

    public RadarItemService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<RadarItem> list(String channel, String kind, String status, String query, Integer limit) {
        if (hasText(status) && !RadarItem.STATUSES.contains(status)) {
            throw new BusinessException(400, "不支持的条目状态：" + status);
        }
        int size = limit == null ? 50 : Math.max(1, Math.min(200, limit));
        StringBuilder sql = new StringBuilder(BASE).append(" WHERE 1=1");
        List<Object> args = new ArrayList<>();
        if (hasText(channel)) {
            sql.append(" AND i.channel=?");
            args.add(channel);
        }
        if (hasText(kind)) {
            sql.append(" AND i.kind=?");
            args.add(kind);
        }
        if (hasText(status)) {
            sql.append(" AND i.status=?");
            args.add(status);
        }
        if (hasText(query)) {
            sql.append(" AND (LOWER(i.title) LIKE ? OR LOWER(i.summary) LIKE ?)");
            String like = "%" + query.strip().toLowerCase(Locale.ROOT) + "%";
            args.add(like);
            args.add(like);
        }
        sql.append(" ORDER BY i.score DESC, i.published_at DESC, i.id DESC LIMIT ?");
        args.add(size);
        return jdbc.query(sql.toString(), this::read, args.toArray());
    }

    /**
     * 日报取数：窗口内新增且未过期的条目。
     *
     * <p>没有发布时间的条目用入库时间兜底（{@code COALESCE}），避免 RSS 缺字段时整条漏掉；
     * 已核实条目排在前面，其余按评分倒序。这里的 {@code status} 过滤不改变条目状态，
     * 只是把已归档/已失效的排除在日报之外。</p>
     */
    public List<RadarItem> window(Instant from, Instant now, String channel, int limit) {
        int size = Math.max(1, Math.min(200, limit));
        StringBuilder sql = new StringBuilder(BASE)
                .append(" WHERE i.status IN ('DRAFT','VERIFIED')")
                .append(" AND COALESCE(i.published_at, i.created_at) >= ?")
                .append(" AND (i.expires_at IS NULL OR i.expires_at > ?)");
        List<Object> args = new ArrayList<>();
        args.add(Timestamp.from(from));
        args.add(Timestamp.from(now));
        if (hasText(channel)) {
            sql.append(" AND i.channel=?");
            args.add(channel);
        }
        sql.append(" ORDER BY CASE WHEN i.status='VERIFIED' THEN 0 ELSE 1 END, i.score DESC, i.id DESC LIMIT ?");
        args.add(size);
        return jdbc.query(sql.toString(), this::read, args.toArray());
    }

    public Map<String, Object> detail(long id) {
        List<RadarItem> found = jdbc.query(BASE + " WHERE i.id=?", this::read, id);
        if (found.isEmpty()) throw new BusinessException(404, "资源条目不存在");
        List<Map<String, Object>> evidences = jdbc.query(
                "SELECT id,evidence_url,evidence_type,captured_at,verified_at,verified_by,note "
                        + "FROM radar_item_evidence WHERE item_id=? ORDER BY captured_at DESC",
                (result, row) -> {
                    Map<String, Object> evidence = new LinkedHashMap<>();
                    evidence.put("id", result.getLong("id"));
                    evidence.put("evidenceUrl", result.getString("evidence_url"));
                    evidence.put("evidenceType", result.getString("evidence_type"));
                    evidence.put("capturedAt", instant(result, "captured_at"));
                    evidence.put("verifiedAt", instant(result, "verified_at"));
                    Object verifiedBy = result.getObject("verified_by");
                    evidence.put("verifiedBy", verifiedBy == null ? null : result.getLong("verified_by"));
                    evidence.put("note", result.getString("note"));
                    return evidence;
                }, id);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("item", found.get(0));
        view.put("evidences", evidences);
        return view;
    }

    public Map<String, Object> stats() {
        List<Map<String, Object>> channels = jdbc.query(
                "SELECT channel, COUNT(*) AS total,"
                        + " SUM(CASE WHEN status='VERIFIED' THEN 1 ELSE 0 END) AS verified,"
                        + " SUM(CASE WHEN status='DRAFT' THEN 1 ELSE 0 END) AS drafts,"
                        + " AVG(score) AS avg_score"
                        + " FROM radar_item GROUP BY channel ORDER BY channel",
                (result, row) -> {
                    Map<String, Object> entry = new LinkedHashMap<>();
                    entry.put("channel", result.getString("channel"));
                    entry.put("total", result.getLong("total"));
                    entry.put("verified", result.getLong("verified"));
                    entry.put("drafts", result.getLong("drafts"));
                    entry.put("avgScore", Math.round(result.getDouble("avg_score") * 10000d) / 10000d);
                    return entry;
                });
        Long total = jdbc.queryForObject("SELECT COUNT(*) FROM radar_item", Long.class);
        Map<String, Object> view = new LinkedHashMap<>();
        view.put("total", total == null ? 0L : total);
        view.put("channels", channels);
        return view;
    }

    private RadarItem read(ResultSet result, int row) throws SQLException {
        return new RadarItem(
                result.getLong("id"),
                result.getLong("source_id"),
                result.getString("source_name"),
                result.getString("channel"),
                result.getString("external_id"),
                result.getString("title"),
                result.getString("summary"),
                result.getString("url"),
                result.getString("kind"),
                result.getString("category"),
                result.getString("obtain"),
                result.getInt("quality"),
                result.getString("trust_level"),
                result.getDouble("freshness"),
                result.getDouble("score"),
                splitFlags(result.getString("risk_flags")),
                result.getString("status"),
                instant(result, "published_at"),
                instant(result, "expires_at"),
                instant(result, "created_at"));
    }

    private static List<String> splitFlags(String raw) {
        if (raw == null || raw.isBlank()) return List.of();
        return Arrays.stream(raw.split(",")).map(String::strip).filter(value -> !value.isEmpty()).toList();
    }

    private static Instant instant(ResultSet result, String column) throws SQLException {
        Timestamp value = result.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
