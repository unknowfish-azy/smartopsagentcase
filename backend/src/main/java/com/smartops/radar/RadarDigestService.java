package com.smartops.radar;

import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 资源雷达站内日报：把窗口内新增条目按审核状态汇总成 Markdown。
 *
 * <p>日报是给人看的汇总，不是事实背书：已核实与待审草案分区展示，
 * 待审部分在正文里明确标注「未经人工复核，不得作为事实引用」。
 * 内容只读 {@code radar_item}，不改状态、不写证据链；生成结果按用户落库，
 * 供前端与后续推送复用。</p>
 */
@Service
public class RadarDigestService {

    private static final ZoneId DISPLAY_ZONE = ZoneId.of("Asia/Shanghai");
    private static final DateTimeFormatter STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm").withZone(DISPLAY_ZONE);
    private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("yyyy-MM-dd").withZone(DISPLAY_ZONE);

    private static final int DEFAULT_HOURS = 24;
    private static final int MIN_HOURS = 1;
    private static final int MAX_HOURS = 168;
    private static final int MAX_ITEMS = 30;
    private static final int MAX_TITLE = 120;
    private static final int MAX_SUMMARY = 160;

    private static final Map<String, String> KIND_LABELS = Map.of(
            "FREE_QUOTA", "免费额度",
            "LIMITED_ACTIVITY", "限时活动",
            "DEAL", "优惠信息",
            "OPEN_SOURCE", "开源项目",
            "NEWS", "资讯动态",
            "FREEBIE", "福利资源");

    private static final Map<String, String> OBTAIN_LABELS = Map.of(
            "DIRECT", "直接获取",
            "NEEDS_REGISTER", "需注册",
            "INVITATION", "邀请制",
            "CONDITIONAL", "需满足条件",
            "PAID_DISCOUNT", "付费折扣");

    private static final Map<String, String> CHANNEL_LABELS = Map.of(
            "CLOUD", "云资源",
            "GPU", "算力",
            "MODEL", "模型",
            "DEVTOOL", "开发工具",
            "CERT", "认证考试",
            "PLUGIN", "插件",
            "HARDWARE", "硬件",
            "SECURITY", "安全");

    private final JdbcTemplate jdbc;
    private final RadarItemService items;

    public RadarDigestService(JdbcTemplate jdbc, RadarItemService items) {
        this.jdbc = jdbc;
        this.items = items;
    }

    /** 未落库的日报草稿；itemIds 是本窗口实际纳入的条目 id。 */
    public record DigestDraft(Instant periodStart, Instant periodEnd, String channel, String contentMd,
                              List<Long> itemIds, int verified, int drafts) {
    }

    /** 已落库的日报。 */
    public record DigestView(long id, String channel, Instant periodStart, Instant periodEnd,
                             String contentMd, List<Long> itemIds, Instant createdAt) {
    }

    /** 预览：只渲染不落库，方便前端先看效果。 */
    public DigestDraft preview(String channel, Integer hours) {
        return build(channel, hours);
    }

    @Transactional
    public DigestView generate(SessionUser actor, String channel, Integer hours) {
        if (actor == null) throw new BusinessException(401, "需要登录后生成日报");
        DigestDraft draft = build(channel, hours);
        String ids = draft.itemIds().stream().map(String::valueOf).collect(Collectors.joining(","));
        KeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO radar_digest(user_id,channel,period_start,period_end,content_md,item_ids)"
                            + " VALUES (?,?,?,?,?,?)", new String[]{"id"});
            statement.setLong(1, actor.id());
            statement.setString(2, draft.channel());
            statement.setTimestamp(3, Timestamp.from(draft.periodStart()));
            statement.setTimestamp(4, Timestamp.from(draft.periodEnd()));
            statement.setString(5, draft.contentMd());
            statement.setString(6, ids.isEmpty() ? null : ids);
            return statement;
        }, keys);
        Number key = keys.getKey();
        return require(actor.id(), key == null ? 0L : key.longValue());
    }

    public List<Map<String, Object>> list(long userId, Integer limit) {
        int size = limit == null ? 20 : Math.max(1, Math.min(100, limit));
        return jdbc.query("SELECT id,channel,period_start,period_end,created_at,item_ids FROM radar_digest"
                        + " WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (result, row) -> {
                    Map<String, Object> view = new LinkedHashMap<>();
                    view.put("id", result.getLong("id"));
                    view.put("channel", result.getString("channel"));
                    view.put("periodStart", instant(result, "period_start"));
                    view.put("periodEnd", instant(result, "period_end"));
                    view.put("createdAt", instant(result, "created_at"));
                    String ids = result.getString("item_ids");
                    view.put("itemCount", ids == null || ids.isBlank() ? 0 : ids.split(",").length);
                    return view;
                }, userId, size);
    }

    public DigestView require(long userId, long id) {
        List<DigestView> found = jdbc.query(
                "SELECT id,channel,period_start,period_end,content_md,item_ids,created_at"
                        + " FROM radar_digest WHERE id=? AND user_id=?",
                (result, row) -> new DigestView(
                        result.getLong("id"),
                        result.getString("channel"),
                        instant(result, "period_start"),
                        instant(result, "period_end"),
                        result.getString("content_md"),
                        parseIds(result.getString("item_ids")),
                        instant(result, "created_at")),
                id, userId);
        if (found.isEmpty()) throw new BusinessException(404, "日报不存在");
        return found.get(0);
    }

    private DigestDraft build(String channel, Integer hours) {
        String target = normalizeChannel(channel);
        int span = hours == null ? DEFAULT_HOURS : Math.max(MIN_HOURS, Math.min(MAX_HOURS, hours));
        Instant now = Instant.now();
        Instant from = now.minus(Duration.ofHours(span));
        List<RadarItem> found = items.window(from, now, target, MAX_ITEMS);
        int verified = (int) found.stream().filter(item -> "VERIFIED".equals(item.status())).count();
        List<Long> ids = found.stream().map(RadarItem::id).toList();
        return new DigestDraft(from, now, target, render(from, now, target, found, span), ids,
                verified, found.size() - verified);
    }

    private String normalizeChannel(String channel) {
        if (channel == null || channel.isBlank()) return null;
        String target = channel.strip().toUpperCase(Locale.ROOT);
        if (!RadarSource.CHANNELS.contains(target)) {
            throw new BusinessException(400, "不支持的资源域：" + channel);
        }
        return target;
    }

    /** 纯渲染，不触库，便于单测确定输出格式。 */
    String render(Instant periodStart, Instant periodEnd, String channel, List<RadarItem> found, int hours) {
        long verified = found.stream().filter(item -> "VERIFIED".equals(item.status())).count();
        StringBuilder md = new StringBuilder();
        md.append("# 资源雷达日报 · ").append(DATE.format(periodEnd)).append("\n\n");
        md.append("> 统计窗口：").append(STAMP.format(periodStart)).append(" → ").append(STAMP.format(periodEnd))
                .append("（Asia/Shanghai，近 ").append(hours).append(" 小时）\n");
        md.append("> 频道：").append(channel == null ? "全部" : channel + "（" + label(CHANNEL_LABELS, channel) + "）").append('\n');
        md.append("> 条目：共 ").append(found.size()).append(" 条，已核实 ").append(verified)
                .append(" 条，待审草案 ").append(found.size() - verified).append(" 条\n");
        md.append("> 说明：待审草案由采集器抓取并按规则初筛，未经人工复核，不得作为事实引用。\n\n");

        if (found.isEmpty()) {
            md.append("本期窗口内没有新增资源条目。\n");
            return md.toString();
        }

        appendSection(md, "已核实", found.stream().filter(item -> "VERIFIED".equals(item.status())).toList(), periodEnd);
        appendSection(md, "待审核草案", found.stream().filter(item -> !"VERIFIED".equals(item.status())).toList(), periodEnd);
        return md.toString();
    }

    private void appendSection(StringBuilder md, String title, List<RadarItem> section, Instant now) {
        if (section.isEmpty()) return;
        md.append("## ").append(title).append("（").append(section.size()).append("）\n\n");
        for (RadarItem item : section) {
            md.append("- ").append(link(item)).append('\n');
            md.append("  ").append(meta(item, now)).append('\n');
            String summary = truncate(plain(item.summary()), MAX_SUMMARY);
            if (!summary.isEmpty()) md.append("  ").append(summary).append('\n');
        }
        md.append('\n');
    }

    private String link(RadarItem item) {
        String title = truncate(escape(plain(item.title())), MAX_TITLE);
        String url = plain(item.url());
        if (url.startsWith("http://") || url.startsWith("https://")) {
            return "[" + title + "](<" + url + ">)";
        }
        // 不是 http(s) 时不做链接，避免把非法地址伪装成可点击资源
        return title;
    }

    private String meta(RadarItem item, Instant now) {
        List<String> parts = new ArrayList<>();
        parts.add("可信 " + blankTo(item.trustLevel(), "L4"));
        parts.add("评分 " + String.format(Locale.ROOT, "%.2f", item.score()));
        parts.add(label(KIND_LABELS, item.kind()));
        parts.add(label(OBTAIN_LABELS, item.obtain()));
        String remaining = remaining(item.expiresAt(), now);
        if (remaining != null) parts.add(remaining);
        if (!item.riskFlags().isEmpty()) parts.add("风险 " + String.join("/", item.riskFlags()));
        return String.join(" · ", parts);
    }

    private static String remaining(Instant expiresAt, Instant now) {
        if (expiresAt == null) return null;
        Duration left = Duration.between(now, expiresAt);
        if (left.isNegative()) return "已过期";
        long hours = left.toHours();
        if (hours >= 48) return "剩余 " + (hours / 24) + " 天";
        if (hours >= 1) return "剩余 " + hours + " 小时";
        return "剩余不足 1 小时";
    }

    private static String label(Map<String, String> labels, String value) {
        if (value == null || value.isBlank()) return "未知";
        return labels.getOrDefault(value, value);
    }

    private static String plain(String value) {
        if (value == null) return "";
        return value.replaceAll("\\s+", " ").strip();
    }

    private static String escape(String value) {
        return value.replace("[", "\\[").replace("]", "\\]");
    }

    private static String truncate(String value, int max) {
        if (value == null) return "";
        return value.length() <= max ? value : value.substring(0, max) + "…";
    }

    private static String blankTo(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private static List<Long> parseIds(String raw) {
        if (raw == null || raw.isBlank()) return List.of();
        List<Long> ids = new ArrayList<>();
        for (String value : raw.split(",")) {
            String trimmed = value.strip();
            if (trimmed.isEmpty()) continue;
            try {
                ids.add(Long.parseLong(trimmed));
            } catch (NumberFormatException ignored) {
                // 脏数据不阻断日报读取，跳过错值
            }
        }
        return List.copyOf(ids);
    }

    private static Instant instant(ResultSet result, String column) throws SQLException {
        Timestamp value = result.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }
}
