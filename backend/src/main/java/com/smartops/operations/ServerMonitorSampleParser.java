package com.smartops.operations;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 解析采样命令输出。纯静态函数，便于单测；任何一段解析失败只让对应字段为 null，
 * 全部失败才判 unsupported——不做任何数值推测。
 *
 * 采样输出分区格式（见 remote-connections-enhance-v1/DESIGN.md）：
 * ===STAT1 / ===LOAD / ===MEM / ===DISK / ===NET / ===STAT2
 */
public final class ServerMonitorSampleParser {

    private ServerMonitorSampleParser() {
    }

    public static ServerMonitorSample parse(String stdout) {
        if (stdout == null || stdout.isBlank()) return ServerMonitorSample.unsupported("EMPTY_SAMPLING_OUTPUT");
        String stat1 = section(stdout, "===STAT1", "===LOAD");
        String load = section(stdout, "===LOAD", "===MEM");
        String mem = section(stdout, "===MEM", "===DISK");
        String disk = section(stdout, "===DISK", "===NET");
        String net = section(stdout, "===NET", "===STAT2");
        String stat2 = tailSection(stdout, "===STAT2");

        Double cpu = cpuPercent(stat1, stat2);
        Double[] loads = loads(load);
        Long[] memory = memory(mem);
        Long[] diskUsage = disk(disk);
        long[] netBytes = netBytes(net);

        boolean anyParsed = cpu != null || memory[0] != null || diskUsage[0] != null || netBytes[0] >= 0 || loads[0] != null;
        if (!anyParsed) return ServerMonitorSample.unsupported("UNPARSEABLE_SAMPLING_OUTPUT");

        return new ServerMonitorSample(true, null, cpu,
                memory[0], memory[1],
                loads[0], loads[1], loads[2],
                diskUsage[0], diskUsage[1], diskUsage[2],
                diskUsage[3] != null ? diskUsage[3].intValue() : null,
                netBytes[0] >= 0 ? netBytes[0] : null,
                netBytes[1] >= 0 ? netBytes[1] : null,
                Instant.now().toString());
    }

    private static String section(String stdout, String marker, String nextMarker) {
        int start = stdout.indexOf(marker);
        if (start < 0) return null;
        start += marker.length();
        int end = stdout.indexOf(nextMarker, start);
        return (end < 0 ? stdout : stdout.substring(0, end)).substring(start);
    }

    private static String tailSection(String stdout, String marker) {
        int start = stdout.lastIndexOf(marker);
        if (start < 0) return null;
        return stdout.substring(start + marker.length());
    }

    /** /proc/stat 双采样：busy = totalDelta - idleDelta（idle+iowait），钳制 0-100。 */
    static Double cpuPercent(String stat1, String stat2) {
        long[] a = cpuFields(stat1);
        long[] b = cpuFields(stat2);
        if (a == null || b == null || a.length < 5 || b.length < 5) return null;
        int n = Math.min(8, Math.min(a.length, b.length));
        long total = 0;
        long idle = 0;
        for (int i = 0; i < n; i++) {
            long delta = b[i] - a[i];
            if (delta < 0) return null; // 计数器回绕或跨核错位，放弃本次推断
            total += delta;
            if (i == 3 || i == 4) idle += delta; // idle + iowait
        }
        if (total <= 0) return null;
        double busy = (total - idle) * 100.0 / total;
        return Math.max(0d, Math.min(100d, busy));
    }

    private static long[] cpuFields(String statSection) {
        if (statSection == null) return null;
        for (String line : statSection.split("\\n")) {
            String trimmed = line.trim();
            if (trimmed.startsWith("cpu ") || trimmed.startsWith("cpu\t")) {
                String[] parts = trimmed.substring(3).trim().split("\\s+");
                long[] values = new long[parts.length];
                for (int i = 0; i < parts.length; i++) {
                    try {
                        values[i] = Long.parseLong(parts[i]);
                    } catch (NumberFormatException e) {
                        return null;
                    }
                }
                return values;
            }
        }
        return null;
    }

    private static Double[] loads(String loadSection) {
        Double[] result = new Double[3];
        if (loadSection == null) return result;
        for (String line : loadSection.split("\\n")) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            String[] parts = trimmed.split("\\s+");
            for (int i = 0; i < 3 && i < parts.length; i++) {
                try {
                    result[i] = Double.parseDouble(parts[i]);
                } catch (NumberFormatException e) {
                    result[i] = null;
                }
            }
            return result;
        }
        return result;
    }

    /** head -5 /proc/meminfo：MemTotal / MemFree / MemAvailable / Buffers / Cached。 */
    private static Long[] memory(String memSection) {
        Long total = readMemField(memSection, "MemTotal");
        Long available = readMemField(memSection, "MemAvailable");
        return new Long[]{total, available};
    }

    private static Long readMemField(String memSection, String field) {
        if (memSection == null) return null;
        for (String line : memSection.split("\\n")) {
            if (line.startsWith(field + ":")) {
                String[] parts = line.substring(field.length() + 1).trim().split("\\s+");
                if (parts.length == 0) return null;
                try {
                    return Long.parseLong(parts[0]);
                } catch (NumberFormatException e) {
                    return null;
                }
            }
        }
        return null;
    }

    /** df -kP / 末行：Filesystem 1024-blocks Used Available Capacity% Mounted。容量列直接取 OS 口径（used/(used+avail)）。 */
    private static Long[] disk(String diskSection) {
        if (diskSection == null) return new Long[]{null, null, null, null};
        for (String line : diskSection.split("\\n")) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("Filesystem")) continue;
            String[] parts = trimmed.split("\\s+");
            if (parts.length < 5) continue;
            try {
                Long capacity = null;
                String capacityColumn = parts[4].endsWith("%") ? parts[4].substring(0, parts[4].length() - 1) : parts[4];
                capacity = Long.parseLong(capacityColumn);
                return new Long[]{Long.parseLong(parts[1]), Long.parseLong(parts[2]), Long.parseLong(parts[3]), capacity};
            } catch (NumberFormatException e) {
                return new Long[]{null, null, null, null};
            }
        }
        return new Long[]{null, null, null, null};
    }

    /** /proc/net/dev：各接口字节求和（排除 lo）；不存在有效数据时返回 -1。 */
    static long[] netBytes(String netSection) {
        long rx = -1;
        long tx = -1;
        if (netSection != null) {
            for (String line : netSection.split("\\n")) {
                int colon = line.indexOf(':');
                if (colon < 0) continue;
                String iface = line.substring(0, colon).trim();
                if (iface.isEmpty() || "lo".equals(iface)) continue;
                String[] parts = line.substring(colon + 1).trim().split("\\s+");
                if (parts.length < 9) continue;
                try {
                    long ifaceRx = Long.parseLong(parts[0]);
                    long ifaceTx = Long.parseLong(parts[8]);
                    rx = Math.max(rx, 0) + ifaceRx;
                    tx = Math.max(tx, 0) + ifaceTx;
                } catch (NumberFormatException e) {
                    // 单个接口解析失败只跳过该接口
                }
            }
        }
        return new long[]{rx, tx};
    }

    static List<String> sectionNames() {
        return new ArrayList<>(List.of("===STAT1", "===LOAD", "===MEM", "===DISK", "===NET", "===STAT2"));
    }
}
