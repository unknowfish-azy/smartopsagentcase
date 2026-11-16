package com.smartops.operations;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 监控采样解析：全部基于真实 /proc 输出格式，不靠推测。 */
class ServerMonitorSampleParserTest {

    private static final String FIXTURE = """
            ===STAT1
            cpu  1259861 11098 592925 12345678 21452 0 38215 0 0 0
            ===LOAD
            0.52 0.58 0.59 2/1234 54321
            ===MEM
            MemTotal:       16384000 kB
            MemFree:         2452868 kB
            MemAvailable:    8243210 kB
            Buffers:          512000 kB
            Cached:          3980012 kB
            ===DISK
            /dev/sda1 61306604 34567890 23600846 60% /
            ===NET
            Inter-|   Receive                                                |  Transmit
             face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
                lo: 3874210    9123    0    0    0     0          0         0  3874210    9123    0    0    0     0       0          0
              eth0: 915243760  612345    0    0    0     0          0         0 845231120  598112    0    0    0     0       0          0
            ===STAT2
            cpu  1260211 11098 593125 12351778 21502 0 38245 0 0 0
            """;

    @Test
    void parsesRealProcOutput() {
        ServerMonitorSample sample = ServerMonitorSampleParser.parse(FIXTURE);

        assertTrue(sample.supported());
        // CPU busy delta: (350+200+10020+50+30) busy? 计算：total=350+0+200+6100+50+0+30=6730, idle=6100+50=6150, busy=580/6730≈8.62%
        assertEquals(8.62, sample.cpuPercent(), 0.05);
        assertEquals(16384000L, sample.memTotalKb());
        assertEquals(8243210L, sample.memAvailableKb());
        assertEquals(0.52, sample.load1(), 1e-9);
        assertEquals(0.58, sample.load5(), 1e-9);
        assertEquals(0.59, sample.load15(), 1e-9);
        assertEquals(61306604L, sample.diskTotalKb());
        assertEquals(34567890L, sample.diskUsedKb());
        assertEquals(23600846L, sample.diskAvailKb());
        assertEquals(60, sample.diskUsagePercent()); // 直接取 df Capacity 列（used/(used+avail)，OS 口径）
        assertEquals(915243760L, sample.netRxBytes());
        assertEquals(845231120L, sample.netTxBytes());
        assertFalse(sample.netRxBytes() == 3874210L, "lo 接口必须排除");
    }

    @Test
    void clampsCpuToHundredAndRejectsNegativeDelta() {
        Double clamped = ServerMonitorSampleParser.cpuPercent(
                "cpu  0 0 0 100 0 0 0 0", "cpu  0 0 0 101 0 0 0 0");
        assertEquals(0d, clamped);

        assertNull(ServerMonitorSampleParser.cpuPercent(
                "cpu  100 0 0 100 0 0 0 0", "cpu  50 0 0 100 0 0 0 0")); // 计数器回绕
    }

    @Test
    void emptyOrGarbageOutputIsUnsupported() {
        assertFalse(ServerMonitorSampleParser.parse("").supported());
        assertFalse(ServerMonitorSampleParser.parse(null).supported());
        assertEquals("UNPARSEABLE_SAMPLING_OUTPUT", ServerMonitorSampleParser.parse("hello world").reason());
        assertEquals("EMPTY_SAMPLING_OUTPUT", ServerMonitorSampleParser.parse("   ").reason());
    }

    @Test
    void partialSectionsStillSupportedWithNullFields() {
        String partial = "===LOAD\n1.10 0.90 0.80 1/999 222\n===MEM\nMemTotal: 1000 kB\nMemAvailable: 500 kB\n";
        ServerMonitorSample sample = ServerMonitorSampleParser.parse(partial);
        assertTrue(sample.supported());
        assertNull(sample.cpuPercent());
        assertEquals(1000L, sample.memTotalKb());
        assertEquals(1.10, sample.load1(), 1e-9);
        assertNull(sample.diskTotalKb());
        assertNull(sample.netRxBytes());
    }

    @Test
    void skipsInterfacesWithMalformedCounters() {
        long[] bytes = ServerMonitorSampleParser.netBytes(
                "\n  eth0: 100 1 0 0 0 0 0 0 50 1 0 0 0 0 0 0\n  eth1: broken\n");
        assertEquals(100L, bytes[0]);
        assertEquals(50L, bytes[1]);
    }
}
