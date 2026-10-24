package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

import static com.smartops.security.LocalScene.shapes;
import static com.smartops.security.LocalScene.solution;
import static org.junit.jupiter.api.Assertions.*;

class LocalGraphicalVerificationProviderTest {
    private static final Instant START = Instant.parse("2026-10-03T00:00:00Z");

    /**
     * 时钟与 provider 的组合。先签发挑战、再推进时钟到人类点击耗时之后提交作答，
     * 因此既能覆盖"抢答被拒"，也能覆盖"正常作答通过"。
     */
    private static final class Fixture {
        private final TestClock clock = new TestClock(START);
        private final LocalGraphicalVerificationProvider provider;

        private Fixture() { this(20261003L); }

        private Fixture(long seed) {
            provider = new LocalGraphicalVerificationProvider(settings("", "", ""), clock, new Random(seed));
        }

        /** 模拟人类从看到图形到完成点击的耗时。 */
        private Fixture human() {
            clock.advanceMillis(LocalGraphicalVerificationProvider.MIN_RESPONSE_MILLIS);
            return this;
        }

        private Fixture advance(long millis) {
            clock.advanceMillis(millis);
            return this;
        }

        private HumanVerificationProvider.Challenge issue(String nonce) { return provider.issue(nonce); }

        private HumanVerificationProvider.Result verify(String token, List<int[]> clicks) {
            return provider.verify(token, "register", clicks);
        }
    }

    @Test
    void correctClicksPassAndTheSceneCarriesNoAnswerMetadata() {
        var fixture = new Fixture();
        var proof = fixture.issue("nonce-1");
        var shapes = shapes(proof.svg());
        assertTrue(shapes.size() >= 5, "场景必须包含目标与不少于 4 个干扰图形");
        assertEquals(1, proof.targets());
        assertFalse(proof.prompt().isBlank());
        assertEquals(LocalGraphicalVerificationProvider.TOKEN_PREFIX + "nonce-1", proof.token());
        assertFalse(proof.svg().contains("data-"), "场景不得携带任何答案属性");
        assertFalse(proof.svg().contains("<metadata"), "场景不得携带答案元数据");
        fixture.human();
        var result = fixture.verify(proof.token(), solution(proof.prompt(), shapes));
        assertTrue(result.success());
        assertEquals("register", result.action());
        assertEquals("nonce-1", result.cdata());
        assertNotNull(result.challengeTime());
    }

    @Test
    void aFailedAnswerBurnsTheProofSoItCanNeverBeReplayed() {
        var fixture = new Fixture();
        var proof = fixture.issue("nonce-2");
        var solution = solution(proof.prompt(), shapes(proof.svg()));
        fixture.human();
        refused(428, () -> fixture.verify(proof.token(), List.of(guaranteedMiss(shapes(proof.svg())))));
        refused(428, () -> fixture.verify(proof.token(), solution));
    }

    @Test
    void toleranceAcceptsTheExactBoundaryAndRejectsBeyondIt() {
        var fixture = new Fixture();
        var proof = fixture.issue("nonce-3");
        var shapes = shapes(proof.svg());
        var solution = solution(proof.prompt(), shapes);
        // 沿"远离最近邻"的若干方向找一个整数坐标点：它距目标 ≤ 容差，且最近图形仍是目标，测的是容差本身。
        var inside = new ArrayList<int[]>();
        for (int index = 0; index < solution.size(); index++) {
            inside.add(withinTolerance(solution.get(index), shapes, targetIndex(proof, shapes, index), LocalGraphicalVerificationProvider.TOLERANCE - 1));
        }
        fixture.human();
        assertTrue(fixture.verify(proof.token(), inside).success());

        var second = fixture.issue("nonce-4");
        var secondShapes = shapes(second.svg());
        var secondSolution = solution(second.prompt(), secondShapes);
        var beyond = new ArrayList<int[]>();
        for (int index = 0; index < secondSolution.size(); index++) {
            beyond.add(offset(secondSolution.get(index), secondShapes, targetIndex(second, secondShapes, index), LocalGraphicalVerificationProvider.TOLERANCE + 5));
        }
        refused(428, () -> fixture.verify(second.token(), beyond));
    }

    /** 找到第 order 个目标在解析结果里的下标（用坐标匹配，避免依赖解析顺序）。 */
    private static int targetIndex(HumanVerificationProvider.Challenge proof, List<LocalScene.Shape> shapes, int order) {
        List<int[]> expected = solution(proof.prompt(), shapes);
        for (int index = 0; index < shapes.size(); index++) {
            if (shapes.get(index).x() == expected.get(order)[0] && shapes.get(index).y() == expected.get(order)[1]) return index;
        }
        throw new AssertionError("无法在场景中定位第 " + order + " 个目标");
    }

    /** 沿"远离最近邻图形"的方向偏移 distance，用于构造必然超出容差的点。 */
    private static int[] offset(int[] point, List<LocalScene.Shape> shapes, int intended, int distance) {
        double[] away = awayFromNearest(point, shapes, intended);
        int x = (int) Math.round(point[0] + away[1] * distance);
        int y = (int) Math.round(point[1] - away[0] * distance);
        return new int[] { Math.max(0, Math.min(LocalGraphicalVerificationProvider.VIEW_WIDTH, x)),
                Math.max(0, Math.min(LocalGraphicalVerificationProvider.VIEW_HEIGHT, y)) };
    }

    /**
     * 在整数坐标网格里找一个满足"距目标 ≤ tolerance 且最近图形就是目标"的点。
     * 容差与图形间距都取整数网格，因此这样的点必然存在。
     */
    private static int[] withinTolerance(int[] point, List<LocalScene.Shape> shapes, int intended, int tolerance) {
        List<int[]> candidates = new ArrayList<>();
        for (int dx = -tolerance; dx <= tolerance; dx++) {
            for (int dy = -tolerance; dy <= tolerance; dy++) {
                if (Math.hypot(dx, dy) > tolerance) continue;
                int x = point[0] + dx;
                int y = point[1] + dy;
                if (x < 0 || x > LocalGraphicalVerificationProvider.VIEW_WIDTH || y < 0 || y > LocalGraphicalVerificationProvider.VIEW_HEIGHT) continue;
                double toIntended = Math.hypot(dx, dy);
                boolean nearest = true;
                for (int index = 0; index < shapes.size(); index++) {
                    if (index == intended) continue;
                    if (Math.hypot(shapes.get(index).x() - x, shapes.get(index).y() - y) <= toIntended) nearest = false;
                }
                if (nearest) candidates.add(new int[] { x, y });
            }
        }
        if (candidates.isEmpty()) throw new AssertionError("场景中不存在可判定的容差点，测试前提不成立");
        return candidates.get(candidates.size() - 1);
    }

    private static double[] awayFromNearest(int[] point, List<LocalScene.Shape> shapes, int intended) {
        double awayX = 1;
        double awayY = 0;
        double closest = Double.MAX_VALUE;
        for (int index = 0; index < shapes.size(); index++) {
            if (index == intended) continue;
            double dx = shapes.get(index).x() - point[0];
            double dy = shapes.get(index).y() - point[1];
            double length = Math.hypot(dx, dy);
            if (length < closest) {
                closest = length;
                awayX = -dx / length;
                awayY = -dy / length;
            }
        }
        return new double[] { awayX, awayY };
    }

    @Test
    void clickCountAndOrderAreEnforcedAgainstTheServerSideTargets() {
        var fixture = new Fixture();
        var proof = fixture.issue("nonce-5");
        var solution = solution(proof.prompt(), shapes(proof.svg()));
        fixture.human();
        if (solution.size() > 1) {
            var reversed = new ArrayList<>(solution);
            Collections.reverse(reversed);
            refused(428, () -> fixture.verify(proof.token(), reversed));
        } else {
            // 单目标挑战：点两次同一个坐标不能冒充"依次点中多个目标"。
            refused(428, () -> fixture.verify(proof.token(), List.of(solution.get(0), solution.get(0))));
        }
    }

    @Test
    void aMissingOrExtraClickIsRejectedForAMultiTargetChallenge() {
        var twoTargets = findTwoTargetChallenge();
        var solution = solution(twoTargets.prompt(), shapes(twoTargets.svg()));
        refused(428, () -> twoTargets.verify(List.of(solution.get(0))));

        var other = findTwoTargetChallenge();
        var otherSolution = solution(other.prompt(), shapes(other.svg()));
        refused(428, () -> other.verify(List.of(otherSolution.get(0), otherSolution.get(0))));
    }

    /** 造一个双目标挑战（提示里出现两个目标），用于覆盖"少点/重复点"的失败路径。 */
    private static Pending findTwoTargetChallenge() {
        for (int seed = 0; seed < 40; seed++) {
            var clock = new TestClock(START);
            var provider = new LocalGraphicalVerificationProvider(settings("", "", ""), clock, new Random(seed));
            var proof = provider.issue("extra-" + seed);
            if (proof.targets() > 1 && LocalScene.solution(proof.prompt(), shapes(proof.svg())).size() == 2) {
                var fixture = new Fixture(seed);
                return new Pending(fixture, fixture.issue("extra-" + seed));
            }
        }
        throw new AssertionError("未找到双目标挑战，测试前提不成立");
    }

    /** 已签发但尚未作答的挑战。 */
    private record Pending(Fixture fixture, HumanVerificationProvider.Challenge proof) {
        private String prompt() { return proof.prompt(); }
        private String svg() { return proof.svg(); }
        private HumanVerificationProvider.Result verify(List<int[]> clicks) {
            fixture.human();
            return fixture.verify(proof.token(), clicks);
        }
    }

    @Test
    void responseTimingGateBlocksInstantScriptedAnswers() {
        // 同一个 nonce 会返回同一次签发的场景，因此可以先验证"抢答被拒"，再验证"正常作答通过"。
        var fixture = new Fixture();
        var scripted = fixture.issue("nonce-6");
        refused(428, () -> fixture.verify(scripted.token(), solution(scripted.prompt(), shapes(scripted.svg()))));

        var patient = fixture.issue("nonce-7");
        var patientSolution = solution(patient.prompt(), shapes(patient.svg()));
        System.out.println("GATE2 prompt=" + patient.prompt().chars()
                .mapToObj(code -> code < 128 ? String.valueOf((char) code) : "\\u" + Integer.toHexString(code)).reduce("", String::concat)
                + " targets=" + patient.targets() + " clicks=" + patientSolution.size() + " scene=" + shapes(patient.svg()));
        fixture.human();
        assertTrue(fixture.verify(patient.token(), patientSolution).success());
    }

    @Test
    void expiredAndUnknownProofsFailClosed() {
        var expired = new Fixture();
        var proof = expired.issue("nonce-8");
        var solution = solution(proof.prompt(), shapes(proof.svg()));
        expired.advance(LocalGraphicalVerificationProvider.TTL_SECONDS * 1000);
        refused(428, () -> expired.verify(proof.token(), solution));
        var afterRestart = new Fixture();
        refused(428, () -> afterRestart.verify(proof.token(), solution));
    }

    /**
     * 空载荷、空白 token、空 action 属于"调用方用错"，供应商返回 null 而不是异常；
     * {@link HumanVerificationService} 把 null 当作失败处理，因此仍然是 fail-closed。几何判定与存储层错误才抛异常。
     */
    @Test
    void emptyOrMissingPayloadsReturnNoResultSoTheServiceCanReject() {
        var fixture = new Fixture();
        assertNull(fixture.provider.verify(null, "register", List.of(new int[] { 10, 10 })));
        assertNull(fixture.provider.verify("", "register", List.of(new int[] { 10, 10 })));
        assertNull(fixture.provider.verify("   ", "register", List.of(new int[] { 10, 10 })));
        assertNull(fixture.provider.verify("nonce", null, List.of(new int[] { 10, 10 })));
        assertNull(fixture.provider.verify("nonce", "register", null));
        assertNull(fixture.provider.verify("nonce", "register", List.of()));
        refused(428, () -> fixture.provider.verify("never-issued", "register", List.of(new int[] { 10, 10 })));
    }

    @Test
    void malformedCoordinatesAndExcessiveClickCountsAreRejectedAsBadRequests() {
        var fixture = new Fixture();
        refused(400, () -> fixture.verify("nonce", List.of(new int[] { LocalGraphicalVerificationProvider.VIEW_WIDTH + 1, 10 })));
        refused(400, () -> fixture.verify("nonce", List.of(new int[] { -1, 10 })));
        refused(400, () -> fixture.verify("nonce", List.of(new int[] { 10, LocalGraphicalVerificationProvider.VIEW_HEIGHT + 1 })));
        refused(400, () -> fixture.verify("nonce", List.of(new int[] { 10 }, new int[] { 1, 2 })));
        var tooMany = new ArrayList<int[]>();
        for (int index = 0; index <= LocalGraphicalVerificationProvider.MAX_CLICKS; index++) tooMany.add(new int[] { 10 + index, 10 });
        refused(400, () -> fixture.verify("nonce", tooMany));
    }

    @Test
    void oneNonceKeepsOneSceneSoRefreshingCannotChangeThePuzzle() {
        var fixture = new Fixture();
        var first = fixture.issue("nonce-9");
        var second = fixture.issue("nonce-9");
        assertEquals(first.svg(), second.svg());
        assertEquals(first.prompt(), second.prompt());
        assertEquals(LocalGraphicalVerificationProvider.TOKEN_PREFIX + "nonce-9", second.token());
        assertNotEquals(first.svg(), fixture.issue("nonce-10").svg());
    }

    @Test
    void everyGeneratedSceneKeepsColoursAndLettersUnique() {
        // 回归护栏：早期版本允许"同字符不同颜色"或"同颜色不同字符"同时出现，会让提示出现歧义答案。
        var fixture = new Fixture();
        for (int index = 0; index < 300; index++) {
            var proof = fixture.issue("uniqueness-" + index);
            var shapes = shapes(proof.svg());
            assertEquals(shapes.size(), shapes.stream().map(LocalScene.Shape::letter).distinct().count(), "字符必须唯一：" + proof.prompt());
            assertEquals(shapes.size(), shapes.stream().map(LocalScene.Shape::color).distinct().count(), "颜色必须唯一：" + proof.prompt());
            assertTrue(proof.targets() >= 1 && proof.targets() <= 2);
            assertEquals(proof.targets(), solution(proof.prompt(), shapes).size(), "提示必须唯一指向目标：" + proof.prompt());
        }
    }

    @Test
    void providerSelectionFollowsConfigurationAndTurnstileKeepsItsOwnShape() {
        var environment = new MockEnvironment().withProperty("spring.profiles.active", "test");
        var local = new HumanVerificationSettings(true, "", "", "", 600, true, environment);
        var turnstile = new HumanVerificationSettings(true, "site", "secret", "ops.example.test", 600, true, environment);
        assertEquals("local", local.providerKind());
        assertEquals("local", new HumanVerificationSettings(true, "site", "", "", 600, true, environment).providerKind());
        assertEquals("local", new HumanVerificationSettings(true, "", "secret", "ops.example.test", 600, true, environment).providerKind());
        assertEquals("turnstile", turnstile.providerKind());
        assertNull(new LocalGraphicalVerificationProvider(local).verify("local.1.nonce.1.2"));
        assertNull(new TurnstileVerificationProvider(turnstile).issue("nonce"));
        assertNull(new TurnstileVerificationProvider(turnstile).verify("token", "register", List.of(new int[] { 1, 2 })));
    }

    /** 找一个必然未命中任何图形的位置，确保"错误作答"真的错。 */
    private static int[] guaranteedMiss(List<LocalScene.Shape> shapes) {
        int[][] candidates = { { 2, 2 }, { LocalGraphicalVerificationProvider.VIEW_WIDTH - 2, 2 },
                { 2, LocalGraphicalVerificationProvider.VIEW_HEIGHT - 2 },
                { LocalGraphicalVerificationProvider.VIEW_WIDTH - 2, LocalGraphicalVerificationProvider.VIEW_HEIGHT - 2 } };
        for (int[] candidate : candidates) {
            boolean clear = true;
            for (LocalScene.Shape shape : shapes) {
                if (Math.hypot(shape.x() - candidate[0], shape.y() - candidate[1]) <= LocalGraphicalVerificationProvider.TOLERANCE) clear = false;
            }
            if (clear) return candidate;
        }
        throw new AssertionError("场景未留下任何必然未命中的位置，测试前提不成立");
    }

    private static HumanVerificationSettings settings(String site, String secret, String hosts) {
        return new HumanVerificationSettings(true, site, secret, hosts, LocalGraphicalVerificationProvider.MIN_RESPONSE_MILLIS,
                true, new MockEnvironment().withProperty("spring.profiles.active", "test"));
    }

    private static void refused(int code, Executable action) {
        assertEquals(code, assertThrows(BusinessException.class, action::run).getCode());
    }

    private interface Executable {
        void run();
    }
}
