package com.smartops.runtime;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 本地 AI 能力链（Ollama 运行时 + ai-service）的启停控制。
 *
 * <p>安全约束（缺一不可）：
 * <ul>
 *   <li>只有配置 {@code smartops.runtime.control.enabled=true} 才启用（默认关闭，仅 local profile 打开）</li>
 *   <li>控制器入口要求 ADMIN 角色，且请求来自 loopback</li>
 *   <li>只调用固定脚本，不接收前端传入的任何命令参数</li>
 *   <li>脚本内部按可执行文件路径 / 命令行指纹校验进程，只动本平台的进程</li>
 * </ul>
 * 启动 ai-service 时脚本会从根 .env 注入 CHAT_RUN_TOKEN_SECRET，避免出现
 * CHAT_RUN_TOKEN_NOT_CONFIGURED。
 */
@Slf4j
@Service
public class LocalAiRuntimeService {

    private static final String SCRIPT_RELATIVE = "scripts/windows/ai-runtime-control.ps1";
    private static final long OPERATION_TTL_MS = 180_000L;
    private static final long STATUS_CACHE_MS = 3_000L;

    private final ObjectMapper json = new ObjectMapper();
    private final SecurityAuditService audit;
    private final ReentrantLock operationLock = new ReentrantLock();
    private final ExecutorService executor = Executors.newSingleThreadExecutor(runnable -> {
        Thread thread = new Thread(runnable, "ai-runtime-control");
        thread.setDaemon(true);
        return thread;
    });

    @Value("${smartops.runtime.control.enabled:false}")
    private boolean enabled;

    @Value("${smartops.runtime.control.status-timeout-sec:25}")
    private int statusTimeoutSec;

    @Value("${smartops.runtime.control.start-timeout-sec:180}")
    private int startTimeoutSec;

    private volatile Operation operation;
    private volatile Map<String, Object> cachedRaw;
    private volatile long cachedAt;
    private volatile Path projectRoot;

    public LocalAiRuntimeService(SecurityAuditService audit) {
        this.audit = audit;
    }

    /** 一次启停操作的状态，供前端轮询展示过渡态。 */
    public record Operation(String action, String state, long startedAt, String message) {}

    public boolean enabled() {
        return enabled;
    }

    public Map<String, Object> status(boolean admin) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("controlEnabled", enabled);
        result.put("controllable", enabled && admin);
        if (!enabled) {
            result.put("state", "disabled");
            result.put("message", "本地运行控制未开启（仅 local profile 可用）");
            return result;
        }
        Map<String, Object> raw = rawStatus();
        Object services = raw.get("state");
        Map<?, ?> state = services instanceof Map<?, ?> map ? map : Map.of();
        result.put("ollama", state.get("ollama"));
        result.put("aiService", state.get("aiService"));
        result.put("state", deriveState(state));
        result.put("operation", operation);
        result.put("message", raw.getOrDefault("message", ""));
        return result;
    }

    public Map<String, Object> start(SessionUser actor) {
        return trigger(actor, "start", startTimeoutSec);
    }

    public Map<String, Object> stop(SessionUser actor) {
        return trigger(actor, "stop", 45);
    }

    private Map<String, Object> trigger(SessionUser actor, String action, int timeoutSec) {
        if (!enabled) {
            throw new IllegalStateException("本地运行控制未开启");
        }
        if (!operationLock.tryLock()) {
            throw new IllegalStateException("已有运行时操作正在进行，请稍候");
        }
        String auditAction = "AI_RUNTIME_" + action.toUpperCase(Locale.ROOT);
        Operation started = new Operation(action, "start".equals(action) ? "starting" : "stopping", System.currentTimeMillis(), "");
        operation = started;
        audit.record(actor, auditAction, "ai-chain", "PENDING", "");
        executor.submit(() -> {
            try {
                Map<String, Object> raw = runScript(action, timeoutSec);
                boolean ok = Boolean.TRUE.equals(raw.get("ok"));
                String message = String.valueOf(raw.getOrDefault("message", ""));
                operation = new Operation(action, ok ? "completed" : "error", started.startedAt(), message);
                audit.record(actor, auditAction, "ai-chain", ok ? "SUCCESS" : "FAILURE", message);
                if (!ok) {
                    log.warn("ai runtime {} finished with failure: {}", action, message);
                }
            } catch (Exception failure) {
                operation = new Operation(action, "error", started.startedAt(), failure.getMessage());
                audit.record(actor, auditAction, "ai-chain", "FAILURE", String.valueOf(failure.getMessage()));
                log.warn("ai runtime {} failed", action, failure);
            } finally {
                cachedRaw = null;
                cachedAt = 0L;
                operationLock.unlock();
            }
        });
        return Map.of("accepted", true, "operation", operation);
    }

    private String deriveState(Map<?, ?> services) {
        Operation current = operation;
        if (current != null && System.currentTimeMillis() - current.startedAt() < OPERATION_TTL_MS
                && ("starting".equals(current.state()) || "stopping".equals(current.state()))) {
            return current.state();
        }
        boolean aiRunning = Boolean.TRUE.equals(read(services.get("aiService"), "running"));
        boolean ollamaRunning = Boolean.TRUE.equals(read(services.get("ollama"), "running"));
        boolean modelReady = Boolean.TRUE.equals(read(services.get("ollama"), "modelReady"));
        if (aiRunning && ollamaRunning && modelReady) return "running";
        if (!aiRunning && !ollamaRunning) return "stopped";
        return "partial";
    }

    private static Object read(Object source, String key) {
        return source instanceof Map<?, ?> map ? map.get(key) : null;
    }

    private Map<String, Object> rawStatus() {
        long now = System.currentTimeMillis();
        Map<String, Object> snapshot = cachedRaw;
        if (snapshot != null && now - cachedAt < STATUS_CACHE_MS) {
            return snapshot;
        }
        try {
            Map<String, Object> fresh = runScript("status", statusTimeoutSec);
            cachedRaw = fresh;
            cachedAt = now;
            return fresh;
        } catch (Exception failure) {
            log.warn("ai runtime status probe failed: {}", failure.getMessage());
            Map<String, Object> fallback = new LinkedHashMap<>();
            fallback.put("ok", false);
            fallback.put("message", String.valueOf(failure.getMessage()));
            fallback.put("state", Map.of());
            return fallback;
        }
    }

    private Map<String, Object> runScript(String action, int timeoutSec) {
        Path root = projectRoot();
        Path script = root.resolve(SCRIPT_RELATIVE);
        if (!Files.isRegularFile(script)) {
            throw new IllegalStateException("找不到运行时控制脚本：" + script);
        }
        List<String> command = List.of("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", script.toString(), "-Action", action);
        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(root.toFile());
        Process process;
        try {
            process = builder.start();
        } catch (IOException launchFailure) {
            throw new IllegalStateException("无法启动 PowerShell：" + launchFailure.getMessage(), launchFailure);
        }
        StringBuilder stdout = new StringBuilder();
        StringBuilder stderr = new StringBuilder();
        Thread outDrain = drain(process.getInputStream(), stdout);
        Thread errDrain = drain(process.getErrorStream(), stderr);
        try {
            if (!process.waitFor(timeoutSec, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                throw new IllegalStateException("运行时控制脚本超时（" + timeoutSec + " 秒）");
            }
            outDrain.join(2_000);
            errDrain.join(2_000);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw new IllegalStateException("运行时控制被中断", interrupted);
        }
        String text = stdout.toString().trim();
        if (text.isEmpty()) {
            throw new IllegalStateException("控制脚本无输出：" + stderr.toString().trim());
        }
        String lastLine = text.substring(text.lastIndexOf('\n') + 1).trim();
        try {
            return json.readValue(lastLine, Map.class);
        } catch (Exception parseFailure) {
            throw new IllegalStateException("控制脚本输出无法解析：" + lastLine, parseFailure);
        }
    }

    private static Thread drain(InputStream stream, StringBuilder sink) {
        Thread thread = new Thread(() -> {
            try (InputStream input = stream) {
                byte[] buffer = new byte[4096];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    synchronized (sink) {
                        sink.append(new String(buffer, 0, read, StandardCharsets.UTF_8));
                    }
                }
            } catch (IOException ignored) {
                // 子进程被强杀时读流会抛异常，忽略即可
            }
        }, "ai-runtime-script-drain");
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    private Path projectRoot() {
        Path cached = projectRoot;
        if (cached != null) {
            return cached;
        }
        Path directory = Paths.get(System.getProperty("user.dir")).toAbsolutePath();
        for (int depth = 0; depth < 6 && directory != null; depth++) {
            if (Files.isRegularFile(directory.resolve(SCRIPT_RELATIVE))) {
                projectRoot = directory;
                return directory;
            }
            directory = directory.getParent();
        }
        throw new IllegalStateException("无法定位项目根目录（未找到 " + SCRIPT_RELATIVE + "）");
    }

    @PreDestroy
    void shutdown() {
        executor.shutdownNow();
    }
}
