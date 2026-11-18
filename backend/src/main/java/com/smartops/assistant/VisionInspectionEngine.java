package com.smartops.assistant;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeoutException;

/**
 * 视觉巡检引擎：调用本地多模态模型（如 llava）分析上传图片。
 *
 * <p>与 {@link MiniAssistantEngine} 同处 assistant 包以复用包级私有的
 * {@link OllamaTransport}（直连回环地址、禁代理、响应限流）。
 * fail-closed 语义：smartops.vision.model 未配置（空串）时 analyze 直接 503，
 * 绝不猜测结论；模型解析失败时诚实降级（abnormal=null，原文截断），不编造判断。</p>
 */
@Service
public class VisionInspectionEngine {

    /** 解码后图片字节数上限：5MB，与前端上传限制一致。 */
    private static final int MAX_IMAGE_BYTES = 5 * 1024 * 1024;
    /** 解析失败降级时保留的原文长度上限。 */
    private static final int FALLBACK_SUMMARY_CHARS = 800;

    /** 固定中文提示词：要求模型只输出 JSON，字段固定，便于下游解析与事件落库。 */
    private static final String PROMPT = "你是智维Agent的视觉巡检助手。请分析这张图片，"
            + "识别其中的设备、界面、仪表、指示灯或异常痕迹。只输出一个 JSON 对象，"
            + "格式为 {\"abnormal\": true 或 false, \"summary\": \"一句话中文结论\", "
            + "\"issues\": [\"问题点1\", \"问题点2\"]}。abnormal 表示画面是否存在异常；"
            + "没有异常时 issues 返回空数组。不要输出 JSON 以外的任何文字。"
            + "无法确认时在 summary 中说明不确定，不要编造结论。";

    private final ObjectMapper mapper;
    private final URI baseUri;
    private final String model;
    private final OllamaTransport transport;
    private final Duration generationTimeout;

    @Autowired
    public VisionInspectionEngine(ObjectMapper mapper,
            @Value("${smartops.model.local.base-url:http://127.0.0.1:11434}") String baseUrl,
            @Value("${smartops.model.local.timeout-seconds:120}") int timeoutSeconds,
            @Value("${smartops.vision.model:}") String model) {
        this.mapper = mapper;
        this.baseUri = loopbackUri(baseUrl);
        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException("视觉巡检超时配置无效：smartops.model.local.timeout-seconds 必须为正数");
        }
        // 空串 = 未配置（fail-closed，analyze 时拒绝）；非空但非法 = 配置错误，启动即失败。
        if (model != null && !model.isBlank()) {
            if (model.length() > 128
                    || !model.matches("[a-zA-Z0-9][a-zA-Z0-9._-]*(?::[a-zA-Z0-9][a-zA-Z0-9._-]*)?")
                    || model.toLowerCase(Locale.ROOT).contains("cloud")) {
                throw new IllegalArgumentException("视觉巡检仅接受本地多模态模型名称，不允许云模型");
            }
        }
        this.model = model == null ? "" : model.strip();
        this.generationTimeout = Duration.ofSeconds(timeoutSeconds);
        this.transport = new OllamaTransport(Duration.ofSeconds(2));
    }

    /** 是否已配置本地视觉模型（决定前端配置徽标与 analyze 是否可用）。 */
    public boolean configured() {
        return !model.isBlank();
    }

    /** 已配置的模型名（未配置时为空串，不泄露任何额外信息）。 */
    public String model() {
        return model;
    }

    /**
     * 分析 base64 编码图片，返回结构化结论。
     *
     * <p>模型输出解析失败时诚实降级：abnormal=null、summary 为原文截断，
     * 不猜测异常与否；由纠察事件侧固定要求人工复核。</p>
     */
    public VisionAnalysis analyze(String imageBase64) {
        if (!configured()) {
            throw new BusinessException(503,
                    "视觉巡检未配置：请设置 smartops.vision.model 指向本地多模态模型（如 llava）");
        }
        String base64 = stripDataUriPrefix(imageBase64);
        if (base64 == null || base64.isBlank()) {
            throw new BusinessException(400, "图片数据不能为空");
        }
        byte[] image;
        try {
            image = Base64.getMimeDecoder().decode(base64);
        } catch (IllegalArgumentException failure) {
            throw new BusinessException(400, "图片数据不是有效的 base64 编码");
        }
        if (image.length == 0) {
            throw new BusinessException(400, "图片数据解码后为空");
        }
        if (image.length > MAX_IMAGE_BYTES) {
            throw new BusinessException(413, "图片过大：解码后不能超过 5MB");
        }

        // Ollama /api/chat 的 images 字段接受未经 data URI 前缀的纯 base64。
        List<Map<String, Object>> messages = new ArrayList<>();
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("role", "user");
        message.put("content", PROMPT);
        message.put("images", List.of(base64));
        messages.add(message);
        Map<String, Object> payload = Map.of(
                "model", model,
                "stream", false,
                "messages", messages,
                "options", Map.of("num_ctx", 4096, "num_predict", 300));

        String raw;
        try {
            HttpRequest request = HttpRequest.newBuilder(baseUri.resolve("/api/chat"))
                    .timeout(generationTimeout).header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(payload))).build();
            OllamaTransport.Response response = transport.send(request, generationTimeout, 1_048_576);
            if (response.code() == 404 || response.code() == 503) {
                throw new BusinessException(503, "视觉巡检本地模型或运行时不可用，请检查安装与运行状态");
            }
            if (response.code() < 200 || response.code() >= 300) {
                throw new BusinessException(502, "视觉巡检本地识别失败，请稍后重试");
            }
            JsonNode body = mapper.readTree(response.body());
            JsonNode content = body == null ? null : body.path("message").get("content");
            if (body == null || body.has("error") || content == null || !content.isTextual()
                    || content.asText().isBlank()) {
                throw new BusinessException(502, "视觉巡检未返回有效结论，请重试");
            }
            raw = content.asText();
        } catch (TimeoutException failure) {
            throw new BusinessException(503, "视觉巡检本地识别超时，请稍后重试");
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw new BusinessException(503, "视觉巡检请求已中断，请重试");
        } catch (OllamaTransport.UnavailableException failure) {
            throw new BusinessException(503, "视觉巡检本地运行时连接失败，请检查运行状态");
        } catch (IOException failure) {
            throw new BusinessException(502, "视觉巡检返回的数据无效，请重试");
        }
        return parse(raw);
    }

    /**
     * 解析模型输出：优先提取 JSON 结论；不是合法 JSON 或字段缺失时降级为
     * abnormal=null、summary=原文截断（诚实标注，不猜测异常与否）。
     */
    private VisionAnalysis parse(String raw) {
        Boolean abnormal = null;
        String summary = null;
        List<String> issues = new ArrayList<>();
        String text = raw.strip();
        String candidate = extractJsonObject(text);
        if (candidate != null) {
            try {
                JsonNode node = mapper.readTree(candidate);
                JsonNode abnormalNode = node.get("abnormal");
                if (abnormalNode != null && abnormalNode.isBoolean()) {
                    abnormal = abnormalNode.asBoolean();
                }
                JsonNode summaryNode = node.get("summary");
                if (summaryNode != null && summaryNode.isTextual() && !summaryNode.asText().isBlank()) {
                    summary = summaryNode.asText().strip();
                }
                JsonNode issuesNode = node.get("issues");
                if (issuesNode != null && issuesNode.isArray()) {
                    for (JsonNode issue : issuesNode) {
                        if (issue.isTextual() && !issue.asText().isBlank()) {
                            issues.add(issue.asText().strip());
                        }
                    }
                }
            } catch (IOException ignored) {
                // JSON 无法解析：走下方诚实降级路径。
            }
        }
        if (summary == null) {
            // 诚实降级：不猜 abnormal，保留模型原文（截断）供人工复核。
            abnormal = null;
            issues = List.of();
            summary = truncate(text, FALLBACK_SUMMARY_CHARS);
        }
        return new VisionAnalysis(abnormal, summary, List.copyOf(issues), model, raw);
    }

    /** 提取文本中第一段 {...}（模型偶尔会在 JSON 前后带说明文字）。 */
    private static String extractJsonObject(String text) {
        int start = text.indexOf('{');
        int end = text.lastIndexOf('}');
        if (start < 0 || end <= start) {
            return null;
        }
        return text.substring(start, end + 1);
    }

    /** 兼容前端 data URI：剥掉 data:image/...;base64, 前缀后取纯 base64。 */
    private static String stripDataUriPrefix(String value) {
        if (value == null) {
            return null;
        }
        String text = value.strip();
        int comma = text.indexOf(',');
        if (text.startsWith("data:") && comma >= 0) {
            return text.substring(comma + 1).strip();
        }
        return text;
    }

    private static String truncate(String text, int limit) {
        if (text == null) {
            return "";
        }
        int end = Math.min(text.length(), limit);
        if (end > 0 && end < text.length() && Character.isHighSurrogate(text.charAt(end - 1))) {
            end--;
        }
        return text.substring(0, end);
    }

    /** 仿照 MiniAssistantEngine：仅允许无凭据、无路径/查询的回环 HTTP 地址。 */
    private static URI loopbackUri(String value) {
        try {
            URI uri = URI.create(value);
            String host = uri.getHost();
            if (host == null || !("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))
                    || uri.getRawUserInfo() != null || uri.getRawQuery() != null || uri.getRawFragment() != null
                    || !(uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath()))
                    || uri.getPort() == 0 || uri.getPort() > 65_535) {
                throw new IllegalArgumentException();
            }
            if ("localhost".equalsIgnoreCase(host)) {
                host = "127.0.0.1";
            }
            boolean allowed = "::1".equals(host) || "[::1]".equals(host);
            if (host.matches("127(?:\\.(?:0|[1-9][0-9]{0,2})){3}")) {
                allowed = true;
                for (String octet : host.split("\\.")) {
                    if (Integer.parseInt(octet) > 255) {
                        allowed = false;
                    }
                }
            }
            if (!allowed) {
                throw new IllegalArgumentException();
            }
            return new URI(uri.getScheme().toLowerCase(Locale.ROOT), null, host, uri.getPort(), "/", null, null);
        } catch (Exception failure) {
            throw new IllegalArgumentException("视觉巡检地址仅允许无凭据、路径、查询参数的回环 HTTP 地址");
        }
    }

    /**
     * 视觉分析结论。raw 为模型原始输出（写入纠察证据，供人工复核）；
     * abnormal 为 null 表示模型输出无法结构化解析（诚实降级）。
     */
    public record VisionAnalysis(Boolean abnormal, String summary, List<String> issues,
            String model, String raw) {}
}
