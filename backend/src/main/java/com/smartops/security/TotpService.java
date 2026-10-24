package com.smartops.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.util.Locale;

@Service
public class TotpService {
    private static final String ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    private final Clock clock;
    private final SecureRandom random = new SecureRandom();
    public TotpService(@Qualifier("mfaClock") Clock clock) { this.clock = clock; }

    public String newSecret() {
        byte[] bytes = new byte[20];
        random.nextBytes(bytes);
        StringBuilder result = new StringBuilder(32);
        int buffer = 0, bits = 0;
        for (byte value : bytes) {
            buffer = (buffer << 8) | (value & 255);
            bits += 8;
            while (bits >= 5) { bits -= 5; result.append(ALPHABET.charAt((buffer >>> bits) & 31)); }
        }
        return result.toString();
    }

    public long currentStep() { return clock.instant().getEpochSecond() / 30; }

    public long match(String secret, String code, long lastUsedStep) {
        if (code == null || !code.matches("[0-9]{6}")) return -1;
        long current = currentStep();
        for (long step = current - 1; step <= current + 1; step++) {
            if (step >= 0 && step > lastUsedStep && MessageDigest.isEqual(code(secret, step).getBytes(StandardCharsets.US_ASCII), code.getBytes(StandardCharsets.US_ASCII))) return step;
        }
        return -1;
    }

    public String code(String secret, long step) { return code(secret, step, 6); }

    String code(String secret, long step, int digits) {
        try {
            Mac mac = Mac.getInstance("HmacSHA1");
            mac.init(new SecretKeySpec(decode(secret), "HmacSHA1"));
            byte[] digest = mac.doFinal(ByteBuffer.allocate(8).putLong(step).array());
            int offset = digest[digest.length - 1] & 15;
            int number = ByteBuffer.wrap(digest, offset, 4).getInt() & 0x7fffffff;
            return String.format(Locale.ROOT, "%0" + digits + "d", number % (digits == 8 ? 100000000 : 1000000));
        } catch (Exception failure) { throw new IllegalStateException("无法计算动态验证码", failure); }
    }

    private static byte[] decode(String secret) {
        if (secret == null || !secret.matches("[A-Z2-7]{32}")) throw new IllegalArgumentException("Invalid TOTP secret");
        byte[] result = new byte[20];
        int buffer = 0, bits = 0, index = 0;
        for (char value : secret.toCharArray()) {
            buffer = (buffer << 5) | ALPHABET.indexOf(value);
            bits += 5;
            if (bits >= 8) { bits -= 8; result[index++] = (byte) (buffer >>> bits); }
        }
        return result;
    }
}
