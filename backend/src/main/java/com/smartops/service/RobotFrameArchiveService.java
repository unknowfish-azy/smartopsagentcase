package com.smartops.service;

import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.LocalDate;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 机器人关键帧归档（视觉数据资产的入口）。
 *
 * <p>解决的问题：M2 的 {@link RobotFrameService} 只把帧放在内存里，进程一重启样本就没了，
 * 于是「蒸馏 → 标注 → YOLO 训练」整条链路没有原料。本服务把帧落盘并在
 * {@code robot_frame} 登记元数据，后续 Python 侧直接按表导出即可。</p>
 *
 * <h3>为什么独立线程</h3>
 * 调用方是桥 WS 线程，类注释里写明必须保持空转（否则遥测停发会被心跳看门狗判 FAULT）。
 * 因此 {@link #archive} 只做参数拷贝后提交任务，磁盘与 DB 都在本服务自己的守护线程里做。
 *
 * <h3>幂等与降级</h3>
 * <ul>
 *   <li>落盘路径由 {@code sha256} 决定（{@code <root>/<yyyy-MM-dd>/<device>/<sha256>.jpg}），
 *       同一张图重复回传只写一次；</li>
 *   <li>DB 用 {@code (sha256, device_key)} 唯一键兜底，重复插入不报错；</li>
 *   <li>归档失败只记日志，绝不向上抛——视觉资产不能影响遥控与巡检主链路；</li>
 *   <li>{@code enabled=false} 时 {@link #archive} 直接返回，不创建目录、不连库。</li>
 * </ul>
 */
@Slf4j
@Service
public class RobotFrameArchiveService {

    private final JdbcTemplate jdbc;
    private final boolean enabled;
    private final Path root;
    private final long maxBytes;
    private final ExecutorService executor = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "robot-frame-archive");
        thread.setDaemon(true);
        return thread;
    });

    public RobotFrameArchiveService(JdbcTemplate jdbc,
            @Value("${smartops.robot.frame-archive.enabled:true}") boolean enabled,
            @Value("${smartops.robot.frame-archive.dir:./data/robot-frames}") String dir,
            @Value("${smartops.robot.frame-archive.max-bytes:8388608}") long maxBytes) {
        this.jdbc = jdbc;
        this.enabled = enabled;
        this.root = Paths.get(dir);
        this.maxBytes = maxBytes;
    }

    /** 异步归档一张关键帧；调用方（WS 线程）立即返回。 */
    public void archive(String deviceKey, String target, String imageBase64, Map<String, Object> payload) {
        if (!enabled || deviceKey == null || deviceKey.isBlank() || imageBase64 == null || imageBase64.isBlank()) {
            return;
        }
        Map<String, Object> snapshot = payload == null ? Map.of() : new LinkedHashMap<>(payload);
        executor.submit(() -> {
            try {
                ArchiveResult result = archiveNow(deviceKey, target, imageBase64, snapshot);
                if (!result.stored()) {
                    log.debug("关键帧未归档 device={} 原因={}", deviceKey, result.reason());
                }
            } catch (RuntimeException error) {
                log.warn("关键帧归档失败 device={}：{}", deviceKey, error.getMessage());
            }
        });
    }

    /**
     * 同步归档（供单测与需要确定结果的场景使用）。
     *
     * @return 归档结果；{@code stored=false} 时 reason 说明真实原因，不伪造成功
     */
    ArchiveResult archiveNow(String deviceKey, String target, String imageBase64, Map<String, Object> payload) {
        if (!enabled) {
            return new ArchiveResult(false, "ARCHIVE_DISABLED", null, null);
        }
        byte[] bytes = decode(imageBase64);
        if (bytes.length == 0) {
            return new ArchiveResult(false, "EMPTY_IMAGE", null, null);
        }
        if (bytes.length > maxBytes) {
            // 不截断：截断后的图不可用于训练，宁可跳过并说明
            return new ArchiveResult(false, "TOO_LARGE:" + bytes.length, null, null);
        }

        String sha256 = sha256(bytes);
        Instant capturedAt = Instant.now();
        Path relative = Paths.get(
                LocalDate.now().toString(),
                safeSegment(deviceKey),
                sha256 + extension(payload == null ? null : payload.get("mime")));
        Path absolute = root.resolve(relative);

        try {
            if (!Files.exists(absolute)) {
                Files.createDirectories(absolute.getParent());
                Files.write(absolute, bytes);
            }
        } catch (IOException error) {
            return new ArchiveResult(false, "IO_FAILED:" + error.getMessage(), null, sha256);
        }

        try {
            // 唯一键 (sha256, device_key) 兜底：重复帧不产生新行
            jdbc.update("""
                    INSERT INTO robot_frame(device_key, target, file_path, sha256, bytes,
                        width, height, quality, simulated, captured_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON DUPLICATE KEY UPDATE device_key=VALUES(device_key)
                    """, deviceKey, target, relative.toString().replace('\\', '/'), sha256, bytes.length,
                    intOrNull(payload == null ? null : payload.get("width")),
                    intOrNull(payload == null ? null : payload.get("height")),
                    payload == null || payload.get("quality") == null ? null : String.valueOf(payload.get("quality")),
                    isTrue(payload == null ? null : payload.get("simulated")),
                    java.sql.Timestamp.from(capturedAt));
        } catch (RuntimeException error) {
            // 文件已写、登记失败：保留文件（下次同图会命中已存在分支并重试登记）
            return new ArchiveResult(false, "DB_FAILED:" + error.getMessage(), relative.toString(), sha256);
        }

        return new ArchiveResult(true, "STORED", relative.toString().replace('\\', '/'), sha256);
    }

    /* ── 内部 helpers ─────────────────────────────────────────────────── */

    /** 剥 data URI 前缀后按 base64 解码；非法内容返回空数组而不是抛异常。 */
    private static byte[] decode(String imageBase64) {
        String raw = imageBase64.trim();
        int comma = raw.indexOf(',');
        if (raw.startsWith("data:") && comma > 0) {
            raw = raw.substring(comma + 1);
        }
        try {
            return java.util.Base64.getMimeDecoder().decode(raw);
        } catch (IllegalArgumentException error) {
            return new byte[0];
        }
    }

    private static String sha256(byte[] bytes) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(bytes));
        } catch (java.security.NoSuchAlgorithmException error) {
            // SHA-256 是 JDK 必备算法，不可能缺失；退化为长度哈希避免整条链路中断
            return Integer.toHexString(bytes.length).repeat(8).substring(0, 64);
        }
    }

    private static String extension(Object mime) {
        String value = mime == null ? "" : String.valueOf(mime).toLowerCase();
        if (value.contains("png")) {
            return ".png";
        }
        if (value.contains("webp")) {
            return ".webp";
        }
        return ".jpg";
    }

    /** 目录名只保留安全字符，防止 deviceKey 里出现路径分隔符导致写到目录外。 */
    private static String safeSegment(String value) {
        String cleaned = value.replaceAll("[^A-Za-z0-9._-]", "_");
        return cleaned.isBlank() ? "unknown" : cleaned;
    }

    private static Integer intOrNull(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value instanceof String text) {
            try {
                return Integer.valueOf(text.trim());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private static boolean isTrue(Object value) {
        return value instanceof Boolean bool ? bool : "true".equalsIgnoreCase(String.valueOf(value));
    }

    @PreDestroy
    void shutdown() {
        executor.shutdownNow();
        try {
            executor.awaitTermination(2, TimeUnit.SECONDS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }

    /** 归档结果：stored=false 时必须给出 reason，禁止把跳过伪装成成功。 */
    public record ArchiveResult(boolean stored, String reason, String filePath, String sha256) {
    }
}
