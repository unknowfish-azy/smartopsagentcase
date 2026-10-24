package com.smartops.security;

import java.time.Instant;
import java.util.List;

public interface HumanVerificationProvider {
    Result verify(String token);

    /**
     * 为一次会话挑战签发供应商侧凭据（本地图形验证用来下发场景并在服务端保存正确答案）。
     * 无状态供应商（Turnstile）返回 null。
     */
    default Challenge issue(String nonce) {
        return null;
    }

    /**
     * 带用途与点击坐标的校验入口，只有本地图形验证需要；其他供应商返回 null，
     * 由 {@link HumanVerificationService} 走 {@link #verify(String)}。
     */
    default Result verify(String token, String action, List<int[]> clicks) {
        return null;
    }

    record Result(boolean success, String hostname, String action, String cdata, Instant challengeTime) {}

    /** 下发给浏览器的挑战信息：图形场景与提示，绝不包含正确坐标。 */
    record Challenge(String provider, String token, String prompt, int targets, int tolerance, String svg) {}
}
