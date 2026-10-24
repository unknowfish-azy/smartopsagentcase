package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.web.MockHttpServletRequest;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

class HumanVerificationServiceTest {
    private final Instant now = Instant.parse("2026-10-03T00:00:00Z");
    private final HumanVerificationProvider provider = mock(HumanVerificationProvider.class);
    private final HumanVerificationSettings settings = settings(true, "site", "secret", "ops.example.test");
    private HumanVerificationService service;
    private MockHttpServletRequest request;

    @BeforeEach
    void setup() {
        service = new HumanVerificationService(settings, provider, Clock.fixed(now, ZoneOffset.UTC));
        request = new MockHttpServletRequest();
        request.setRemoteAddr("192.0.2.1");
    }

    @Test
    void registrationAndAdminAreMandatoryAndOrdinaryLoginIsMandatoryByDefault() {
        // 默认 always-require-login=true：两个入口行为对齐，用户层登录也要验证。
        assertTrue(service.policy("register", request).required());
        assertTrue(service.policy("admin_login", request).required());
        assertTrue(service.policy("login", request).required());
        denied(428, () -> service.verify("login", "user", null, request));
        denied(428, () -> service.verify("register", "user", null, request));
        denied(428, () -> service.verify("admin_login", "user", "", request));
        verifyNoInteractions(provider);
    }

    @Test
    void ordinaryLoginFallsBackToLowFrictionWhenAlwaysRequireIsDisabled() {
        // 关闭开关后退回"失败三次才强制"的按风险策略（保留给不需要每次验证的部署）。
        // 这里保留 Turnstile 配置，让 provider 可用；只看 required 的判定。
        var lowFriction = new HumanVerificationService(
                new HumanVerificationSettings(true, "site", "secret", "ops.example.test", 600, false, new MockEnvironment().withProperty("spring.profiles.active", "test")),
                provider, Clock.fixed(now, ZoneOffset.UTC));
        assertFalse(lowFriction.policy("login", request).required());
        assertTrue(lowFriction.policy("register", request).required());
        assertTrue(lowFriction.policy("admin_login", request).required());
    }

    @Test
    void ipAndAccountFailuresSurviveSessionRotationAndTriggerVerification() {
        for (int attempt = 0; attempt < 3; attempt++) service.failedLogin("Account", request.getRemoteAddr());
        assertTrue(service.policy("login", request).required());
        var otherSession = new MockHttpServletRequest();
        otherSession.setRemoteAddr("192.0.2.2");
        denied(428, () -> service.verify("login", "ACCOUNT", "", otherSession));
        denied(428, () -> service.verify("login", "different-account", "", request));
    }

    @Test
    void concurrentPasswordAttemptsCannotExceedRemainingUnverifiedAllowance() throws Exception {
        // 这条用例验证的是"按风险触发"模式下的在途额度预占，
        // 因此显式关闭 always-require-login，避免被"一律要求验证"提前拦掉。
        var lowFriction = new HumanVerificationService(
                new HumanVerificationSettings(true, "", "", "", 600, false, new MockEnvironment().withProperty("spring.profiles.active", "test")),
                provider, Clock.fixed(now, ZoneOffset.UTC));
        lowFriction.failedLogin("user", "192.0.2.1");
        lowFriction.failedLogin("user", "192.0.2.1");
        var executor = Executors.newFixedThreadPool(4);
        var start = new CountDownLatch(1);
        var results = new ArrayList<Future<Integer>>();
        try {
            for (int attempt = 0; attempt < 4; attempt++) {
                results.add(executor.submit(() -> {
                    start.await();
                    var concurrent = new MockHttpServletRequest();
                    concurrent.setRemoteAddr("192.0.2.1");
                    try { lowFriction.verify("login", "user", "", concurrent); return 200; }
                    catch (BusinessException denied) { return denied.getCode(); }
                }));
            }
            start.countDown();
            int admitted = 0;
            for (var result : results) {
                int status = result.get(5, TimeUnit.SECONDS);
                assertTrue(status == 200 || status == 428);
                if (status == 200) admitted++;
            }
            assertEquals(1, admitted, "only the third unverified password attempt may enter authentication");
        } finally { executor.shutdownNow(); }
    }

    @Test
    void boundTokenIsConsumedOnceEvenIfProviderReturnsSuccessAgain() {
        String challenge = service.policy("register", request).challenge();
        when(provider.verify("valid-token")).thenReturn(result("register", challenge));
        service.verify("register", "user", "valid-token", request);
        denied(428, () -> service.verify("register", "user", "valid-token", request));
        verify(provider, times(1)).verify("valid-token");
    }

    @Test
    void crossSessionTokenFailsEvenWithProviderSuccess() {
        String challenge = service.policy("register", request).challenge();
        var differentSession = new MockHttpServletRequest();
        service.policy("register", differentSession);
        when(provider.verify(anyString())).thenReturn(result("register", challenge));
        denied(428, () -> service.verify("register", "user", "borrowed-token", differentSession));
    }

    @Test
    void wrongActionHostnameNonceAndTimestampAreRejected() {
        for (String scenario : new String[] { "action", "hostname", "nonce", "expired", "future", "missing", "false" }) {
            String challenge = service.policy("admin_login", request).challenge();
            when(provider.verify(anyString())).thenReturn(new HumanVerificationProvider.Result(!scenario.equals("false"),
                    scenario.equals("hostname") ? "attacker.example.test" : "ops.example.test",
                    scenario.equals("action") ? "register" : "admin_login", scenario.equals("nonce") ? "wrong" : challenge,
                    scenario.equals("expired") ? now.minusSeconds(301) : scenario.equals("future") ? now.plusSeconds(31) : scenario.equals("missing") ? null : now));
            denied(428, () -> service.verify("admin_login", "user", "token", request));
        }
    }

    @Test
    void expiredServerChallengeFailsWithoutCallingProvider() {
        Clock clock = mock(Clock.class);
        when(clock.instant()).thenReturn(now);
        service = new HumanVerificationService(settings, provider, clock);
        service.policy("register", request);
        when(clock.instant()).thenReturn(now.plusSeconds(301));
        denied(428, () -> service.verify("register", "user", "token", request));
        verifyNoInteractions(provider);
    }

    @Test
    void providerOutageNeverFallsBackToSuccess() {
        service.policy("register", request);
        when(provider.verify(anyString())).thenThrow(new BusinessException(503, "unavailable"));
        denied(503, () -> service.verify("register", "user", "token", request));
        denied(428, () -> service.verify("register", "user", "token", request));
    }

    @Test
    void missingTurnstileKeysNowFallBackToOfflineGraphicalVerification() {
        var local = localService(settings(true, "", "", ""), now.plusSeconds(30), 5);
        var policy = local.service().policy("login", request);
        assertTrue(policy.available());
        assertEquals("local", policy.provider());
        assertTrue(policy.scene().startsWith("<svg"));
        assertTrue(policy.targets() >= 1);
        assertFalse(policy.scene().contains("data-"));
        assertNotNull(policy.challenge());
    }

    @Test
    void graphicalProofExchangesForASingleUseTokenThatStillBindsTheSession() {
        var local = localService(settings(true, "", "", ""), now.plusSeconds(30), 11);
        var service = local.service();
        var policy = service.policy("register", request);
        local.human();
        var proof = service.prove("register", policy.challenge(), solve(policy.scene(), policy.prompt()), request);
        // 一次性 token = 前缀 + 会话挑战 + 每个点击的两段坐标，逐字锁定接口契约。
        StringBuilder expected = new StringBuilder(LocalGraphicalVerificationProvider.TOKEN_PREFIX).append(policy.challenge());
        for (int[] click : solve(policy.scene(), policy.prompt())) expected.append('.').append(click[0]).append('.').append(click[1]);
        assertTrue(proof.token().startsWith(LocalGraphicalVerificationProvider.TOKEN_PREFIX + policy.challenge() + "."));
        assertEquals(expected.length(), proof.token().length());
        assertEquals(policy.targets(), proof.targets());
        service.verify("register", "user", proof.token(), request);
        denied(428, () -> service.verify("register", "user", proof.token(), request));

        var replayed = service.policy("register", request);
        assertNotEquals(policy.challenge(), replayed.challenge(), "prove() 之后必须签发新的挑战");
        local.human();
        var nextProof = service.prove("register", replayed.challenge(), solve(replayed.scene(), replayed.prompt()), request);
        var otherSession = new MockHttpServletRequest();
        otherSession.setRemoteAddr("192.0.2.9");
        service.policy("register", otherSession);
        denied(428, () -> service.verify("register", "user", nextProof.token(), otherSession));
    }

    @Test
    void forgedLocalTokensAndWrongClicksAreRejectedWithoutWeakeningMandatoryPortals() {
        var local = localService(settings(true, "", "", ""), now.plusSeconds(30), 13);
        var service = local.service();
        assertTrue(service.policy("register", request).required());
        assertTrue(service.policy("admin_login", request).required());
        var policy = service.policy("admin_login", request);
        var clicks = solve(policy.scene(), policy.prompt());
        var wrong = clickThatMissesEveryShape(policy.scene());
        local.human();
        denied(428, () -> service.prove("admin_login", policy.challenge(), wrong, request));
        denied(428, () -> service.prove("admin_login", "0".repeat(32), clicks, request));
        denied(428, () -> service.prove("admin_login", policy.challenge(), clicks, request));
        denied(400, () -> service.prove("unknown", policy.challenge(), clicks, request));
        // 本地 token 不能跨越"供应商已切回 Turnstile"的配置边界被接受。
        var turnstile = new HumanVerificationService(settings(true, "site", "secret", "ops.example.test"), provider, Clock.fixed(now.plusSeconds(30), ZoneOffset.UTC));
        turnstile.policy("register", request);
        denied(428, () -> turnstile.verify("register", "user", "local.1." + "a".repeat(32) + ".10.10", request));
    }

    @Test
    void aLocalTokenIssuedInOneSessionIsNeverAcceptedInAnother() {
        var local = localService(settings(true, "", "", ""), now.plusSeconds(30), 17);
        var service = local.service();
        var policy = service.policy("register", request);
        local.human();
        var proof = service.prove("register", policy.challenge(), solve(policy.scene(), policy.prompt()), request);
        var attacker = new MockHttpServletRequest();
        attacker.setRemoteAddr("192.0.2.77");
        service.policy("register", attacker);
        denied(428, () -> service.verify("register", "user", proof.token(), attacker));
        service.verify("register", "user", proof.token(), request);
    }

    @Test
    void requestLimitsAreNotResetBySuccessfulVerification() {
        // 这两条用例验证的是"未验证登录的在途额度与限流"，只在按风险触发模式下存在；
        // 显式使用低摩擦实例，避免被默认的"一律要求验证"提前拦掉。
        var lowFriction = lowFriction();
        for (int attempt = 0; attempt < 60; attempt++) lowFriction.verify("login", "user", "", request).close();
        denied(429, () -> lowFriction.verify("login", "user", "", request));
    }

    @Test
    void completionReleasesInFlightAllowanceExactlyOnce() {
        var lowFriction = lowFriction();
        var first = lowFriction.verify("login", "user", "", request);
        var second = lowFriction.verify("login", "user", "", request);
        var third = lowFriction.verify("login", "user", "", request);
        denied(428, () -> lowFriction.verify("login", "user", "", request));
        first.close();
        first.close();
        var replacement = lowFriction.verify("login", "user", "", request);
        denied(428, () -> lowFriction.verify("login", "user", "", request));
        second.close();
        third.close();
        replacement.close();
        assertFalse(lowFriction.policy("login", request).required());
    }

    /** 按风险触发模式的实例：always-require-login=false。 */
    private HumanVerificationService lowFriction() {
        return new HumanVerificationService(
                new HumanVerificationSettings(true, "site", "secret", "ops.example.test", 600, false,
                        new MockEnvironment().withProperty("spring.profiles.active", "test")),
                provider, Clock.fixed(now, ZoneOffset.UTC));
    }

    @Test
    void invalidActionOrPortalCannotSelectUnprotectedPolicy() {
        denied(400, () -> service.policy("unknown", request));
        denied(400, () -> service.loginAction("operator"));
        assertEquals("login", service.loginAction(null));
        assertEquals("admin_login", service.loginAction("admin"));
    }

    @Test
    void devOptOutIsExplicitAndDoesNotInvokeProvider() {
        service = new HumanVerificationService(settings(false, "", "", ""), provider);
        assertFalse(service.policy("register", request).enabled());
        service.verify("register", "user", null, request);
        verifyNoInteractions(provider);
    }

    private HumanVerificationProvider.Result result(String action, String nonce) {
        return new HumanVerificationProvider.Result(true, "ops.example.test", action, nonce, now);
    }

    /** provider 与 service 必须共用同一个时钟：供应商自带的"人类点击下限"以签发时间为基准。 */
    private static LocalGraphicalVerificationProvider localProvider(Instant at, long seed) {
        return new LocalGraphicalVerificationProvider(settings(true, "", "", ""), Clock.fixed(at, ZoneOffset.UTC), new Random(seed));
    }

    /**
     * 本地图形验证的完整服务 + 可推进时钟。挑战在时钟推进之前签发，作答在人类点击耗时之后提交，
     * 否则会被"最短作答时间"闸门判成脚本。
     */
    private record LocalService(HumanVerificationService service, TestClock clock) {
        private void human() { clock.advanceMillis(LocalGraphicalVerificationProvider.MIN_RESPONSE_MILLIS); }
    }

    private static LocalService localService(HumanVerificationSettings settings, Instant issuedAt, long seed) {
        var clock = new TestClock(issuedAt);
        var provider = new LocalGraphicalVerificationProvider(settings, clock, new Random(seed));
        return new LocalService(new HumanVerificationService(settings, provider, clock), clock);
    }

    /** 只依据提示文字（颜色/字符）挑出目标，模拟"看懂提示后点击"的作答。 */
    private static List<int[]> solve(String scene, String prompt) {
        List<int[]> clicks = LocalScene.solution(prompt, LocalScene.shapes(scene));
        assertFalse(clicks.isEmpty(), "必须能从提示推出至少一个目标");
        return clicks;
    }

    /** 找一个必然未命中任何图形的位置，确保"错误作答"真的错。 */
    private static List<int[]> clickThatMissesEveryShape(String scene) {
        List<LocalScene.Shape> shapes = LocalScene.shapes(scene);
        int[][] candidates = { { 2, 2 }, { 298, 2 }, { 2, 198 }, { 298, 198 } };
        for (int[] candidate : candidates) {
            boolean clear = true;
            for (LocalScene.Shape shape : shapes) {
                if (Math.hypot(shape.x() - candidate[0], shape.y() - candidate[1]) <= LocalGraphicalVerificationProvider.TOLERANCE) clear = false;
            }
            if (clear) return List.of(candidate);
        }
        throw new AssertionError("场景未留下任何必然未命中的位置，测试前提不成立");
    }

    private static HumanVerificationSettings settings(boolean enabled, String site, String secret, String hosts) {
        return new HumanVerificationSettings(enabled, site, secret, hosts, 600, true, new MockEnvironment().withProperty("spring.profiles.active", "test"));
    }

    private static void denied(int code, Runnable request) {
        assertEquals(code, assertThrows(BusinessException.class, request::run).getCode());
    }
}
