package com.smartops.knowledge;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 本机 Playwright 受控渲染器（T33b）：通过受控 Node 子进程（backend/tools/web-render.mjs）渲染页面。
 *
 * <p>进程隔离：渲染在独立 Node 进程中完成，Java 侧只消费 stdout JSON；超时强制销毁进程。
 * Playwright 复用前端既有依赖，后端不新增安装。渲染器不可用（无 node/脚本）时如实上报，
 * 由调用方返回 RENDERER_UNAVAILABLE，不回退伪造静态正文。</p>
 */
@Component
public class LocalPlaywrightRenderer implements HeadlessRenderer {

    private final String nodeCommand;
    private final Path scriptPath;
    private final Path profileRoot;
    private final long timeoutMs;
    private final int maxContent;
    private final ObjectMapper mapper = new ObjectMapper();
    private final AtomicBoolean availabilityChecked = new AtomicBoolean(false);
    private final AtomicBoolean available = new AtomicBoolean(false);

    public LocalPlaywrightRenderer(
            @Value("${smartops.web-research.render.node-command:node}") String nodeCommand,
            @Value("${smartops.web-research.render.script:tools/web-render.mjs}") String script,
            @Value("${smartops.web-research.render.profile-root:data/web-render-profiles}") String profileRoot,
            @Value("${smartops.web-research.render.timeout-ms:15000}") long timeoutMs,
            @Value("${smartops.web-research.render.max-content:20000}") int maxContent) {
        this.nodeCommand = nodeCommand;
        this.scriptPath = Path.of(script).toAbsolutePath().normalize();
        this.profileRoot = Path.of(profileRoot).toAbsolutePath().normalize();
        this.timeoutMs = timeoutMs;
        this.maxContent = maxContent;
    }

    @Override
    public boolean isAvailable() {
        if (availabilityChecked.compareAndSet(false, true)) {
            boolean scriptExists = Files.isRegularFile(scriptPath);
            boolean nodeExists = run(5_000, nodeCommand, "--version") != null;
            available.set(scriptExists && nodeExists);
        }
        return available.get();
    }

    @Override
    public RenderedPage render(String url, String storageStateJson) {
        requireAvailable();
        Path stateFile = null;
        try {
            if (storageStateJson != null && !storageStateJson.isBlank()) {
                Path profile = profileFor("render");
                Files.createDirectories(profile);
                stateFile = profile.resolve("render-state.json");
                Files.writeString(stateFile, storageStateJson, StandardCharsets.UTF_8);
            }
            String json = runRender(url, stateFile);
            return parsePage(json, url);
        } catch (BusinessException failure) {
            throw failure;
        } catch (Exception failure) {
            throw new BusinessException(502, "WEB_RESEARCH_RENDER_FAILED");
        } finally {
            if (stateFile != null) {
                try { Files.deleteIfExists(stateFile); } catch (IOException ignored) { /* 临时态文件，尽力删除 */ }
            }
        }
    }

    @Override
    public String startLogin(long userId) {
        requireAvailable();
        Path profile = profileFor("user-" + userId);
        try {
            Files.createDirectories(profile);
        } catch (IOException failure) {
            throw new BusinessException(503, "WEB_RENDER_PROFILE_UNWRITABLE");
        }
        Process process = launch(nodeCommand, scriptPath.toString(), "login", profile.toString(),
                "--timeout-ms", String.valueOf(timeoutMs));
        // 有头窗口交给用户操作；进程随窗口关闭退出。不 await——句柄立即返回，finish 时读 state.json。
        ProcessTracker.INSTANCE.register(userId, process);
        return "LOGIN_WINDOW_OPENED";
    }

    @Override
    public String exportLoginState(long userId) {
        Path stateFile = profileFor("user-" + userId).resolve("state.json");
        if (!Files.isRegularFile(stateFile)) return null;
        try {
            String state = Files.readString(stateFile, StandardCharsets.UTF_8);
            JsonNode node = mapper.readTree(state);
            if (!node.isArray() || node.isEmpty()) return null;
            return state;
        } catch (Exception failure) {
            return null;
        }
    }

    /** 会话删除时清理该用户的隔离 profile（含明文 state.json）。 */
    public void wipeProfile(long userId) {
        deleteRecursively(profileFor("user-" + userId));
    }

    private RenderedPage parsePage(String json, String url) throws IOException {
        JsonNode node = mapper.readTree(json);
        if (!node.path("ok").asBoolean(false)) {
            throw new BusinessException(502, node.path("code").asText("WEB_RESEARCH_RENDER_FAILED"));
        }
        String text = node.path("text").asText("");
        if (text.isBlank()) throw new BusinessException(422, "WEB_RESEARCH_EMPTY_CONTENT");
        String title = node.path("title").asText("");
        return new RenderedPage(title, text.length() > maxContent ? text.substring(0, maxContent) : text);
    }

    private String runRender(String url, Path stateFile) throws IOException, InterruptedException {
        ProcessBuilder builder = stateFile == null
                ? new ProcessBuilder(nodeCommand, scriptPath.toString(), "render", url, "--timeout-ms", String.valueOf(timeoutMs))
                : new ProcessBuilder(nodeCommand, scriptPath.toString(), "render", url,
                        "--state", stateFile.toString(), "--timeout-ms", String.valueOf(timeoutMs));
        builder.redirectErrorStream(false);
        Process process = builder.start();
        StringBuilder stdout = new StringBuilder();
        Thread reader = new Thread(() -> {
            try (var input = process.getInputStream()) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    if (stdout.length() < 1_048_576) stdout.append(new String(buffer, 0, read, StandardCharsets.UTF_8));
                }
            } catch (IOException ignored) {
                // 进程被销毁时的管道中断属预期
            }
        });
        reader.setDaemon(true);
        reader.start();
        if (!process.waitFor(timeoutMs + 5_000, TimeUnit.MILLISECONDS)) {
            process.destroyForcibly();
            throw new BusinessException(504, "RENDER_TIMEOUT");
        }
        if (process.exitValue() != 0) {
            String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8);
            if (stderr.contains("RENDER_TIMEOUT")) throw new BusinessException(504, "RENDER_TIMEOUT");
            if (stderr.contains("INVALID_URL")) throw new BusinessException(400, "INVALID_URL");
            throw new BusinessException(502, "WEB_RESEARCH_RENDER_FAILED");
        }
        return stdout.toString();
    }

    private void requireAvailable() {
        if (!isAvailable()) throw new BusinessException(503, "RENDERER_UNAVAILABLE");
    }

    private Path profileFor(String name) {
        return profileRoot.resolve(name);
    }

    private String run(long timeoutMs, String... command) {
        try {
            Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            boolean finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS);
            return finished && process.exitValue() == 0 ? output.trim() : null;
        } catch (Exception failure) {
            return null;
        }
    }

    private Process launch(String... command) {
        try {
            return new ProcessBuilder(command).inheritIO().start();
        } catch (IOException failure) {
            throw new BusinessException(503, "RENDERER_UNAVAILABLE");
        }
    }

    private static void deleteRecursively(Path path) {
        if (path == null || !Files.exists(path)) return;
        try (var paths = Files.walk(path)) {
            paths.sorted((a, b) -> b.compareTo(a)).forEach(p -> {
                try { Files.deleteIfExists(p); } catch (IOException ignored) { /* 尽力删除 */ }
            });
        } catch (IOException ignored) {
            // 尽力删除
        }
    }

    @PreDestroy
    void shutdown() {
        ProcessTracker.INSTANCE.destroyAll();
    }

    /** 登录窗口进程登记：会话删除/应用关闭时强制回收。 */
    private static final class ProcessTracker {
        static final ProcessTracker INSTANCE = new ProcessTracker();
        private final java.util.concurrent.ConcurrentHashMap<Long, Process> processes = new java.util.concurrent.ConcurrentHashMap<>();

        void register(long userId, Process process) {
            Process previous = processes.put(userId, process);
            if (previous != null && previous.isAlive()) previous.destroyForcibly();
        }

        void destroyAll() {
            processes.values().forEach(process -> {
                if (process.isAlive()) process.destroyForcibly();
            });
            processes.clear();
        }
    }
}
