package com.smartops.radar;

import org.springframework.stereotype.Service;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 资源雷达确定性评分。
 *
 * <p>全部规则可复现、不依赖模型；P2 接入 AI 语义定级时只允许覆盖 quality 与 category，
 * 不允许改变 status、风险标记与 URL 指纹。</p>
 *
 * <p>评分只影响排序，不构成事实判断：可信等级来自来源登记，可达性只按协议形态评估，
 * 真实可达性与活动有效性必须由证据链复核补足。</p>
 */
@Service
public class RadarScoreService {

    private static final Map<String, Double> TRUST_WEIGHT = Map.of(
            "L0", 1.00, "L1", 0.85, "L2", 0.65, "L3", 0.40, "L4", 0.20);

    /** 按条目的时效类型给半衰期，避免“开源项目”和“限时活动”用同一把尺子。 */
    private static final Map<String, Long> HALF_LIFE_HOURS = Map.of(
            "LIMITED_ACTIVITY", 24L,
            "DEAL", 72L,
            "NEWS", 48L,
            "FREE_QUOTA", 168L,
            "FREEBIE", 336L,
            "OPEN_SOURCE", 720L);

    private static final Set<String> SHORTENER_HOSTS = Set.of(
            "bit.ly", "t.cn", "tinyurl.com", "goo.gl", "is.gd", "ow.ly", "cutt.ly");

    /**
     * 评分结果。urlHash 用于入库去重，kind/category/obtain 是规则分流结果。
     */
    public record Grade(String kind, String category, String obtain, int quality, String trustLevel,
                        double freshness, double score, List<String> riskFlags, String urlHash) {
    }

    public Grade grade(CollectedResource resource, RadarSource source, Instant now) {
        String text = ((resource.title() == null ? "" : resource.title()) + " "
                + (resource.summary() == null ? "" : resource.summary())).toLowerCase(Locale.ROOT);
        String trust = source.trustLevel() != null && RadarSource.TRUST_LEVELS.contains(source.trustLevel())
                ? source.trustLevel() : "L4";
        String kind = kindOf(text);
        int quality = qualityOf(text, resource, trust);
        List<String> risks = riskFlagsOf(text, resource, trust);
        double freshness = freshnessOf(resource.publishedAt(), kind, now);
        double access = accessOf(resource.url());
        double trustWeight = TRUST_WEIGHT.getOrDefault(trust, 0.20);
        double riskPenalty = Math.min(1.0, risks.size() * 0.4);
        double score = 0.30 * freshness + 0.25 * trustWeight + 0.25 * (quality / 5.0)
                + 0.10 * access - 0.20 * riskPenalty;
        return new Grade(kind, source.channel(), obtainOf(text), quality, trust,
                round(freshness), round(clamp(score)), List.copyOf(risks), fingerprint(resource.url()));
    }

    /**
     * URL 指纹：去掉片段、末尾斜杠与跟踪参数后取 SHA-256，用于同一条目的跨来源去重。
     *
     * @throws IllegalArgumentException URL 缺少主机名或格式非法
     */
    public static String fingerprint(String url) {
        return sha256(normalizeUrl(url));
    }

    private static String normalizeUrl(String raw) {
        URI uri = URI.create(raw.strip());
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
        if (host.isEmpty()) throw new IllegalArgumentException("条目地址缺少主机名");
        String scheme = uri.getScheme() == null ? "https" : uri.getScheme().toLowerCase(Locale.ROOT);
        String path = uri.getPath() == null ? "" : uri.getPath();
        while (path.endsWith("/")) path = path.substring(0, path.length() - 1);
        String port = uri.getPort() > 0 ? ":" + uri.getPort() : "";
        return scheme + "://" + host + port + path + canonicalQuery(uri.getRawQuery());
    }

    private static String canonicalQuery(String rawQuery) {
        if (rawQuery == null || rawQuery.isBlank()) return "";
        List<String> kept = new ArrayList<>();
        for (String pair : rawQuery.split("&")) {
            String key = pair.contains("=") ? pair.substring(0, pair.indexOf('=')) : pair;
            String normalized = key.toLowerCase(Locale.ROOT);
            if (normalized.startsWith("utm_") || normalized.equals("ref")
                    || normalized.equals("spm") || normalized.equals("from")) {
                continue;
            }
            kept.add(pair);
        }
        return kept.isEmpty() ? "" : "?" + String.join("&", kept);
    }

    private static String kindOf(String text) {
        if (contains(text, "免费额度", "免费试用", "free tier", "free quota", "免费api", "试用额度", "credits")) {
            return "FREE_QUOTA";
        }
        if (contains(text, "限时", "limited time")) return "LIMITED_ACTIVITY";
        if (contains(text, "优惠", "折扣", "coupon", "promo", "deal", "黑五")) return "DEAL";
        if (contains(text, "开源", "open source", "github", "repository", "sdk")) return "OPEN_SOURCE";
        if (contains(text, "新闻", "announcement", "release notes", "changelog", "发布")) return "NEWS";
        return "FREEBIE";
    }

    private static String obtainOf(String text) {
        if (contains(text, "邀请码", "invite code", "邀请制")) return "INVITATION";
        if (contains(text, "信用卡", "credit card", "预授权")) return "CONDITIONAL";
        if (contains(text, "注册", "sign up", "register", "登录")) return "NEEDS_REGISTER";
        if (contains(text, "付费", "paid", "discount")) return "PAID_DISCOUNT";
        return "DIRECT";
    }

    private static int qualityOf(String text, CollectedResource resource, String trust) {
        int quality = 3;
        if (contains(text, "官方", "official")) quality++;
        if (resource.expiresAt() != null) quality++;
        if ("L0".equals(trust) || "L1".equals(trust)) quality++;
        if (contains(text, "疑似", "传闻", "未经证实", "rumor")) quality--;
        return Math.max(1, Math.min(5, quality));
    }

    private static List<String> riskFlagsOf(String text, CollectedResource resource, String trust) {
        Set<String> flags = new LinkedHashSet<>();
        if (contains(text, "信用卡", "credit card", "预授权")) flags.add("REQUIRES_CARD");
        if (contains(text, "邀请码", "invite code", "邀请制")) flags.add("INVITATION_ONLY");
        if (contains(text, "自动续费", "auto renew", "subscription")) flags.add("AUTO_RENEW");
        if (contains(text, "二次付费", "付费升级", "upgrade to paid")) flags.add("PAID_UPGRADE");
        if (SHORTENER_HOSTS.contains(hostOf(resource.url()))) flags.add("SHORT_LINK");
        if ("L3".equals(trust) || "L4".equals(trust)) flags.add("UNVERIFIED_SOURCE");
        String url = resource.url() == null ? "" : resource.url();
        if (!url.startsWith("http://") && !url.startsWith("https://")) flags.add("URL_NOT_HTTP");
        return new ArrayList<>(flags);
    }

    /** 发布时间未知时给 0.5 的中性值：既不伪装成新鲜，也不直接判死。 */
    private static double freshnessOf(Instant publishedAt, String kind, Instant now) {
        if (publishedAt == null) return 0.5;
        long hours = Duration.between(publishedAt, now).toHours();
        if (hours <= 0) return 1.0;
        long halfLife = HALF_LIFE_HOURS.getOrDefault(kind, 336L);
        return clamp(Math.exp(-hours / (double) halfLife));
    }

    /** 只按协议形态评估，不做联网探活。 */
    private static double accessOf(String url) {
        if (url == null) return 0.0;
        if (url.startsWith("https://")) return 1.0;
        if (url.startsWith("http://")) return 0.7;
        return 0.0;
    }

    private static String hostOf(String url) {
        if (url == null) return "";
        try {
            String host = URI.create(url.strip()).getHost();
            return host == null ? "" : host.toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException invalid) {
            return "";
        }
    }

    private static boolean contains(String text, String... needles) {
        for (String needle : needles) {
            if (text.contains(needle)) return true;
        }
        return false;
    }

    private static double clamp(double value) {
        return Math.max(0.0, Math.min(1.0, value));
    }

    private static double round(double value) {
        return Math.round(value * 10000d) / 10000d;
    }

    private static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 不可用", impossible);
        }
    }
}
