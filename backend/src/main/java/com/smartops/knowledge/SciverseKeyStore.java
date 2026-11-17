package com.smartops.knowledge;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * SciverseKeyStore — SciVerse API Key 的本地持久化（手动配置通道）
 *
 * 职责：把页面「配置密钥」提交的 Key 以 SMARTOPS_SCIVERSE_API_KEY 行的形式
 * upsert 进 backend/.env.local（已被 *.env.local 通配 gitignore，不入库）。
 * 重启链路 scripts/start-backend.ps1 会把 .env.local 全部键注入进程环境，
 * 因此写进该文件即获得「长期保存」语义，无需额外的自研加载机制。
 *
 * 安全红线：不回显完整 Key；日志只落指纹；文件仅本地磁盘。
 */
@Service
public class SciverseKeyStore {

    private static final Logger log = LoggerFactory.getLogger(SciverseKeyStore.class);
    public static final String ENV_VAR = "SMARTOPS_SCIVERSE_API_KEY";

    private final Path file;

    public SciverseKeyStore(
            @Value("${smartops.sciverse.env-local-file:backend/.env.local}") String configuredPath) {
        this.file = resolve(configuredPath == null ? "backend/.env.local" : configuredPath.trim());
        log.info("SCIVERSE keystore file: {}", this.file);
    }

    /**
     * 相对路径解析：兼容两种工作目录（仓库根 / backend）。
     * 运行 jar 时 cwd 通常是 backend（start-backend.ps1），
     * IDE 启动时可能是仓库根。
     */
    private static Path resolve(String configured) {
        Path raw = Paths.get(configured);
        if (raw.isAbsolute()) return raw.normalize();
        String cwd = System.getProperty("user.dir", ".");
        boolean cwdIsBackend = Paths.get(cwd).getFileName() != null
                && "backend".equalsIgnoreCase(Paths.get(cwd).getFileName().toString());
        if (cwdIsBackend) return Paths.get(cwd).resolve(raw.getFileName()).normalize();
        Path underRoot = Paths.get(cwd).resolve(raw).normalize();
        return Files.exists(underRoot) ? underRoot
                : Paths.get(cwd, "backend").resolve(raw.getFileName()).normalize();
    }

    /** 当前进程实际生效的 Key 是否已持久化到磁盘（重启后仍生效）。 */
    public boolean persisted() {
        return readValue() != null;
    }

    /** 读取文件中的 Key（供测试与状态判断）；不存在或未配置返回 null。 */
    public synchronized String readValue() {
        if (!Files.exists(file)) return null;
        try {
            for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
                String trimmed = line.strip();
                if (trimmed.toUpperCase(Locale.ROOT).startsWith(ENV_VAR + "=")) {
                    String value = trimmed.substring(ENV_VAR.length() + 1).strip();
                    if (!value.isEmpty()) return value;
                }
            }
        } catch (IOException failure) {
            log.warn("SCIVERSE keystore read failed: {}", failure.getMessage());
        }
        return null;
    }

    /** upsert：替换已有 SMARTOPS_SCIVERSE_API_KEY 行，不存在则追加。其余行原样保留。 */
    public synchronized void save(String apiKey) {
        try {
            if (file.getParent() != null) Files.createDirectories(file.getParent());
            List<String> lines = Files.exists(file)
                    ? new ArrayList<>(Files.readAllLines(file, StandardCharsets.UTF_8))
                    : new ArrayList<>();
            String newline = ENV_VAR + "=" + apiKey;
            boolean replaced = false;
            List<String> out = new ArrayList<>(lines.size() + 1);
            for (String line : lines) {
                if (line.strip().toUpperCase(Locale.ROOT).startsWith(ENV_VAR + "=") && !replaced) {
                    out.add(newline);
                    replaced = true;
                } else if (!line.strip().toUpperCase(Locale.ROOT).startsWith(ENV_VAR + "=")) {
                    out.add(line);
                }
                // 连续的旧 Key 行只保留第一条替换结果，其余丢弃
            }
            if (!replaced) out.add(newline);
            Files.writeString(file, String.join("\n", out) + "\n", StandardCharsets.UTF_8);
            log.info("SCIVERSE keystore updated: {} (key fingerprint={}…{}, {} chars)",
                    file, apiKey.substring(0, Math.min(6, apiKey.length())),
                    apiKey.substring(Math.max(0, apiKey.length() - 4)), apiKey.length());
        } catch (IOException failure) {
            throw new IllegalStateException("SCIVERSE_KEY_PERSIST_FAILED: " + failure.getMessage(), failure);
        }
    }
}
