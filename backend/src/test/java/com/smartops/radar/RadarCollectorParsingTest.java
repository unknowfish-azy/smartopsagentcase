package com.smartops.radar;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * 三个采集器的解析契约：字段映射、时间解析、去重指纹。
 * 不联网，HTTP 响应由 mock 提供，避免把外部站点可用性带进测试。
 */
class RadarCollectorParsingTest {

    private static RadarSource source(String type, String url) {
        return new RadarSource(1L, "测试来源", type, url, "CLOUD", "L3", true, 360,
                null, null, null, null, 1L, null, null);
    }

    @Test
    void rssParsesItemsAndRfc1123Date() throws IOException {
        RadarHttpClient http = mock(RadarHttpClient.class);
        when(http.get(anyString(), anyString(), any())).thenReturn("""
                <?xml version="1.0" encoding="UTF-8"?>
                <rss version="2.0"><channel><title>福利</title>
                  <item>
                    <title>免费 GPU 额度</title>
                    <link>https://example.com/a</link>
                    <description>&lt;p&gt;限时&lt;b&gt;免费&lt;/b&gt;领取&lt;/p&gt;</description>
                    <pubDate>Tue, 10 Jun 2025 09:00:00 GMT</pubDate>
                    <guid>a-1</guid>
                  </item>
                </channel></rss>
                """);

        List<CollectedResource> resources = new RssCollector(http).collect(source("RSS", "https://example.com/feed"));

        assertEquals(1, resources.size());
        CollectedResource item = resources.get(0);
        assertEquals("免费 GPU 额度", item.title());
        assertEquals("https://example.com/a", item.url());
        assertEquals("限时 免费 领取", item.summary());
        assertEquals(Instant.parse("2025-06-10T09:00:00Z"), item.publishedAt());
        assertNull(item.expiresAt());
    }

    @Test
    void rssParsesAtomEntries() throws IOException {
        RadarHttpClient http = mock(RadarHttpClient.class);
        when(http.get(anyString(), anyString(), any())).thenReturn("""
                <?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                  <entry>
                    <title>Release 2.0</title>
                    <link rel="alternate" href="https://example.com/r2"/>
                    <summary>新增免费额度</summary>
                    <published>2025-06-10T09:00:00Z</published>
                    <id>tag:r2</id>
                  </entry>
                </feed>
                """);

        List<CollectedResource> resources = new RssCollector(http).collect(source("RSS", "https://example.com/atom"));

        assertEquals(1, resources.size());
        assertEquals("Release 2.0", resources.get(0).title());
        assertEquals("https://example.com/r2", resources.get(0).url());
        assertEquals(Instant.parse("2025-06-10T09:00:00Z"), resources.get(0).publishedAt());
    }

    @Test
    void jsonApiParsesNestedArrayAndEpochTime() throws IOException {
        RadarHttpClient http = mock(RadarHttpClient.class);
        when(http.get(anyString(), anyString(), any())).thenReturn("""
                {"code":0,"data":{"items":[
                  {"name":"GPU 试用","url":"https://example.com/g","description":"7 天",
                   "created_at":1718000000,"expires_at":"2025-07-01T00:00:00Z"},
                  {"name":"缺少地址"}
                ]}}
                """);

        List<CollectedResource> resources =
                new JsonApiCollector(http, new ObjectMapper()).collect(source("JSON_API", "https://example.com/api"));

        assertEquals(1, resources.size());
        assertEquals("GPU 试用", resources.get(0).title());
        assertEquals(Instant.ofEpochSecond(1718000000), resources.get(0).publishedAt());
        assertEquals(Instant.parse("2025-07-01T00:00:00Z"), resources.get(0).expiresAt());
    }

    @Test
    void githubParsesReleasesAndSkipsDrafts() throws IOException {
        RadarHttpClient http = mock(RadarHttpClient.class);
        when(http.get(anyString(), anyString(), any())).thenReturn("""
                [
                  {"id":11,"tag_name":"v1.0.0","name":"v1.0.0",
                   "html_url":"https://github.com/acme/tool/releases/tag/v1.0.0",
                   "body":"首个版本","published_at":"2025-06-10T09:00:00Z","draft":false},
                  {"id":12,"tag_name":"v1.1.0","name":"v1.1.0",
                   "html_url":"https://github.com/acme/tool/releases/tag/v1.1.0","draft":true}
                ]
                """);

        List<CollectedResource> resources =
                new GithubCollector(http, new ObjectMapper()).collect(source("GITHUB", "https://github.com/acme/tool"));

        assertEquals(1, resources.size());
        assertEquals("v1.0.0", resources.get(0).title());
        assertEquals("https://github.com/acme/tool/releases/tag/v1.0.0", resources.get(0).url());
    }

    @Test
    void fingerprintIgnoresTrackingParamsAndTrailingSlash() {
        assertEquals(
                RadarScoreService.fingerprint("https://Example.com/a/"),
                RadarScoreService.fingerprint("https://example.com/a?utm_source=x"));
    }
}
