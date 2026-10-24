package com.smartops.security;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

/**
 * 可推进的测试时钟。让同一个被测实例既保留下发的挑战，又能模拟"人类点击耗时"这类时间依赖。
 */
final class TestClock extends Clock {
    private Instant now;

    TestClock(Instant now) { this.now = now; }

    @Override public ZoneOffset getZone() { return ZoneOffset.UTC; }
    @Override public Clock withZone(ZoneId zone) { return this; }
    @Override public Instant instant() { return now; }

    /** 推进时钟：同一个实例上后续的调用都会看到新的"现在"。 */
    TestClock advanceMillis(long millis) {
        now = now.plusMillis(millis);
        return this;
    }
}
