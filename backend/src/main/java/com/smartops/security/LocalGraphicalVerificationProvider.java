package com.smartops.security;

import com.smartops.exception.BusinessException;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;

/**
 * 离线可用的本地图形点选验证供应商。
 *
 * <p>服务端生成一张 SVG 图形场景（若干带颜色和字符的图形），同时随机指定"要按顺序点中的图形"。
 * 图形坐标与正确答案只保存在本类的服务端存储（{@link #challenges}）中，任何下发给浏览器的数据
 * 都不包含坐标；前端只回报点击坐标，由 {@link #verify(String, String, List)} 做几何判定。</p>
 *
 * <p>不访问网络、不加载任何第三方脚本，因此默认配置（未配置 Turnstile 密钥）下即可工作。
 * 该 Bean 由 {@link HumanVerificationProviderConfig} 按配置装配，因此不加 {@code @Component}。</p>
 */
public class LocalGraphicalVerificationProvider implements HumanVerificationProvider {
    static final String PROVIDER = "local";
    /** 前端回报的点击凭据前缀：local.1.&lt;nonce&gt;.&lt;x&gt;.&lt;y&gt;[.&lt;x&gt;.&lt;y&gt;] */
    static final String TOKEN_PREFIX = "local.1.";
    static final int VIEW_WIDTH = 300;
    static final int VIEW_HEIGHT = 200;
    /** 点击容差（视图坐标）。必须小于图形最小中心间距的一半，否则一次点击可能同时落在两个图形里。 */
    static final int TOLERANCE = 18;
    static final int TARGET_RADIUS = 24;
    static final int MAX_ATTEMPTS = 3;
    static final int MAX_CLICKS = 8;
    /** 图形中心最小间距下限（TARGET_RADIUS * 2.2 = 52.8，视图坐标）：保证容差内的点击不会落得更靠近邻图形。 */
    static final double MIN_SPACING = TARGET_RADIUS * 2.2;
    /** 人类点击下限的默认值（毫秒）；可由 smartops.security.human-verification.min-response-ms 调整。 */
    static final long MIN_RESPONSE_MILLIS = 600;
    static final long TTL_SECONDS = 300;
    private static final int CAPACITY = 20000;
    private static final int DECOYS = 4;
    private static final String[] COLORS = { "红色", "蓝色", "绿色", "橙色", "紫色", "青色" };
    private static final String[] HEX = { "#e2453c", "#2f6fe0", "#2f9e5f", "#e88b1f", "#8b5cf6", "#0ea5b7" };
    private static final String[] LETTERS = { "A", "B", "C", "D", "E", "F", "G", "H", "K", "M", "P", "R", "S", "T", "X", "Z" };

    private final HumanVerificationSettings settings;
    private final Clock clock;
    private final Random random;
    private final Map<String, ChallengeState> challenges = new HashMap<>();

    public LocalGraphicalVerificationProvider(HumanVerificationSettings settings) {
        this(settings, Clock.systemUTC(), new Random());
    }

    LocalGraphicalVerificationProvider(HumanVerificationSettings settings, Clock clock, Random random) {
        this.settings = settings;
        this.clock = clock;
        this.random = random;
    }

    /**
     * 无状态的 Turnstile 式校验不适用于本地点选：必须携带 action 与点击坐标，
     * 因此这里统一返回失败，真实入口是 {@link #verify(String, String, List)}。
     */
    @Override
    public Result verify(String token) {
        return null;
    }

    /**
     * 为一次会话挑战生成图形场景并保存正确答案。同一个 nonce 重复调用返回同一个场景，
     * 因此刷新页面不会看到"换了一张图但提示变了"的不一致状态。
     */
    @Override
    public synchronized HumanVerificationProvider.Challenge issue(String nonce) {
        ChallengeState existing = live(nonce);
        if (existing != null) return existing.proof;
        Instant now = clock.instant();
        sweep(now);
        if (challenges.size() >= CAPACITY) throw new BusinessException(429, "验证请求过于频繁，请稍后重试");
        ChallengeState created = generate(nonce, now);
        challenges.put(nonce, created);
        return created.proof;
    }

    /**
     * 校验一次作答：按坐标做几何判定（含容差、次数与响应时间约束）。
     *
     * @param token  会话挑战 nonce
     * @param action 验证用途（register / admin_login / login），仅用于回填会话绑定字段
     * @param clicks 前端回报的点击坐标，顺序敏感
     * @return 成功时返回带 action 与 nonce 的结果；失败抛 {@link BusinessException}
     */
    @Override
    public synchronized Result verify(String token, String action, List<int[]> clicks) {
        if (token == null || token.isBlank() || action == null || clicks == null || clicks.isEmpty()) return null;
        // 允许直接传入下发给浏览器的一次性 token（带 local.1. 前缀）或裸 nonce，两种情况都收敛到 nonce。
        String nonce = token.startsWith(TOKEN_PREFIX) ? token.substring(TOKEN_PREFIX.length()) : token;
        if (nonce.isBlank()) return null;
        if (clicks.size() > MAX_CLICKS) throw new BusinessException(400, "点击数量超出限制");
        for (int[] point : clicks) {
            if (point == null || point.length != 2 || point[0] < 0 || point[0] > VIEW_WIDTH || point[1] < 0 || point[1] > VIEW_HEIGHT) {
                throw new BusinessException(400, "点击坐标无效，请重新验证");
            }
        }
        Instant now = clock.instant();
        sweep(now);
        ChallengeState state = challenges.get(nonce);
        if (state == null) throw new BusinessException(428, "验证已失效，请重新完成人机验证");
        if (state.consumed) throw new BusinessException(428, "验证已使用，请重新完成人机验证");
        // 无论判定成功与否都先消费，杜绝同一凭据重放；作答失败只能重新领取挑战。
        state.consumed = true;
        challenges.remove(nonce);
        if (!state.expires.isAfter(now)) throw new BusinessException(428, "验证已过期，请重新完成人机验证");
        if (now.toEpochMilli() - state.issuedAt.toEpochMilli() < settings.minResponseMillis) throw new BusinessException(428, "提交过快，请重新完成人机验证");
        if (state.attempts >= MAX_ATTEMPTS) throw new BusinessException(429, "验证尝试次数过多，请重新完成人机验证");
        state.attempts++;
        if (clicks.size() != state.targets.size()) throw failed(state, "请完整点击图中的 " + state.targets.size() + " 个图形");
        Set<Integer> used = new LinkedHashSet<>();
        for (int index = 0; index < clicks.size(); index++) {
            int[] point = clicks.get(index);
            int hit = hit(state, point[0], point[1]);
            if (hit < 0) throw failed(state, "没有点中正确图形，请重试");
            if (hit != state.targets.get(index)) throw failed(state, "点击顺序或目标不正确，请重试");
            // 一个图形只能算一次：重复点同一个图形不能冒充"依次点中多个目标"。
            if (!used.add(hit)) throw failed(state, "不能重复点击同一个图形，请重试");
        }
        return new Result(true, "", action, nonce, now);
    }

    private ChallengeState generate(String nonce, Instant now) {
        int shapeCount = DECOYS + 1 + random.nextInt(2);
        List<Shape> shapes = new ArrayList<>(shapeCount);
        Set<Integer> usedColors = new LinkedHashSet<>();
        Set<String> usedLetters = new LinkedHashSet<>();
        // 场景里颜色与字符都必须互不相同：这样"按颜色点选""按字符点选""按组合点选"三种提示都只有唯一答案。
        while (shapes.size() < shapeCount) {
            int color = random.nextInt(HEX.length);
            String letter = LETTERS[random.nextInt(LETTERS.length)];
            if (usedColors.contains(color) || usedLetters.contains(letter)) continue;
            int x = TARGET_RADIUS + 12 + random.nextInt(VIEW_WIDTH - 2 * (TARGET_RADIUS + 12));
            int y = TARGET_RADIUS + 12 + random.nextInt(VIEW_HEIGHT - 2 * (TARGET_RADIUS + 12));
            if (shapes.stream().anyMatch(other -> distance(other.x, other.y, x, y) < MIN_SPACING)) continue;
            usedColors.add(color);
            usedLetters.add(letter);
            shapes.add(new Shape(x, y, color, letter));
        }
        Collections.shuffle(shapes, random);
        // 目标定义：颜色+字符全匹配，或字符唯一，或颜色唯一，三种难度都要求看图作答。
        int mode = random.nextInt(3);
        List<Integer> targets;
        String prompt;
        if (mode == 0) {
            int pick = random.nextInt(shapes.size());
            Shape target = shapes.get(pick);
            targets = List.of(pick);
            prompt = "请点击图中的 " + HEX[target.color] + " " + target.letter;
        } else if (mode == 1) {            List<Integer> picks = firstDistinct(shapes, true, 1 + random.nextInt(2));
            targets = List.copyOf(picks);
            prompt = "请依次点击图中的 " + join(picks.stream().map(index -> shapes.get(index).letter).toList());
        } else {
            List<Integer> picks = firstDistinct(shapes, false, 1 + random.nextInt(2));
            targets = List.copyOf(picks);
            prompt = "请依次点击图中的 " + join(picks.stream().map(index -> COLORS[shapes.get(index).color] + "图形").toList());
        }
        String svg = render(shapes);
        String proof = TOKEN_PREFIX + nonce;
        return new ChallengeState(shapes, targets, prompt, svg, proof, now, now.plusSeconds(TTL_SECONDS));
    }

    /** 按字符（byLetter=true）或按颜色取前 limit 个目标；生成的组合保证判别键互不重复。 */
    private static List<Integer> firstDistinct(List<Shape> shapes, boolean byLetter, int limit) {
        Map<String, Integer> seen = new HashMap<>();
        List<Integer> picks = new ArrayList<>(limit);
        for (int index = 0; index < shapes.size() && picks.size() < limit; index++) {
            Shape shape = shapes.get(index);
            if (seen.putIfAbsent(byLetter ? shape.letter : Integer.toString(shape.color), index) == null) picks.add(index);
        }
        return picks;
    }

    private static String join(List<String> items) {
        StringBuilder text = new StringBuilder();
        for (int index = 0; index < items.size(); index++) {
            if (index > 0) text.append('、');
            text.append(items.get(index));
        }
        return text.toString();
    }

    private String render(List<Shape> shapes) {
        StringBuilder svg = new StringBuilder(1200);
        svg.append("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 ").append(VIEW_WIDTH).append(' ').append(VIEW_HEIGHT)
                .append("\" role=\"img\" aria-label=\"人机验证图形\">");
        svg.append("<rect width=\"").append(VIEW_WIDTH).append("\" height=\"").append(VIEW_HEIGHT).append("\" fill=\"#0f2231\"/>");
        for (int index = 0; index < 6; index++) {
            svg.append("<line x1=\"").append(random.nextInt(VIEW_WIDTH)).append("\" y1=\"").append(random.nextInt(VIEW_HEIGHT))
                    .append("\" x2=\"").append(random.nextInt(VIEW_WIDTH)).append("\" y2=\"").append(random.nextInt(VIEW_HEIGHT))
                    .append("\" stroke=\"#24455c\" stroke-width=\"1\" opacity=\".55\"/>");
        }
        for (Shape shape : shapes) {
            String fill = HEX[shape.color];
            switch (shape.kind()) {
                case 0 -> svg.append("<circle cx=\"").append(shape.x).append("\" cy=\"").append(shape.y).append("\" r=\"")
                        .append(TARGET_RADIUS).append("\" fill=\"").append(fill).append("\"/>");
                case 1 -> svg.append("<rect x=\"").append(shape.x - TARGET_RADIUS).append("\" y=\"").append(shape.y - TARGET_RADIUS)
                        .append("\" width=\"").append(TARGET_RADIUS * 2).append("\" height=\"").append(TARGET_RADIUS * 2)
                        .append("\" rx=\"6\" fill=\"").append(fill).append("\"/>");
                case 2 -> svg.append("<polygon points=\"").append(shape.x).append(',').append(shape.y - TARGET_RADIUS).append(' ')
                        .append(shape.x + TARGET_RADIUS).append(',').append(shape.y).append(' ')
                        .append(shape.x).append(',').append(shape.y + TARGET_RADIUS).append(' ')
                        .append(shape.x - TARGET_RADIUS).append(',').append(shape.y).append("\" fill=\"").append(fill).append("\"/>");
                default -> svg.append("<polygon points=\"").append(shape.x).append(',').append(shape.y - TARGET_RADIUS).append(' ')
                        .append(shape.x + TARGET_RADIUS).append(',').append(shape.y + TARGET_RADIUS).append(' ')
                        .append(shape.x - TARGET_RADIUS).append(',').append(shape.y + TARGET_RADIUS).append("\" fill=\"").append(fill).append("\"/>");
            }
            svg.append("<text x=\"").append(shape.x).append("\" y=\"").append(shape.y)
                    .append("\" fill=\"#ffffff\" font-family=\"system-ui,sans-serif\" font-size=\"20\" font-weight=\"700\"")
                    .append(" text-anchor=\"middle\" dominant-baseline=\"central\">").append(shape.letter).append("</text>");
        }
        return svg.append("</svg>").toString();
    }

    /** 命中判定：返回容差范围内最近的图形下标，未命中返回 -1。 */
    private static int hit(ChallengeState state, int x, int y) {
        int best = -1;
        double bestDistance = Double.MAX_VALUE;
        for (int index = 0; index < state.shapes.size(); index++) {
            Shape shape = state.shapes.get(index);
            double distance = distance(shape.x, shape.y, x, y);
            if (distance <= TOLERANCE && distance < bestDistance) {
                bestDistance = distance;
                best = index;
            }
        }
        return best;
    }

    private static double distance(int x1, int y1, int x2, int y2) {
        return Math.hypot(x1 - (double) x2, y1 - (double) y2);
    }

    private static BusinessException failed(ChallengeState state, String message) {
        int remaining = MAX_ATTEMPTS - state.attempts;
        return new BusinessException(428, remaining > 0 ? message + "（本次挑战还剩 " + remaining + " 次机会）" : message);
    }

    private ChallengeState live(String nonce) {
        if (nonce == null || nonce.isBlank()) return null;
        ChallengeState state = challenges.get(nonce);
        if (state == null || state.consumed) return null;
        Instant now = clock.instant();
        if (!state.expires.isAfter(now)) {
            challenges.remove(nonce);
            return null;
        }
        return state;
    }

    private void sweep(Instant now) {
        challenges.entrySet().removeIf(entry -> entry.getValue().consumed || !entry.getValue().expires.isAfter(now));
    }

    private static final class ChallengeState {
        private final List<Shape> shapes;
        private final List<Integer> targets;
        private final HumanVerificationProvider.Challenge proof;
        private final Instant issuedAt;
        private final Instant expires;
        private int attempts;
        private boolean consumed;

        private ChallengeState(List<Shape> shapes, List<Integer> targets, String prompt, String svg, String token,
                Instant issuedAt, Instant expires) {
            this.shapes = shapes;
            this.targets = targets;
            this.proof = new HumanVerificationProvider.Challenge(PROVIDER, token, prompt, targets.size(), TOLERANCE, svg);
            this.issuedAt = issuedAt;
            this.expires = expires;
        }
    }

    private record Shape(int x, int y, int color, String letter) {
        private int kind() { return (x + y + color + letter.charAt(0)) & 3; }
    }
}
