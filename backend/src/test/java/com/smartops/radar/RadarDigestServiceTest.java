package com.smartops.radar;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

/**
 * 日报渲染契约：分区、状态标注、链接与剩余时间。
 * 只测纯渲染，不触库、不联网。
 */
class RadarDigestServiceTest {

    private final RadarDigestService service = new RadarDigestService(
            mock(JdbcTemplate.class), mock(RadarItemService.class));

    private static RadarItem item(long id, String status, String title, String url, double score,
                                  String trust, String kind, String obtain, List<String> risks, Instant expiresAt) {
        return new RadarItem(id, 1L, "测试来源", "GPU", "ext-" + id, title, "摘要 " + id, url,
                kind, "GPU", obtain, 4, trust, 1.0, score, risks, status, null, expiresAt, null);
    }

    @Test
    void emptyWindowStatesNoNewItems() {
        Instant now = Instant.parse("2026-11-18T00:00:00Z");
        String md = service.render(now.minusSeconds(86400), now, null, List.of(), 24);

        assertTrue(md.contains("频道：全部"));
        assertTrue(md.contains("共 0 条，已核实 0 条，待审草案 0 条"));
        assertTrue(md.contains("本期窗口内没有新增资源条目。"));
    }

    @Test
    void verifiedAndDraftAreSeparated() {
        Instant now = Instant.parse("2026-11-18T00:00:00Z");
        Instant expires = now.plusSeconds(72 * 3600);
        String md = service.render(now.minusSeconds(86400), now, "GPU", List.of(
                item(1, "VERIFIED", "官方免费额度", "https://example.com/gpu", 0.9,
                        "L1", "FREE_QUOTA", "NEEDS_REGISTER", List.of(), expires),
                item(2, "DRAFT", "转载福利", "https://example.com/b", 0.4,
                        "L4", "FREEBIE", "INVITATION", List.of("UNVERIFIED_SOURCE"), null)), 24);

        assertTrue(md.contains("频道：GPU（算力）"));
        assertTrue(md.contains("## 已核实（1）"));
        assertTrue(md.contains("## 待审核草案（1）"));
        assertTrue(md.contains("已核实 1 条，待审草案 1 条"));
        assertTrue(md.contains("[官方免费额度](<https://example.com/gpu>)"));
        assertTrue(md.contains("可信 L1 · 评分 0.90 · 免费额度 · 需注册 · 剩余 3 天"));
        assertTrue(md.contains("风险 UNVERIFIED_SOURCE"));
        assertTrue(md.indexOf("已核实") < md.indexOf("转载福利"));
    }

    @Test
    void markdownSpecialCharactersAreEscaped() {
        Instant now = Instant.parse("2026-11-18T00:00:00Z");
        String md = service.render(now.minusSeconds(86400), now, null, List.of(
                item(3, "DRAFT", "[限时] 免费", "https://example.com/c", 0.5,
                        "L3", "LIMITED_ACTIVITY", "DIRECT", List.of(), now.plusSeconds(5 * 3600))), 24);

        assertTrue(md.contains("- [\\[限时\\] 免费](<https://example.com/c>)"), md);
        assertTrue(md.contains("剩余 5 小时"), md);
        assertFalse(md.contains("已过期"), md);
    }

    @Test
    void nonHttpUrlIsNotRenderedAsLink() {
        Instant now = Instant.parse("2026-11-18T00:00:00Z");
        String md = service.render(now.minusSeconds(86400), now, null, List.of(
                item(4, "DRAFT", "无协议地址", "ftp://example.com/d", 0.1,
                        "L4", "FREEBIE", "DIRECT", List.of("URL_NOT_HTTP"), null)), 24);

        assertTrue(md.contains("- 无协议地址"));
        assertFalse(md.contains("](<ftp://example.com/d>)"));
    }
}
