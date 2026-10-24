package com.smartops.security;

import java.time.Instant;
import java.util.List;

/**
 * 本地图形点选验证的作答凭据。
 *
 * <p>只包含"哪一次挑战（nonce）+ 要按顺序点中几个图形（targets）+ 何时过期"，正确答案（图形坐标）
 * 始终留在 {@link LocalGraphicalVerificationProvider} 的服务端存储里，从不下发给浏览器。</p>
 */
record HumanVerificationChallenge(String nonce, List<String> targets, Instant expires) {
}
