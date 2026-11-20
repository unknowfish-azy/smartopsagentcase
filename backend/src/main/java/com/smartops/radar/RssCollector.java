package com.smartops.radar;

import org.springframework.stereotype.Component;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

/**
 * RSS 2.0 / Atom 采集器。
 *
 * <p>只做解析，不补造字段：发布时间解析不出来就留空，截止时间没有就留空。
 * XML 解析禁用 DOCTYPE 与外部实体，避免把采集源当成 XXE 入口。</p>
 */
@Component
public class RssCollector implements RadarCollector {

    private static final int MAX_ITEMS = 100;
    private static final int MAX_SUMMARY = 2000;
    private static final String ACCEPT =
            "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8";

    private final RadarHttpClient http;

    public RssCollector(RadarHttpClient http) {
        this.http = http;
    }

    @Override
    public String type() {
        return "RSS";
    }

    @Override
    public List<CollectedResource> collect(RadarSource source) {
        String body;
        try {
            body = http.get(source.url(), ACCEPT, null);
        } catch (IOException failure) {
            throw new IllegalStateException("RSS 抓取失败：" + failure.getMessage(), failure);
        }
        Document document = parse(body);
        NodeList items = document.getElementsByTagName("item");
        boolean atom = items.getLength() == 0;
        if (atom) items = document.getElementsByTagName("entry");

        List<CollectedResource> resources = new ArrayList<>();
        for (int index = 0; index < items.getLength() && resources.size() < MAX_ITEMS; index++) {
            Element item = (Element) items.item(index);
            String title = childText(item, "title");
            String link = atom ? atomLink(item) : firstNonNull(childText(item, "link"), childText(item, "guid"));
            if (title == null || link == null) continue;
            String summary = atom
                    ? firstNonNull(childText(item, "summary"), childText(item, "content"))
                    : firstNonNull(childText(item, "description"), childText(item, "content:encoded"));
            String published = atom
                    ? firstNonNull(childText(item, "published"), childText(item, "updated"))
                    : childText(item, "pubDate");
            resources.add(new CollectedResource(
                    firstNonNull(childText(item, "guid"), childText(item, "id")),
                    title,
                    RadarParseSupport.plainText(summary, MAX_SUMMARY),
                    link,
                    RadarParseSupport.instant(published),
                    null));
        }
        return resources;
    }

    private static Document parse(String body) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);
            factory.setNamespaceAware(false);
            return factory.newDocumentBuilder().parse(new InputSource(new StringReader(body)));
        } catch (ParserConfigurationException | SAXException | IOException failure) {
            throw new IllegalStateException("RSS 解析失败：" + failure.getMessage(), failure);
        }
    }

    private static String childText(Element parent, String tag) {
        NodeList nodes = parent.getElementsByTagName(tag);
        if (nodes.getLength() == 0) return null;
        String value = nodes.item(0).getTextContent();
        return value == null || value.isBlank() ? null : value.strip();
    }

    /** Atom 的 link 是属性；优先取 rel="alternate" 或未声明 rel 的那一条。 */
    private static String atomLink(Element item) {
        NodeList links = item.getElementsByTagName("link");
        String fallback = null;
        for (int index = 0; index < links.getLength(); index++) {
            Element link = (Element) links.item(index);
            String href = link.getAttribute("href");
            if (href == null || href.isBlank()) continue;
            String rel = link.getAttribute("rel");
            if (rel == null || rel.isBlank() || "alternate".equalsIgnoreCase(rel)) return href.strip();
            if (fallback == null) fallback = href.strip();
        }
        return fallback;
    }

    private static String firstNonNull(String first, String second) {
        return first != null && !first.isBlank() ? first : second;
    }
}
