package com.smartops.security;

import com.smartops.exception.BusinessException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.regex.Pattern;

/**
 * 聊天 run 令牌（SEC-01/SEC-02）。
 *
 * <p>Java 边缘在已认证会话内签发短时 HMAC 令牌，ai-service 只信任令牌里的
 * subject / run_id，客户端自带的 {@code X-Run-ID} 不再作为身份。令牌只承载
 * 关联身份，不携带 Prompt、工具参数或凭据。</p>
 *
 * <p>令牌格式：{@code v1.<base64url(payload)>.<base64url(hmacSha256("v1." + payload)>)}，
 * payload 为紧凑 JSON：{@code {"sub":"<userId>","run":"<runId>","iat":...,"exp":...}}。</p>
 */
@Service
public class RunTokenService {

    public static final String HEADER = "X-Run-Token";
    public static final String VERSION = "v1";

    private static final Pattern RUN_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}");
    private static final int MIN_SECRET_BYTES = 16;

    private final byte[] secret;
    private final long ttlSeconds;
    private final SecureRandom random = new SecureRandom();

    public RunTokenService(
            @Value("${smartops.security.chat.run-token.secret:}") String secret,
            @Value("${smartops.security.chat.run-token.ttl-seconds:300}") long ttlSeconds
    ) {
        this.secret = secret == null ? new byte[0] : secret.trim().getBytes(StandardCharsets.UTF_8);
        this.ttlSeconds = Math.max(30, ttlSeconds);
    }

    public Issued issue(long userId) {
        return issue(userId, Instant.now());
    }

    Issued issue(long userId, Instant now) {
        if (secret.length < MIN_SECRET_BYTES) {
            // fail-closed：未配置共享密钥时拒绝签发，而不是发一个无人能校验的令牌。
            throw new BusinessException(503, "CHAT_RUN_TOKEN_NOT_CONFIGURED");
        }
        long issuedAt = now.getEpochSecond();
        long expiresAt = issuedAt + ttlSeconds;
        String runId = "run-" + HexFormat.of().formatHex(randomBytes(16));
        String payload = "{\"sub\":\"" + userId + "\",\"run\":\"" + runId
                + "\",\"iat\":" + issuedAt + ",\"exp\":" + expiresAt + "}";
        String encoded = encode(payload.getBytes(StandardCharsets.UTF_8));
        String signingInput = VERSION + "." + encoded;
        String signature = encode(hmac(signingInput.getBytes(StandardCharsets.UTF_8)));
        return new Issued(runId, signingInput + "." + signature, ttlSeconds);
    }

    public Token verify(String token) {
        return verify(token, Instant.now());
    }

    Token verify(String token, Instant now) {
        if (secret.length < MIN_SECRET_BYTES) {
            throw new BusinessException(503, "CHAT_RUN_TOKEN_NOT_CONFIGURED");
        }
        if (token == null || token.isBlank()) {
            throw new BusinessException(401, "RUN_TOKEN_REQUIRED");
        }
        String[] parts = token.split("\\.");
        if (parts.length != 3 || !VERSION.equals(parts[0])) {
            throw new BusinessException(401, "RUN_TOKEN_INVALID");
        }
        byte[] signingInput = (VERSION + "." + parts[1]).getBytes(StandardCharsets.UTF_8);
        byte[] expected = hmac(signingInput);
        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(parts[2]);
        } catch (IllegalArgumentException invalid) {
            throw new BusinessException(401, "RUN_TOKEN_INVALID");
        }
        if (!MessageDigest.isEqual(expected, supplied)) {
            throw new BusinessException(401, "RUN_TOKEN_INVALID");
        }
        Payload payload = parse(parts[1]);
        if (payload.expiresAt() <= now.getEpochSecond()) {
            throw new BusinessException(401, "RUN_TOKEN_EXPIRED");
        }
        if (payload.subject() == null || !payload.subject().matches("[0-9]{1,19}")
                || payload.runId() == null || !RUN_ID.matcher(payload.runId()).matches()) {
            throw new BusinessException(401, "RUN_TOKEN_INVALID");
        }
        return new Token(payload.subject(), payload.runId(), payload.expiresAt());
    }

    private Payload parse(String encoded) {
        try {
            String json = new String(Base64.getUrlDecoder().decode(encoded), StandardCharsets.UTF_8);
            // 只接受本服务生成的紧凑 JSON，避免引入额外 JSON 解析依赖与歧义。
            java.util.regex.Matcher matcher = Pattern
                    .compile("\\{\"sub\":\"([0-9]{1,19})\",\"run\":\"([^\"]*)\",\"iat\":([0-9]{1,15}),\"exp\":([0-9]{1,15})\\}")
                    .matcher(json);
            if (!matcher.matches()) throw new IllegalArgumentException("payload");
            return new Payload(matcher.group(1), matcher.group(2),
                    Long.parseLong(matcher.group(4)));
        } catch (IllegalArgumentException invalid) {
            throw new BusinessException(401, "RUN_TOKEN_INVALID");
        }
    }

    private byte[] hmac(byte[] input) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(input);
        } catch (java.security.GeneralSecurityException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private byte[] randomBytes(int length) {
        byte[] bytes = new byte[length];
        random.nextBytes(bytes);
        return bytes;
    }

    private static String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    public record Issued(String runId, String token, long ttlSeconds) {}

    public record Token(String subject, String runId, long expiresAt) {}

    private record Payload(String subject, String runId, long expiresAt) {}
}
