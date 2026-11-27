package com.smartops.ensplab;

import org.springframework.stereotype.Component;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilderFactory;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 解析 eNSP 的 .topo（XML）文件，输出前端可直接渲染的节点与连线数据。
 *
 * <p>eNSP 拓扑由 devices/dev（含 slot/interface 端口列表）与 lines/line
 * （含 interfacePair 物理接口对）组成，坐标 cx/cy 用于还原画布布局。</p>
 */
@Component
public class TopologyParser {

    private final EnspKnowledgeBase kb;

    public TopologyParser(EnspKnowledgeBase kb) {
        this.kb = kb;
    }

    public TopologyGraph parse(String topologyId) {
        EnspModels.TopologyMeta meta = kb.manifest().topologies().stream()
                .filter(t -> t.id().equals(topologyId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("TOPOLOGY_NOT_FOUND: " + topologyId));
        return parseXml(kb.topologyStream(topologyId), meta);
    }

    /** 解析外部提交的 XML（粘贴/上传场景）。 */
    public TopologyGraph parseRaw(String xml, String topologyId) {
        try (InputStream in = new java.io.ByteArrayInputStream(xml.getBytes(java.nio.charset.StandardCharsets.UTF_8))) {
            return parseDocument(in, new EnspModels.TopologyMeta(
                    topologyId == null ? "custom" : topologyId, "自定义拓扑", null, "", ""));
        } catch (IllegalArgumentException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new IllegalArgumentException("TOPOLOGY_XML_INVALID: " + ex.getMessage(), ex);
        }
    }

    private TopologyGraph parseXml(InputStream in, EnspModels.TopologyMeta meta) {
        try {
            return parseDocument(in, meta);
        } catch (RuntimeException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new IllegalStateException("TOPOLOGY_PARSE_FAILED: " + meta.id(), ex);
        }
    }

    private TopologyGraph parseDocument(InputStream in, EnspModels.TopologyMeta meta) throws Exception {
        var factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(false);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        var builder = factory.newDocumentBuilder();
        Document doc = builder.parse(new org.xml.sax.InputSource(
                new java.io.StringReader(normalizeXml(in))));

        Map<String, DeviceNode> nodesById = new LinkedHashMap<>();
        List<TopologyGraph> ignored = new ArrayList<>();
        NodeList devs = doc.getElementsByTagName("dev");
        for (int i = 0; i < devs.getLength(); i++) {
            Element dev = (Element) devs.item(i);
            List<String> ports = readPorts(dev);
            DeviceNode node = new DeviceNode(
                    attr(dev, "id"), attr(dev, "name"), attr(dev, "model"),
                    doubleOr(dev.getAttribute("cx"), 0), doubleOr(dev.getAttribute("cy"), 0),
                    ports);
            nodesById.put(node.id(), node);
        }

        List<Link> links = new ArrayList<>();
        NodeList lines = doc.getElementsByTagName("line");
        for (int i = 0; i < lines.getLength(); i++) {
            Element line = (Element) lines.item(i);
            Element pair = firstChild(line, "interfacePair");
            if (pair == null) {
                continue;
            }
            String srcId = attr(line, "srcDeviceID");
            String dstId = attr(line, "destDeviceID");
            DeviceNode src = nodesById.get(srcId);
            DeviceNode dst = nodesById.get(dstId);
            links.add(new Link(srcId, src == null ? null : src.name(),
                    dstId, dst == null ? null : dst.name(),
                    portLabel(src, intOr(pair.getAttribute("srcIndex"), -1)),
                    intOr(pair.getAttribute("srcIndex"), -1),
                    portLabel(dst, intOr(pair.getAttribute("tarIndex"), -1)),
                    intOr(pair.getAttribute("tarIndex"), -1),
                    attr(pair, "lineName")));
        }

        List<TextTip> tips = new ArrayList<>();
        NodeList tipNodes = doc.getElementsByTagName("txttip");
        for (int i = 0; i < tipNodes.getLength(); i++) {
            Element tip = (Element) tipNodes.item(i);
            tips.add(new TextTip(doubleOr(tip.getAttribute("left"), 0), doubleOr(tip.getAttribute("top"), 0),
                    attr(tip, "content")));
        }
        return new TopologyGraph(meta.id(), meta.title(), meta.project(), meta.path(),
                List.copyOf(nodesById.values()), links, tips);
    }

    /**
     * eNSP 导出的 .topo 声明为 {@code encoding="UNICODE"}，这不是合法的 XML 编码名，
     * 直接交给 DOM 解析会报「前言中不允许有内容」。这里按字节读取后强制改写声明，
     * 并以字符串方式解析，避免解析器按错误编码二次解码。
     */
    private static String normalizeXml(InputStream in) throws java.io.IOException {
        byte[] bytes = in.readAllBytes();
        java.nio.charset.Charset charset = detectCharset(bytes);
        String xml = new String(bytes, charset);
        return xml.replaceFirst("(?is)<\\?xml[^>]*\\?>", "<?xml version=\"1.0\" encoding=\"UTF-8\"?>");
    }

    private static java.nio.charset.Charset detectCharset(byte[] bytes) {
        if (bytes.length >= 3 && (bytes[0] & 0xFF) == 0xEF && (bytes[1] & 0xFF) == 0xBB
                && (bytes[2] & 0xFF) == 0xBF) {
            return java.nio.charset.StandardCharsets.UTF_8;
        }
        if (bytes.length >= 2 && ((bytes[0] & 0xFF) == 0xFF && (bytes[1] & 0xFF) == 0xFE
                || (bytes[0] & 0xFF) == 0xFE && (bytes[1] & 0xFF) == 0xFF)) {
            return java.nio.charset.StandardCharsets.UTF_16;
        }
        try {
            java.nio.charset.StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                    .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                    .decode(java.nio.ByteBuffer.wrap(bytes));
            return java.nio.charset.StandardCharsets.UTF_8;
        } catch (java.nio.charset.CharacterCodingException ex) {
            return java.nio.charset.Charset.forName("GBK");
        }
    }

    private List<String> readPorts(Element dev) {        List<String> ports = new ArrayList<>();
        NodeList slots = dev.getElementsByTagName("slot");
        for (int s = 0; s < slots.getLength(); s++) {
            Element slot = (Element) slots.item(s);
            NodeList interfaces = slot.getElementsByTagName("interface");
            for (int j = 0; j < interfaces.getLength(); j++) {
                Element iface = (Element) interfaces.item(j);
                String type = attr(iface, "sztype");
                int count = Math.max(1, intOr(iface.getAttribute("count"), 1));
                for (int k = 0; k < count; k++) {
                    ports.add(labelOf(type, k));
                }
            }
        }
        return ports;
    }

    private static String labelOf(String sztype, int index) {
        return switch (sztype) {
            case "GE" -> "GigabitEthernet 0/0/" + index;
            case "FE" -> "FastEthernet 0/0/" + index;
            case "Serial" -> "Serial 2/0/" + index;
            default -> sztype + " 0/0/" + index;
        };
    }

    private static String portLabel(DeviceNode node, int index) {
        if (node == null || index < 0 || index >= node.ports().size()) {
            return "?";
        }
        return node.ports().get(index);
    }

    private static Element firstChild(Element parent, String tag) {
        NodeList nodes = parent.getElementsByTagName(tag);
        return nodes.getLength() == 0 ? null : (Element) nodes.item(0);
    }

    private static String attr(Element el, String name) {
        String value = el.getAttribute(name);
        return value == null ? "" : value;
    }

    private static int intOr(String raw, int fallback) {
        try {
            return Integer.parseInt(raw.trim());
        } catch (NumberFormatException ex) {
            return fallback;
        }
    }

    private static double doubleOr(String raw, double fallback) {
        try {
            return Double.parseDouble(raw.trim());
        } catch (NumberFormatException ex) {
            return fallback;
        }
    }

    /** 解析后的拓扑图，直接作为前端渲染契约。 */
    public record TopologyGraph(String id, String title, Integer project, String path,
                                List<DeviceNode> devices, List<Link> links,
                                List<TextTip> tips) {
    }

    public record DeviceNode(String id, String name, String model,
                             double x, double y, List<String> ports) {
    }

    public record Link(String srcDeviceId, String srcName, String dstDeviceId, String dstName,
                       String srcPort, int srcIndex, String dstPort, int dstIndex,
                       String lineName) {
    }

    public record TextTip(double left, double top, String content) {
    }
}
