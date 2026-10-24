package com.smartops.security;

import com.smartops.exception.BusinessException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Service
public class HumanVerificationService {
    private static final Set<String> ACTIONS = Set.of("login", "admin_login", "register");
    private static final String CHALLENGE = HumanVerificationService.class.getName() + ".";
    private final HumanVerificationSettings settings;
    private final HumanVerificationProvider provider;
    private final Clock clock;
    private final AccountAttemptLimiter requests = new AccountAttemptLimiter();
    private final Map<String, FailureWindow> failures = new HashMap<>();
    private final Map<String, Integer> inFlight = new HashMap<>();
    private Instant saturatedUntil = Instant.MIN;

    @Autowired
    public HumanVerificationService(HumanVerificationSettings settings, HumanVerificationProvider provider) {
        this(settings, provider, Clock.systemUTC());
    }

    HumanVerificationService(HumanVerificationSettings settings, HumanVerificationProvider provider, Clock clock) {
        this.settings = settings;
        this.provider = provider;
        this.clock = clock;
    }

    public String loginAction(String portal) {
        if (portal == null || "user".equals(portal)) return "login";
        if ("admin".equals(portal)) return "admin_login";
        throw new BusinessException(400, "登录入口无效");
    }

    public Policy policy(String action, HttpServletRequest request) {
        requireAction(action);
        if (!settings.enabled) return new Policy(false, true, false, "none", "", action, "", "", 0, 0, "");
        if (!configured()) return new Policy(true, false, false, "none", "", action, "", "", 0, 0, "");
        requests.consume("policy:" + request.getRemoteAddr(), 120, 60);
        requests.consume("policy:global", 1200, 60);
        boolean required = required(action, request.getRemoteAddr(), "");
        boolean turnstile = turnstile();
        HttpSession session = request.getSession(true);
        Challenge challenge;
        synchronized (session) {
            challenge = (Challenge) session.getAttribute(CHALLENGE + action);
            // proof() 之后会话里保存的是"待提交 token"的一次性句柄，再次读取策略时必须重新签发挑战。
            if (challenge == null || !challenge.proof().isEmpty() || !challenge.expires().isAfter(clock.instant())) {
                challenge = fresh();
                session.setAttribute(CHALLENGE + action, challenge);
            }
        }
        if (turnstile) return new Policy(true, true, required, "turnstile", settings.siteKey, action, challenge.nonce(), "", 0, 0, "");
        // 供应商由配置决定，不在供应商内部二次判断，避免"策略说 local、注入的却是 Turnstile"这类错配。
        HumanVerificationProvider.Challenge local = provider.issue(challenge.nonce());
        if (local == null) throw new BusinessException(503, "人机验证暂不可用，请稍后重试");
        return new Policy(true, true, required, local.provider(), "", action, challenge.nonce(),
                local.prompt(), local.targets(), local.tolerance(), local.svg());
    }

    public Permit verify(String action, String username, String token, HttpServletRequest request) {
        requireAction(action);
        if (!settings.enabled) return new Permit();
        requests.consume("submit:" + request.getRemoteAddr(), 60, 60);
        requests.consume("submit:global", 600, 60);
        if (!configured()) throw new BusinessException(503, "人机验证尚未配置，请联系管理员");
        boolean local = token != null && token.startsWith(LocalGraphicalVerificationProvider.TOKEN_PREFIX);
        boolean supplied = token != null && !token.isBlank();
        if ("login".equals(action) && !supplied) return reserve(username, request.getRemoteAddr());
        if (!supplied || token.length() > 2048) throw rejected();
        HttpSession session = request.getSession(false);
        Challenge challenge = null;
        if (session != null) {
            synchronized (session) {
                challenge = (Challenge) session.getAttribute(CHALLENGE + action);
                session.removeAttribute(CHALLENGE + action);
            }
        }
        if (challenge == null || !challenge.expires().isAfter(clock.instant())) throw rejected();
        Instant now = clock.instant();
        HumanVerificationProvider.Result result;
        if (local) {
            // 本地图形验证的几何判定已经在 prove() 里完成并消费掉挑战，这里只验"一次性 token + 会话绑定"，
            // 否则同一挑战会被判定两次。Turnstile 仍然要求每次都向供应商核验。
            if (turnstile()) throw rejected();
            if (!challenge.proof().equals(token) || !challenge.nonce().equals(nonceOf(token))) throw rejected();
            parseClicks(token);
            result = new HumanVerificationProvider.Result(true, "", action, challenge.nonce(), now);
        } else {
            result = provider.verify(token);
        }
        if (result == null || !result.success() || !action.equals(result.action()) || !challenge.nonce().equals(result.cdata())
                || result.challengeTime() == null || result.challengeTime().isBefore(now.minusSeconds(300))
                || result.challengeTime().isAfter(now.plusSeconds(30))
                || (turnstile() && !settings.hostnames.contains(result.hostname()))) throw rejected();
        return new Permit();
    }

    /**
     * 交换一次性人机验证 token：校验本地图形点选的点击坐标，成功返回可提交给登录/注册接口的 token。
     * 与 {@link #verify(String, String, String, HttpServletRequest)} 共用同一套会话绑定、一次性消费与几何判定。
     */
    public Proof prove(String action, String nonce, List<int[]> clicks, HttpServletRequest request) {
        requireAction(action);
        if (!settings.enabled) return new Proof(0, "");
        requests.consume("prove:" + request.getRemoteAddr(), 60, 60);
        requests.consume("prove:global", 600, 60);
        if (!configured()) throw new BusinessException(503, "人机验证尚未配置，请联系管理员");
        if (turnstile()) throw new BusinessException(400, "当前人机验证无需交换 token");
        String token = proofToken(action, nonce, clicks, request);
        return new Proof(clicks.size(), token);
    }

    private String proofToken(String action, String nonce, List<int[]> clicks, HttpServletRequest request) {
        if (nonce == null || nonce.isBlank() || clicks == null || clicks.isEmpty()) throw rejected();
        HttpSession session = request.getSession(false);
        Challenge challenge = null;
        if (session != null) {
            synchronized (session) {
                challenge = (Challenge) session.getAttribute(CHALLENGE + action);
                session.removeAttribute(CHALLENGE + action);
            }
        }
        if (challenge == null || !challenge.nonce().equals(nonce) || !challenge.expires().isAfter(clock.instant())) throw rejected();
        HumanVerificationProvider.Result result = provider.verify(nonce, action, clicks);
        Instant now = clock.instant();
        if (result == null || !result.success() || !action.equals(result.action()) || !nonce.equals(result.cdata())
                || result.challengeTime() == null || result.challengeTime().isBefore(now.minusSeconds(300))
                || result.challengeTime().isAfter(now.plusSeconds(30))) throw rejected();
        StringBuilder token = new StringBuilder(LocalGraphicalVerificationProvider.TOKEN_PREFIX).append(nonce);
        for (int[] point : clicks) {
            if (point == null || point.length != 2) throw rejected();
            token.append('.').append(point[0]).append('.').append(point[1]);
        }
        String issued = token.toString();
        if (issued.length() > 2048) throw rejected();
        // 把一次性 token 句柄放回会话：登录/注册时必须由同一会话原样提交，且 verify 会再次消费掉它。
        if (session != null) {
            synchronized (session) {
                session.setAttribute(CHALLENGE + action, new Challenge(nonce, clock.instant().plusSeconds(300), issued));
            }
        }
        return issued;
    }

    private static List<int[]> parseClicks(String token) {
        // local . 1 . nonce . x . y [ . x . y ] → 坐标从下标 3 开始，成对出现。
        String[] parts = token.split("\\.", -1);
        if (parts.length < 5 || parts.length % 2 != 1) throw rejected();
        List<int[]> clicks = new ArrayList<>(parts.length / 2 - 1);
        try {
            for (int index = 3; index < parts.length; index += 2) {
                clicks.add(new int[] { Integer.parseInt(parts[index]), Integer.parseInt(parts[index + 1]) });
            }
        } catch (NumberFormatException invalid) {
            throw rejected();
        }
        return clicks;
    }

    /** 一次性 token 形如 local.1.&lt;nonce&gt;.&lt;x&gt;.&lt;y&gt;[.&lt;x&gt;.&lt;y&gt;]，nonce 是第 3 段。 */
    private static String nonceOf(String token) {
        String[] parts = token.split("\\.", -1);
        if (parts.length < 4 || parts[2].isBlank()) throw rejected();
        return parts[2];
    }

    private Challenge fresh() {
        return new Challenge(UUID.randomUUID().toString().replace("-", ""), clock.instant().plusSeconds(300), "");
    }

    private boolean configured() {
        // 供应商 Bean 由 HumanVerificationProviderConfig 按同一份配置装配（Turnstile 或本地图形），
        // 不可用时一律 fail-closed：绝不出现"没配置却能过验证"。
        return turnstile() || LocalGraphicalVerificationProvider.PROVIDER.equals(settings.providerKind());
    }

    private boolean turnstile() {
        return "turnstile".equals(settings.providerKind());
    }

    private synchronized Permit reserve(String username, String address) {
        if (required("login", address, username) || inFlight.size() >= 10000) throw rejected();
        String[] keys = { "ip:" + address, "account:" + normalize(username) };
        for (String key : keys) inFlight.merge(key, 1, Integer::sum);
        return new Permit(keys);
    }

    public synchronized void failedLogin(String username, String address) {
        if (!settings.enabled) return;
        Instant now = clock.instant();
        failures.entrySet().removeIf(entry -> !entry.getValue().expires().isAfter(now));
        for (String key : new String[] { "ip:" + address, "account:" + normalize(username) }) {
            FailureWindow previous = failures.get(key);
            if (previous == null && failures.size() >= 10000) {
                saturatedUntil = now.plusSeconds(900);
            } else {
                failures.put(key, new FailureWindow(previous == null ? 1 : Math.min(3, previous.count() + 1),
                        previous == null ? now.plusSeconds(900) : previous.expires()));
            }
        }
    }

    private synchronized boolean required(String action, String address, String username) {
        Instant now = clock.instant();
        // admin_login 与 register 一律要求；普通 login 由 always-require-login 决定，
        // 关闭该开关时退回"失败三次后强制"的按风险策略。
        if (!"login".equals(action) || saturatedUntil.isAfter(now)) return true;
        if (settings.alwaysRequireLogin) return true;
        for (String key : new String[] { "ip:" + address, "account:" + normalize(username) }) {
            FailureWindow window = failures.get(key);
            int completedFailures = window != null && window.expires().isAfter(now) ? window.count() : 0;
            if (completedFailures + inFlight.getOrDefault(key, 0) >= 3) return true;
        }
        return false;
    }

    private static String normalize(String username) { return username == null ? "" : username.trim().toLowerCase(Locale.ROOT); }
    private static void requireAction(String action) {
        if (!ACTIONS.contains(action)) throw new BusinessException(400, "验证用途无效");
    }
    private static BusinessException rejected() { return new BusinessException(428, "请重新完成人机验证后提交"); }

    public final class Permit implements AutoCloseable {
        private final String[] keys;
        private boolean completed;

        private Permit(String... keys) { this.keys = keys; }

        @Override
        public void close() {
            synchronized (HumanVerificationService.this) {
                if (completed) return;
                completed = true;
                for (String key : keys) inFlight.computeIfPresent(key, (ignored, count) -> count <= 1 ? null : count - 1);
            }
        }
    }

    /**
     * 公开策略。Turnstile 生效时继续返回 siteKey；本地图形验证生效时返回服务端生成的 SVG 场景与提示
     * （prompt / targets / tolerance / scene），任何字段都不包含正确坐标。
     */
    public record Policy(boolean enabled, boolean available, boolean required, String provider, String siteKey, String action,
            String challenge, String prompt, int targets, int tolerance, String scene) {}

    /** 一次性人机验证 token 及其对应的点击数量。 */
    public record Proof(int targets, String token) {}

    private record Challenge(String nonce, Instant expires, String proof) implements java.io.Serializable {}
    private record FailureWindow(int count, Instant expires) {}
}
