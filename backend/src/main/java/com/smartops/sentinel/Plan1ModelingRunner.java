package com.smartops.sentinel;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * 方案一建模脚本执行器：把 STL + 孤立森林 + CUSUM 的离线分析接进 SentinelGuardian 定时链。
 *
 * <p>单例执行器，所有跨语言调用收敛到此一处，按以下纪律避免 ProcessBuilder 经典坑：
 * <ol>
 *   <li>stdout / stderr 用两个独立线程并行消费，防止缓冲区写满死锁；</li>
 *   <li>以退出码驱动分支：0 成功（INFO），非 0 失败（WARN，附 stderr 摘要）；</li>
 *   <li>120 秒硬超时，超时后 {@code destroyForcibly} 并返回可区分的失败结果；</li>
 *   <li>工作目录设为项目根，脚本内用 {@code Path(__file__).resolve().parent.parent} 找 data/ 输出；</li>
 *   <li>所有异常内部消化，绝不向上抛出（Guardian 定时链不应因 Python 崩溃）。</li>
 * </ol>
 *
 * <p>配置项全部有默认值，application-*.yml 里不写也能跑：</p>
 * <pre>
 * smartops.sentinel.modeling.enabled=true
 * smartops.sentinel.modeling.python.executable=python
 * smartops.sentinel.modeling.script=scripts/sentinel_modeling_plan1.py
 * smartops.sentinel.modeling.timeout-sec=120
 * smartops.sentinel.modeling.project-root=.
 * </pre>
 */
@Component
public class Plan1ModelingRunner {

    private static final Logger log = LoggerFactory.getLogger(Plan1ModelingRunner.class);

    /** 执行总开关：false 时 run() 直接返回 0，不启动子进程。 */
    @Value("${smartops.sentinel.modeling.enabled:true}")
    private boolean enabled;

    /** Python 可执行文件名或绝对路径。Windows 上建议填 "python" 或完整路径。 */
    @Value("${smartops.sentinel.modeling.python.executable:python}")
    private String pythonExecutable;

    /** 建模脚本路径，相对于 projectRoot。 */
    @Value("${smartops.sentinel.modeling.script:scripts/sentinel_modeling_plan1.py}")
    private String scriptPath;

    /** 子进程硬超时（秒）。脚本 7 个 metric 实际耗时 ~0.7s，留足余量。 */
    @Value("${smartops.sentinel.modeling.timeout-sec:120}")
    private int timeoutSec;

    /** SmartOpsAgent 项目根目录。默认 "." 对应 backend/ 下启动，需显式指定。 */
    @Value("${smartops.sentinel.modeling.project-root:.}")
    private String projectRoot;

    // 数据库连接参数 —— 跟 Java 应用自己的 datasource 对齐，避免硬编码散落
    @Value("${spring.datasource.host:127.0.0.1}")
    private String dbHost;
    @Value("${spring.datasource.port:3306}")
    private int dbPort;
    @Value("${spring.datasource.username:root}")
    private String dbUser;
    @Value("${spring.datasource.password:password}")
    private String dbPassword;
    @Value("${spring.datasource.database:smartops}")
    private String dbName;

    /**
     * 执行一次建模脚本。返回脚本的"样本数 + 异常数 + 变点数"等综合扫描行数。
     * 任何内部异常都被捕获并返回 0，不破坏 Guardian 定时链。
     */
    public int run() {
        if (!enabled) {
            log.debug("plan1 modeling disabled by config, skip");
            return 0;
        }

        Path root = resolveProjectRoot();
        Path script = root.resolve(scriptPath).toAbsolutePath();
        if (!script.toFile().isFile()) {
            log.warn("plan1 modeling script not found: {} (projectRoot={})", script, root);
            return 0;
        }

        // 拼命令
        List<String> cmd = new ArrayList<>();
        cmd.add(pythonExecutable);
        cmd.add(script.toString());
        cmd.add("--host");      cmd.add(dbHost);
        cmd.add("--port");      cmd.add(String.valueOf(dbPort));
        cmd.add("--user");      cmd.add(dbUser);
        cmd.add("--password");  cmd.add(dbPassword);
        cmd.add("--db");        cmd.add(dbName);

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.directory(root.toFile());
        pb.redirectErrorStream(false); // 分离 stdout/stderr，并行消费
        pb.environment().put("PYTHONUNBUFFERED", "1"); // 实时输出，不让 Python 缓冲

        log.info("plan1 modeling launching: {} (cwd={})", String.join(" ", cmd), root);
        long t0 = System.currentTimeMillis();

        Process proc;
        try {
            proc = pb.start();
        } catch (Exception launchFail) {
            log.warn("plan1 modeling cannot start: {}", launchFail.getMessage());
            return 0;
        }

        // 并行消费 stdout/stderr
        StringBuilder stdoutBuf = new StringBuilder();
        StringBuilder stderrBuf = new StringBuilder();
        Thread stdoutThread = drain(proc.getInputStream(), stdoutBuf);
        Thread stderrThread = drain(proc.getErrorStream(), stderrBuf);

        int exitCode;
        boolean timedOut = false;
        try {
            boolean finished = proc.waitFor(timeoutSec, TimeUnit.SECONDS);
            if (!finished) {
                timedOut = true;
                proc.destroyForcibly();
                // 等一下消费线程退出，避免线程泄漏
                stdoutThread.join(1000);
                stderrThread.join(1000);
                log.warn("plan1 modeling timed out after {}s, killed", timeoutSec);
                return 0;
            }
            exitCode = proc.exitValue();
            // 等消费线程把剩余内容读完
            stdoutThread.join(2000);
            stderrThread.join(2000);
        } catch (InterruptedException ie) {
            proc.destroyForcibly();
            Thread.currentThread().interrupt();
            log.warn("plan1 modeling interrupted");
            return 0;
        }

        long elapsed = System.currentTimeMillis() - t0;
        String stdoutTail = tail(stdoutBuf.toString(), 20);
        String stderrHead = head(stderrBuf.toString(), 20);

        if (timedOut) {
            return 0;
        }
        if (exitCode != 0) {
            log.warn("plan1 modeling exitCode={} ({}ms) stderr: {}", exitCode, elapsed, stderrHead);
            return 0;
        }

        // 成功：解析 stdout 尾部（脚本最后输出了"扫描样本 X / 异常 Y / 变点 Z"）
        // 脚本不输出结构化 JSON，直接记一条聚合 INFO，让运维侧在日志里能检索到
        int samples = extractNumber(stdoutTail, "扫描样本");
        int abnormal = extractNumber(stdoutTail, "孤立森林异常");
        int changepoints = extractNumber(stdoutTail, "CUSUM 变点");
        log.info("plan1 modeling done ({}ms): samples={} abnormal={} changepoints={}",
                elapsed, samples, abnormal, changepoints);
        if (!stderrBuf.isEmpty()) {
            // Python 的警告（⚠️ STL 降级之类）走 stderr，记 DEBUG 方便排查
            log.debug("plan1 modeling stderr tail: {}", tail(stderrBuf.toString(), 10));
        }
        return samples;
    }

    /* ── 工具 ───────────────────────────────────────────────── */

    private Path resolveProjectRoot() {
        // 如果是显式路径（绝对或含盘符），直接用；否则尝试相对于 user.dir
        Path p = Paths.get(projectRoot);
        if (p.isAbsolute()) return p;
        Path userDir = Paths.get(System.getProperty("user.dir"));
        // Spring Boot 用 backend/ 作为 user.dir，往上一层就是 SmartOpsAgent 根
        Path candidate = userDir.resolve(p).normalize();
        if (candidate.toFile().isDirectory()) return candidate;
        // 兜底：再往上一层（backend/ → SmartOpsAgent/）
        Path parent = userDir.getParent();
        if (parent != null) {
            Path parentCandidate = parent.resolve(p).normalize();
            if (parentCandidate.toFile().isDirectory()) return parentCandidate;
        }
        return userDir;
    }

    /** 独立线程把 InputStream 全量 drain 到 StringBuilder，避免缓冲区写满。 */
    private Thread drain(InputStream stream, StringBuilder sink) {
        Thread t = new Thread(() -> {
            try (BufferedReader br = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) {
                    synchronized (sink) {
                        sink.append(line).append('\n');
                    }
                }
            } catch (Exception ignored) {
                // 进程被 destroy 后流可能关闭，忽略
            }
        }, "plan1-modeling-io");
        t.setDaemon(true);
        t.start();
        return t;
    }

    private static String tail(String text, int lines) {
        if (text == null || text.isEmpty()) return "";
        String[] arr = text.split("\n");
        int from = Math.max(0, arr.length - lines);
        return String.join(" | ", java.util.Arrays.asList(arr).subList(from, arr.length));
    }

    private static String head(String text, int lines) {
        if (text == null || text.isEmpty()) return "";
        String[] arr = text.split("\n");
        int to = Math.min(arr.length, lines);
        return String.join(" | ", java.util.Arrays.asList(arr).subList(0, to));
    }

    /** 从脚本 stdout 里把 "扫描样本：911" 这种文本里的数字抠出来。 */
    private static int extractNumber(String text, String label) {
        if (text == null || !text.contains(label)) return 0;
        int idx = text.indexOf(label);
        // 找 label 后第一个数字
        for (int i = idx + label.length(); i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isDigit(c)) {
                int start = i;
                while (i < text.length() && Character.isDigit(text.charAt(i))) i++;
                try {
                    return Integer.parseInt(text.substring(start, i));
                } catch (NumberFormatException nfe) {
                    return 0;
                }
            }
        }
        return 0;
    }
}
