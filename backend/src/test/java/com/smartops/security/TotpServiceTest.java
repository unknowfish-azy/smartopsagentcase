package com.smartops.security;

import org.junit.jupiter.api.Test;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import static org.junit.jupiter.api.Assertions.*;

class TotpServiceTest {
    private static final String SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
    @Test void matchesRfc6238Sha1Vectors() {
        var totp = new TotpService(Clock.systemUTC());
        long[] times = {59, 1111111109, 1111111111, 1234567890, 2000000000, 20000000000L};
        String[] expected = {"94287082", "07081804", "14050471", "89005924", "69279037", "65353130"};
        for (int index = 0; index < times.length; index++) assertEquals(expected[index], totp.code(SECRET, times[index] / 30, 8));
    }
    @Test void checksWindowFormatAndConsumedStep() {
        var totp = new TotpService(Clock.fixed(Instant.ofEpochSecond(3000), ZoneOffset.UTC));
        for (long step : new long[] {99, 100, 101}) assertEquals(step, totp.match(SECRET, totp.code(SECRET, step), 98));
        assertEquals(-1, totp.match(SECRET, totp.code(SECRET, 100), 100));
        assertEquals(-1, totp.match(SECRET, totp.code(SECRET, 98), -1));
        for (String code : new String[] {"", "12345", "1234567", "abcdef", "１２３４５６"}) assertEquals(-1, totp.match(SECRET, code, -1));
    }
    @Test void generatesDistinctTwentyByteBase32Secrets() {
        var totp = new TotpService(Clock.systemUTC());
        var secrets = new HashSet<String>();
        for (int index = 0; index < 100; index++) { String secret = totp.newSecret(); assertTrue(secret.matches("[A-Z2-7]{32}")); secrets.add(secret); }
        assertEquals(100, secrets.size());
    }
}
