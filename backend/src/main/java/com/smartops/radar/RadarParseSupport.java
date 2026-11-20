package com.smartops.radar;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

/**
 * 采集器的文本与时间解析兜底。
 *
 * <p>解析失败一律返回 null，由评分环节按“未知时间”降级，不用当前时间顶替，
 * 否则会把老内容伪装成新鲜内容。</p>
 */
final class RadarParseSupport {

    private RadarParseSupport() {
    }

    /** 支持 RFC 1123（RSS pubDate）、ISO 偏移时间与 UTC 瞬时时间。 */
    static Instant instant(String value) {
        if (value == null || value.isBlank()) return null;
        String text = value.strip();
        try {
            return ZonedDateTime.parse(text, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant();
        } catch (DateTimeParseException ignored) {
            // 继续尝试下一种格式
        }
        try {
            return OffsetDateTime.parse(text, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant();
        } catch (DateTimeParseException ignored) {
            // 继续尝试下一种格式
        }
        try {
            return Instant.parse(text);
        } catch (DateTimeParseException ignored) {
            return null;
        }
    }

    /** 去掉 HTML 标签与常见实体，压缩空白并截断。 */
    static String plainText(String value, int max) {
        if (value == null) return null;
        // 先解实体再去标签：RSS 常把正文转义成 &lt;p&gt;，反序会留下裸标签文本。
        String text = value.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", "\"")
                .replace("&#39;", "'")
                .replace("&#x27;", "'")
                .replaceAll("<[^>]+>", " ");
        text = text.replaceAll("\\s+", " ").strip();
        if (text.isEmpty()) return null;
        return text.length() <= max ? text : text.substring(0, max);
    }
}
