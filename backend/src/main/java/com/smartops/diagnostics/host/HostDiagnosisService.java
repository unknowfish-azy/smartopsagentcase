package com.smartops.diagnostics.host;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 主机、中间件与 Java 诊断包（OPS-08）。
 *
 * <p><b>结论口径</b>：{@code OK} 只能来自“确实采到了证据且检查通过”。命令不存在、
 * 权限不足、输出不可解析一律不得写成 OK：命令不存在记为 {@code UNVERIFIED}，stderr 匹配
 * forbidden / Permission denied / not permitted 记为 {@code UNVERIFIED}（权限不足），
 * 命令成功但输出为空或不可解析记为 {@code DATA_MISSING}，目标组件不存在（无 redis/nginx/java
 * 进程、非 systemd 系统）记为 {@code NOT_APPLICABLE}。</p>
 *
 * <p>所有命令均为只读（vmstat/df/free/systemctl 状态查询、redis-cli info、jcmd/jstat 等），
 * 单条命令 10s 超时，整单最多 14 条命令并受 60s 总预算约束。预算耗尽时置
 * {@code truncated=true} 并停止发起新命令，不把“没采完”当成“采完了且没问题”。</p>
 *
 * <p>evidence 一律压缩成单行且不超过 300 字：禁止整段 dump 日志、线程栈与 nginx 配置，
 * JVM 检查只保留线程数、堆/老年代占比等聚合数值。</p>
 */
@Service
public class HostDiagnosisService {

    static final long COMMAND_TIMEOUT_MS = 10_000L;
    static final int MAX_COMMANDS = 14;
    static final long TOTAL_TIMEOUT_MS = 60_000L;
    static final int MAX_EVIDENCE_LENGTH = 300;
    static final int MAX_JVM_PIDS = 2;

    static final String STATUS_OK = "OK";
    static final String STATUS_WARNING = "WARNING";
    static final String STATUS_FAILED = "FAILED";
    static final String STATUS_NOT_APPLICABLE = "NOT_APPLICABLE";
    static final String STATUS_UNVERIFIED = "UNVERIFIED";
    static final String STATUS_DATA_MISSING = "DATA_MISSING";

    static final String OVERALL_INCOMPLETE = "INCOMPLETE";

    private static final String CHECK_CPU = "CPU";
    private static final String CHECK_LOAD = "LOAD";
    private static final String CHECK_MEMORY = "MEMORY";
    private static final String CHECK_DISK = "DISK";
    private static final String CHECK_IO = "IO";
    private static final String CHECK_SYSTEMD = "SYSTEMD";
    private static final String CHECK_TIME_SYNC = "TIME_SYNC";
    private static final String CHECK_REDIS_REPLICATION = "REDIS_REPLICATION";
    private static final String CHECK_REDIS_PERSISTENCE = "REDIS_PERSISTENCE";
    private static final String CHECK_NGINX_UPSTREAM = "NGINX_UPSTREAM";
    private static final String CHECK_JVM = "JVM";

    private static final String NO_PERMISSION_EVIDENCE = "权限不足，未核验";
    private static final String BUDGET_EXHAUSTED_EVIDENCE = "命令预算或整单超时已耗尽，本项未核验";

    private static final Pattern PERMISSION_ERROR =
            Pattern.compile("forbidden|Permission denied|not permitted", Pattern.CASE_INSENSITIVE);
    private static final Pattern COMMAND_UNAVAILABLE =
            Pattern.compile("command not found|not recognized", Pattern.CASE_INSENSITIVE);
    private static final Pattern NON_SYSTEMD = Pattern.compile(
            "System has not been booted with systemd|Failed to connect to bus|Running in chroot"
                    + "|command not found",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern TOP_CPU = Pattern.compile(
            "([0-9]+(?:\\.[0-9]+)?)%?\\s*us,\\s*([0-9]+(?:\\.[0-9]+)?)%?\\s*sy,.*?"
                    + "([0-9]+(?:\\.[0-9]+)?)%?\\s*wa");
    private static final Pattern REDIS_PORT = Pattern.compile("--port\\s+(\\d+)");
    private static final Pattern HEAP_USAGE = Pattern.compile("total\\s+(\\d+)K,\\s+used\\s+(\\d+)K");
    private static final Pattern LEAP_STATUS = Pattern.compile("Leap status\\s*:\\s*(\\S+)");
    private static final Pattern NGINX_VERSION = Pattern.compile("nginx version", Pattern.CASE_INSENSITIVE);

    private final OperationRuntimeRegistry registry;

    public HostDiagnosisService(OperationRuntimeRegistry registry) {
        this.registry = registry;
    }

    public HostDiagnosisResult diagnose(Long userId, HostDiagnosisRequest request) {
        OperationRuntime runtime = registry.requireOwned(request.runtimeId(), userId);
        if (!runtime.isOpen()) throw new BusinessException(409, "RUNTIME_CLOSED");

        Instant startedAt = Instant.now();
        Run run = new Run(runtime, request, startedAt);
        List<HostCheck> checks = new ArrayList<>(11);

        checks.add(checkCpu(run));
        checks.add(checkLoad(run));
        checks.add(checkMemory(run));
        checks.add(checkDisk(run));
        checks.add(checkIo(run));
        checks.add(checkSystemd(run));
        checks.add(checkTimeSync(run));
        Integer redisPort = collectRedisReplication(run, checks);
        checks.add(checkRedisPersistence(run, redisPort));
        checks.add(checkNginx(run));
        checks.add(checkJvm(run));

        Instant endedAt = Instant.now();
        boolean anyFailed = checks.stream().anyMatch(c -> STATUS_FAILED.equals(c.status()));
        boolean anyWarning = checks.stream().anyMatch(c -> STATUS_WARNING.equals(c.status()));
        boolean anyUnverified = checks.stream().anyMatch(c -> STATUS_UNVERIFIED.equals(c.status()));
        String overallStatus = anyFailed ? STATUS_FAILED
                : anyWarning ? STATUS_WARNING
                : anyUnverified ? OVERALL_INCOMPLETE : STATUS_OK;
        HostScope scope = new HostScope(request.runtimeId(), request.sampleSeconds());
        return new HostDiagnosisResult(scope, startedAt.toString(), endedAt.toString(),
                Duration.between(startedAt, endedAt).toMillis(), List.copyOf(checks),
                overallStatus, anyUnverified, run.truncated);
    }

    /* ── 采集项 ─────────────────────────────────────────────────────────── */

    private HostCheck checkCpu(Run run) {
        int samples = samples(run.request);
        String sampleWindow = samples + "s";
        List<String> commands = new ArrayList<>();
        String vmstat = "vmstat 1 " + samples;
        commands.add(vmstat);
        Execution execution = run.execute(vmstat);
        if (execution == null) {
            return check(CHECK_CPU, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    sampleWindow, Instant.now());
        }
        if (isPermissionDenied(execution)) {
            return check(CHECK_CPU, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    sampleWindow, execution.collectedAt());
        }
        double[] vm = execution.exitCode() == 0 ? parseVmstat(execution.stdout()) : null;
        if (vm != null) {
            String evidence = "r=" + (long) vm[0] + " us=" + fmt(vm[1]) + " sy=" + fmt(vm[2])
                    + " wa=" + fmt(vm[3]);
            String status = (vm[1] + vm[2] > 90 || vm[3] > 30) ? STATUS_WARNING : STATUS_OK;
            return check(CHECK_CPU, status, commands, evidence, sampleWindow, execution.collectedAt());
        }

        // vmstat 不存在或无输出：用 top 单帧补证
        String top = "top -bn1 | head -n 5";
        commands.add(top);
        Execution topExecution = run.execute(top);
        if (topExecution == null) {
            return check(CHECK_CPU, STATUS_UNVERIFIED, commands,
                    "vmstat 不可用且命令预算耗尽，CPU 未核验", sampleWindow, Instant.now());
        }
        if (isPermissionDenied(topExecution)) {
            return check(CHECK_CPU, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    sampleWindow, topExecution.collectedAt());
        }
        double[] topCpu = topExecution.exitCode() == 0 ? parseTop(topExecution.stdout()) : null;
        if (topCpu != null) {
            String evidence = "（来源 top 单帧）us=" + fmt(topCpu[1]) + " sy=" + fmt(topCpu[2])
                    + " wa=" + fmt(topCpu[3]);
            String status = (topCpu[1] + topCpu[2] > 90 || topCpu[3] > 30)
                    ? STATUS_WARNING : STATUS_OK;
            return check(CHECK_CPU, status, commands, evidence, sampleWindow,
                    topExecution.collectedAt());
        }
        return check(CHECK_CPU, STATUS_UNVERIFIED, commands,
                "vmstat 与 top 均不可用，CPU 未核验", sampleWindow, topExecution.collectedAt());
    }

    private HostCheck checkLoad(Run run) {
        List<String> commands = new ArrayList<>();
        String loadavg = "cat /proc/loadavg";
        commands.add(loadavg);
        Execution loadExecution = run.execute(loadavg);
        if (loadExecution == null) {
            return check(CHECK_LOAD, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    null, Instant.now());
        }
        if (isPermissionDenied(loadExecution)) {
            return check(CHECK_LOAD, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, loadExecution.collectedAt());
        }
        Instant collectedAt = loadExecution.collectedAt();
        String nproc = "nproc";
        commands.add(nproc);
        Execution nprocExecution = run.execute(nproc);
        if (nprocExecution == null) {
            return check(CHECK_LOAD, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    null, Instant.now());
        }
        collectedAt = nprocExecution.collectedAt();
        if (isPermissionDenied(nprocExecution)) {
            return check(CHECK_LOAD, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, collectedAt);
        }
        Double load1 = loadExecution.exitCode() == 0
                ? firstDouble(loadExecution.stdout()) : null;
        Integer cores = nprocExecution.exitCode() == 0 ? firstInt(nprocExecution.stdout()) : null;
        if (load1 == null || cores == null || cores <= 0) {
            return check(CHECK_LOAD, STATUS_DATA_MISSING, commands,
                    "loadavg 或核数输出为空/不可解析，LOAD 未核验", null, collectedAt);
        }
        double ratio = load1 / cores;
        String evidence = "load1=" + fmt(load1) + " cores=" + cores + " ratio=" + fmt(ratio);
        String status = ratio > 3 ? STATUS_FAILED : ratio > 1.5 ? STATUS_WARNING : STATUS_OK;
        return check(CHECK_LOAD, status, commands, evidence, null, collectedAt);
    }

    private HostCheck checkMemory(Run run) {
        String command = "free -m";
        List<String> commands = new ArrayList<>(List.of(command));
        Execution execution = run.execute(command);
        if (execution == null) {
            return check(CHECK_MEMORY, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    null, Instant.now());
        }
        if (isPermissionDenied(execution)) {
            return check(CHECK_MEMORY, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, execution.collectedAt());
        }
        long[] mem = execution.exitCode() == 0 ? parseFree(execution.stdout()) : null;
        if (mem == null) {
            return check(CHECK_MEMORY, STATUS_DATA_MISSING, commands,
                    "free 输出为空/不可解析，MEMORY 未核验", null, execution.collectedAt());
        }
        long total = mem[0];
        long available = mem[1];
        long swapTotal = mem[2];
        long swapUsed = mem[3];
        double availablePct = available * 100.0 / total;
        double swapUsedPct = swapTotal > 0 ? swapUsed * 100.0 / swapTotal : 0;
        String evidence = "memTotal=" + total + "MB available=" + available + "MB("
                + fmt(availablePct) + "%) swapUsed=" + fmt(swapUsedPct) + "%";
        String status = STATUS_OK;
        if (availablePct < 5) {
            status = STATUS_FAILED;
        } else if (availablePct < 10 || swapUsedPct > 50) {
            status = STATUS_WARNING;
        }
        return check(CHECK_MEMORY, status, commands, evidence, null, execution.collectedAt());
    }

    private HostCheck checkDisk(Run run) {
        List<String> commands = new ArrayList<>();
        String df = "df -P";
        commands.add(df);
        Execution dfExecution = run.execute(df);
        if (dfExecution == null) {
            return check(CHECK_DISK, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    null, Instant.now());
        }
        if (isPermissionDenied(dfExecution)) {
            return check(CHECK_DISK, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, dfExecution.collectedAt());
        }
        Instant collectedAt = dfExecution.collectedAt();
        List<String[]> mounts = dfExecution.exitCode() == 0
                ? parseDf(dfExecution.stdout()) : List.of();

        String dfInode = "df -iP";
        commands.add(dfInode);
        Execution inodeExecution = run.execute(dfInode);
        if (inodeExecution == null) {
            return check(CHECK_DISK, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    null, Instant.now());
        }
        collectedAt = inodeExecution.collectedAt();
        if (isPermissionDenied(inodeExecution)) {
            return check(CHECK_DISK, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, collectedAt);
        }
        List<String[]> inodes = inodeExecution.exitCode() == 0
                ? parseDf(inodeExecution.stdout()) : List.of();
        if (mounts.isEmpty() && inodes.isEmpty()) {
            return check(CHECK_DISK, STATUS_DATA_MISSING, commands,
                    "df 输出为空/不可解析，DISK 未核验", null, collectedAt);
        }

        int maxUse = maxPct(mounts);
        int maxInode = maxPct(inodes);
        List<String> hot = new ArrayList<>();
        for (String[] mount : mounts) {
            if (Integer.parseInt(mount[1]) >= 90 && hot.size() < 3) {
                hot.add(mount[0] + ":" + mount[1] + "%");
            }
        }
        for (String[] inode : inodes) {
            if (Integer.parseInt(inode[1]) >= 90 && hot.size() < 3) {
                hot.add(inode[0] + ":inode=" + inode[1] + "%");
            }
        }
        String evidence = "maxUse=" + maxUse + "% maxInodeUse=" + maxInode + "%"
                + (hot.isEmpty() ? "" : " hot=" + String.join(",", hot));
        String status = maxUse >= 95 ? STATUS_FAILED
                : (maxUse >= 90 || maxInode >= 90) ? STATUS_WARNING : STATUS_OK;
        return check(CHECK_DISK, status, commands, evidence, null, collectedAt);
    }

    private HostCheck checkIo(Run run) {
        String command = "iostat -x 1 2";
        String sampleWindow = "2s";
        List<String> commands = new ArrayList<>(List.of(command));
        Execution execution = run.execute(command);
        if (execution == null) {
            return check(CHECK_IO, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    sampleWindow, Instant.now());
        }
        if (isPermissionDenied(execution)) {
            return check(CHECK_IO, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    sampleWindow, execution.collectedAt());
        }
        if (execution.exitCode() != 0
                || isUnavailable(execution) || execution.stdout().isBlank()) {
            return check(CHECK_IO, STATUS_UNVERIFIED, commands,
                    "iostat 不存在（sysstat 未安装），IO 未核验；vmstat 的 wa 仅供参考，不作 IO 结论",
                    sampleWindow, execution.collectedAt());
        }
        List<IoRow> rows = parseIostat(execution.stdout());
        if (rows.isEmpty()) {
            return check(CHECK_IO, STATUS_DATA_MISSING, commands,
                    "iostat 输出不可解析，IO 未核验", sampleWindow, execution.collectedAt());
        }
        double maxUtil = 0;
        double maxAwait = 0;
        List<String> hot = new ArrayList<>();
        for (IoRow row : rows) {
            maxUtil = Math.max(maxUtil, row.util());
            maxAwait = Math.max(maxAwait, row.await());
            if ((row.util() > 80 || row.await() > 50) && hot.size() < 3) {
                hot.add(row.device() + "(util=" + fmt(row.util()) + ",await=" + fmt(row.await()) + ")");
            }
        }
        String evidence = "devices=" + rows.size() + " maxUtil=" + fmt(maxUtil)
                + " maxAwait=" + fmt(maxAwait)
                + (hot.isEmpty() ? "" : " hot=" + String.join(",", hot));
        String status = (maxUtil > 80 || maxAwait > 50) ? STATUS_WARNING : STATUS_OK;
        return check(CHECK_IO, status, commands, evidence, sampleWindow, execution.collectedAt());
    }

    private HostCheck checkSystemd(Run run) {
        List<String> commands = new ArrayList<>();
        String failed = "systemctl --failed --no-pager --plain";
        commands.add(failed);
        Execution execution = run.execute(failed);
        if (execution == null) {
            return check(CHECK_SYSTEMD, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    null, Instant.now());
        }
        String combined = (execution.stdout() + " " + execution.stderr()).trim();
        if (NON_SYSTEMD.matcher(combined).find()) {
            return check(CHECK_SYSTEMD, STATUS_NOT_APPLICABLE, commands,
                    "目标主机非 systemd 环境，本项不适用", null, execution.collectedAt());
        }
        if (isPermissionDenied(execution)) {
            return check(CHECK_SYSTEMD, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, execution.collectedAt());
        }
        Instant collectedAt = execution.collectedAt();
        List<String> failedUnits = execution.exitCode() == 0
                ? parseFailedUnits(execution.stdout()) : List.of();

        String running = "systemctl is-system-running";
        commands.add(running);
        Execution runningExecution = run.execute(running);
        boolean degraded = false;
        if (runningExecution != null) {
            collectedAt = runningExecution.collectedAt();
            if (isPermissionDenied(runningExecution)) {
                return check(CHECK_SYSTEMD, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                        null, collectedAt);
            }
            degraded = "degraded".equals(runningExecution.stdout().trim());
        }
        if (!failedUnits.isEmpty()) {
            String evidence = "failed units: "
                    + String.join(", ", failedUnits.subList(0, Math.min(5, failedUnits.size())))
                    + "（共 " + failedUnits.size() + " 个）";
            return check(CHECK_SYSTEMD, STATUS_FAILED, commands, evidence, null, collectedAt);
        }
        if (degraded) {
            return check(CHECK_SYSTEMD, STATUS_WARNING, commands,
                    "is-system-running=degraded 但无 failed unit", null, collectedAt);
        }
        return check(CHECK_SYSTEMD, STATUS_OK, commands,
                "failed units=0 state=" + (runningExecution == null ? "unknown"
                        : runningExecution.stdout().trim()),
                null, collectedAt);
    }

    private HostCheck checkTimeSync(Run run) {
        List<String> commands = new ArrayList<>();
        String timedatectl = "timedatectl show -p NTPSynchronized --value";
        commands.add(timedatectl);
        Execution execution = run.execute(timedatectl);
        if (execution == null) {
            return check(CHECK_TIME_SYNC, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    null, Instant.now());
        }
        if (isPermissionDenied(execution)) {
            return check(CHECK_TIME_SYNC, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, execution.collectedAt());
        }
        String value = execution.stdout().trim().toLowerCase(Locale.ROOT);
        if (execution.exitCode() == 0 && ("yes".equals(value) || "no".equals(value))) {
            return check(CHECK_TIME_SYNC, "yes".equals(value) ? STATUS_OK : STATUS_WARNING,
                    commands, "NTPSynchronized=" + value, null, execution.collectedAt());
        }
        if (execution.exitCode() == 0 && !isUnavailable(execution) && !value.isEmpty()) {
            return check(CHECK_TIME_SYNC, STATUS_DATA_MISSING, commands,
                    "timedatectl 输出不可解析: " + value, null, execution.collectedAt());
        }

        // timedatectl 不存在：用 chronyc 补证
        String chronyc = "chronyc tracking 2>/dev/null | head -n 20";
        commands.add(chronyc);
        Execution chronyExecution = run.execute(chronyc);
        if (chronyExecution == null) {
            return check(CHECK_TIME_SYNC, STATUS_UNVERIFIED, commands,
                    "timedatectl 不可用且命令预算耗尽，TIME_SYNC 未核验", null, Instant.now());
        }
        if (isPermissionDenied(chronyExecution)) {
            return check(CHECK_TIME_SYNC, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    null, chronyExecution.collectedAt());
        }
        Matcher leap = chronyExecution.exitCode() == 0
                ? LEAP_STATUS.matcher(chronyExecution.stdout()) : null;
        if (leap != null && leap.find()) {
            String status = leap.group(1);
            return check(CHECK_TIME_SYNC,
                    "Normal".equals(status) ? STATUS_OK : STATUS_WARNING, commands,
                    "（来源 chronyc）Leap status=" + status, null, chronyExecution.collectedAt());
        }
        return check(CHECK_TIME_SYNC, STATUS_UNVERIFIED, commands,
                "timedatectl 与 chronyc 均不可用，TIME_SYNC 未核验", null,
                chronyExecution.collectedAt());
    }

    /**
     * 采集 REDIS_REPLICATION；返回探测到的 redis 端口供持久化检查复用，无 redis 时返回 null。
     */
    private Integer collectRedisReplication(Run run, List<HostCheck> checks) {
        List<String> commands = new ArrayList<>();
        String pgrep = "pgrep -a redis-server | head -n 5";
        commands.add(pgrep);
        Execution pgrepExecution = run.execute(pgrep);
        if (pgrepExecution == null) {
            checks.add(check(CHECK_REDIS_REPLICATION, STATUS_UNVERIFIED, commands,
                    BUDGET_EXHAUSTED_EVIDENCE, null, Instant.now()));
            return null;
        }
        if (isPermissionDenied(pgrepExecution)) {
            checks.add(check(CHECK_REDIS_REPLICATION, STATUS_UNVERIFIED, commands,
                    NO_PERMISSION_EVIDENCE, null, pgrepExecution.collectedAt()));
            return null;
        }
        if (pgrepExecution.exitCode() != 0 || pgrepExecution.stdout().isBlank()) {
            checks.add(check(CHECK_REDIS_REPLICATION, STATUS_NOT_APPLICABLE, commands,
                    "未发现 redis-server 进程，本项不适用", null, pgrepExecution.collectedAt()));
            return null;
        }
        int port = redisPort(pgrepExecution.stdout());

        String info = "redis-cli -h 127.0.0.1 -p " + port + " --no-auth-warning info replication";
        commands.add(info);
        Execution infoExecution = run.execute(info);
        if (infoExecution == null) {
            checks.add(check(CHECK_REDIS_REPLICATION, STATUS_UNVERIFIED, commands,
                    BUDGET_EXHAUSTED_EVIDENCE, null, Instant.now()));
            return port;
        }
        if (isPermissionDenied(infoExecution)) {
            checks.add(check(CHECK_REDIS_REPLICATION, STATUS_UNVERIFIED, commands,
                    NO_PERMISSION_EVIDENCE, null, infoExecution.collectedAt()));
            return port;
        }
        if (infoExecution.exitCode() != 0 || isUnavailable(infoExecution)) {
            checks.add(check(CHECK_REDIS_REPLICATION, STATUS_UNVERIFIED, commands,
                    "redis-cli 不存在或执行失败，复制状态未核验", null, infoExecution.collectedAt()));
            return port;
        }
        Map<String, String> kv = parseRedisInfo(infoExecution.stdout());
        String role = kv.get("role");
        if (role == null) {
            checks.add(check(CHECK_REDIS_REPLICATION, STATUS_DATA_MISSING, commands,
                    "info replication 输出为空/不可解析", null, infoExecution.collectedAt()));
            return port;
        }
        String status = STATUS_OK;
        String evidence;
        if ("master".equals(role)) {
            evidence = "port=" + port + " role=master connected_slaves="
                    + kv.getOrDefault("connected_slaves", "unknown");
        } else {
            String linkStatus = kv.getOrDefault("master_link_status", "unknown");
            long lastIo = longOf(kv.get("master_last_io_seconds_ago"), -1);
            evidence = "port=" + port + " role=" + role + " master_link_status=" + linkStatus
                    + " master_last_io_seconds_ago=" + lastIo;
            if ("down".equals(linkStatus)) {
                status = STATUS_FAILED;
            } else if (lastIo > 10) {
                status = STATUS_WARNING;
            }
        }
        checks.add(check(CHECK_REDIS_REPLICATION, status, commands, evidence, null,
                infoExecution.collectedAt()));
        return port;
    }

    private HostCheck checkRedisPersistence(Run run, Integer redisPort) {
        if (redisPort == null) {
            return check(CHECK_REDIS_PERSISTENCE, STATUS_NOT_APPLICABLE,
                    List.of(), "未发现 redis-server 进程，本项不适用", null, Instant.now());
        }
        String command = "redis-cli -h 127.0.0.1 -p " + redisPort
                + " --no-auth-warning info persistence";
        List<String> commands = new ArrayList<>(List.of(command));
        Execution execution = run.execute(command);
        if (execution == null) {
            return check(CHECK_REDIS_PERSISTENCE, STATUS_UNVERIFIED, commands,
                    BUDGET_EXHAUSTED_EVIDENCE, null, Instant.now());
        }
        if (isPermissionDenied(execution)) {
            return check(CHECK_REDIS_PERSISTENCE, STATUS_UNVERIFIED, commands,
                    NO_PERMISSION_EVIDENCE, null, execution.collectedAt());
        }
        if (execution.exitCode() != 0 || isUnavailable(execution)) {
            return check(CHECK_REDIS_PERSISTENCE, STATUS_UNVERIFIED, commands,
                    "redis-cli 不存在或执行失败，持久化状态未核验", null, execution.collectedAt());
        }
        Map<String, String> kv = parseRedisInfo(execution.stdout());
        if (kv.isEmpty()) {
            return check(CHECK_REDIS_PERSISTENCE, STATUS_DATA_MISSING, commands,
                    "info persistence 输出为空/不可解析", null, execution.collectedAt());
        }
        String rdb = kv.getOrDefault("rdb_last_bgsave_status", "unknown");
        String aof = kv.getOrDefault("aof_last_bgrewrite_status", "unknown");
        boolean loading = "1".equals(kv.get("loading"));
        String evidence = "rdb_last_bgsave_status=" + rdb + " aof_last_bgrewrite_status=" + aof
                + " loading=" + kv.getOrDefault("loading", "0");
        String status = ("err".equals(rdb) || "err".equals(aof)) ? STATUS_FAILED
                : loading ? STATUS_WARNING : STATUS_OK;
        return check(CHECK_REDIS_PERSISTENCE, status, commands, evidence, null,
                execution.collectedAt());
    }

    private HostCheck checkNginx(Run run) {
        List<String> commands = new ArrayList<>();
        String version = "nginx -v 2>&1";
        commands.add(version);
        Execution versionExecution = run.execute(version);
        if (versionExecution == null) {
            return check(CHECK_NGINX_UPSTREAM, STATUS_UNVERIFIED, commands,
                    BUDGET_EXHAUSTED_EVIDENCE, null, Instant.now());
        }
        String combined = (versionExecution.stdout() + " " + versionExecution.stderr()).trim();
        if (isUnavailable(versionExecution)
                || !NGINX_VERSION.matcher(combined).find() && versionExecution.exitCode() != 0) {
            return check(CHECK_NGINX_UPSTREAM, STATUS_NOT_APPLICABLE, commands,
                    "nginx 不存在，本项不适用", null, versionExecution.collectedAt());
        }
        if (isPermissionDenied(versionExecution)) {
            return check(CHECK_NGINX_UPSTREAM, STATUS_UNVERIFIED, commands,
                    NO_PERMISSION_EVIDENCE, null, versionExecution.collectedAt());
        }
        Instant collectedAt = versionExecution.collectedAt();

        String test = "nginx -t 2>&1 | tail -n 5";
        commands.add(test);
        Execution testExecution = run.execute(test);
        if (testExecution == null) {
            return check(CHECK_NGINX_UPSTREAM, STATUS_UNVERIFIED, commands,
                    BUDGET_EXHAUSTED_EVIDENCE, null, Instant.now());
        }
        collectedAt = testExecution.collectedAt();
        if (isPermissionDenied(testExecution)) {
            return check(CHECK_NGINX_UPSTREAM, STATUS_UNVERIFIED, commands,
                    NO_PERMISSION_EVIDENCE, null, collectedAt);
        }
        if (testExecution.exitCode() != 0) {
            String tail = testExecution.stdout().isBlank()
                    ? testExecution.stderr() : testExecution.stdout();
            return check(CHECK_NGINX_UPSTREAM, STATUS_FAILED, commands,
                    "nginx -t 失败: " + tail, null, collectedAt);
        }

        String dump = "nginx -T 2>/dev/null | grep -E \"^\\s*(upstream|server\\s)\" | head -n 40";
        commands.add(dump);
        Execution dumpExecution = run.execute(dump);
        if (dumpExecution == null) {
            return check(CHECK_NGINX_UPSTREAM, STATUS_UNVERIFIED, commands,
                    "nginx -t 通过，但命令预算耗尽，upstream 统计未采集", null, Instant.now());
        }
        collectedAt = dumpExecution.collectedAt();
        int upstreamBlocks = 0;
        int serverLines = 0;
        for (String line : dumpExecution.stdout().split("\n")) {
            String trimmed = line.trim();
            if (trimmed.startsWith("upstream ") || trimmed.equals("upstream")) {
                upstreamBlocks++;
            } else if (trimmed.startsWith("server ") || trimmed.equals("server")
                    || trimmed.startsWith("server{")) {
                serverLines++;
            }
        }
        return check(CHECK_NGINX_UPSTREAM, STATUS_OK, commands,
                "nginx -t 通过；upstream 块=" + upstreamBlocks + " server 行=" + serverLines,
                null, collectedAt);
    }

    private HostCheck checkJvm(Run run) {
        int samples = samples(run.request);
        String sampleWindow = samples + "s";
        List<String> commands = new ArrayList<>();
        String pgrep = "pgrep -af \"java\" | head -n 5";
        commands.add(pgrep);
        Execution pgrepExecution = run.execute(pgrep);
        if (pgrepExecution == null) {
            return check(CHECK_JVM, STATUS_UNVERIFIED, commands, BUDGET_EXHAUSTED_EVIDENCE,
                    sampleWindow, Instant.now());
        }
        if (isPermissionDenied(pgrepExecution)) {
            return check(CHECK_JVM, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                    sampleWindow, pgrepExecution.collectedAt());
        }
        if (pgrepExecution.exitCode() != 0 || pgrepExecution.stdout().isBlank()) {
            return check(CHECK_JVM, STATUS_NOT_APPLICABLE, commands,
                    "未发现 java 进程，本项不适用", sampleWindow, pgrepExecution.collectedAt());
        }
        Instant collectedAt = pgrepExecution.collectedAt();
        List<String> pids = new ArrayList<>();
        for (String line : pgrepExecution.stdout().split("\n")) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            String pid = trimmed.split("\\s+")[0];
            if (pid.matches("\\d+") && !pids.contains(pid)) pids.add(pid);
            if (pids.size() >= MAX_JVM_PIDS) break;
        }

        StringBuilder evidence = new StringBuilder();
        boolean warning = false;
        for (String pid : pids) {
            String version = "jcmd " + pid + " VM.version";
            commands.add(version);
            Execution versionExecution = run.execute(version);
            if (versionExecution == null) {
                evidence.append("pid=").append(pid).append(" 命令预算耗尽，未核验; ");
                continue;
            }
            collectedAt = versionExecution.collectedAt();
            if (isPermissionDenied(versionExecution)) {
                return check(CHECK_JVM, STATUS_UNVERIFIED, commands, NO_PERMISSION_EVIDENCE,
                        sampleWindow, collectedAt);
            }
            if (versionExecution.exitCode() != 0 || isUnavailable(versionExecution)) {
                return check(CHECK_JVM, STATUS_UNVERIFIED, commands,
                        "jcmd 不存在或不可用（exit=" + versionExecution.exitCode()
                                + "），JVM 未核验；已发现 java 进程 pid=" + String.join(",", pids),
                        sampleWindow, collectedAt);
            }

            String heap = "jcmd " + pid + " GC.heap_info";
            commands.add(heap);
            Execution heapExecution = run.execute(heap);
            double heapPct = -1;
            if (heapExecution != null) {
                collectedAt = heapExecution.collectedAt();
                if (heapExecution.exitCode() == 0) {
                    heapPct = parseHeapUsedPct(heapExecution.stdout());
                }
            }

            String jstat = "jstat -gcutil " + pid + " 1000 " + samples + " | tail -n 3";
            commands.add(jstat);
            Execution jstatExecution = run.execute(jstat);
            Double oldPct = null;
            if (jstatExecution != null) {
                collectedAt = jstatExecution.collectedAt();
                if (jstatExecution.exitCode() == 0) {
                    oldPct = parseJstatOld(jstatExecution.stdout());
                }
            }

            String threads = "jcmd " + pid + " Thread.print | grep -c '^\"'";
            commands.add(threads);
            Execution threadExecution = run.execute(threads);
            Integer threadCount = null;
            if (threadExecution != null) {
                collectedAt = threadExecution.collectedAt();
                if (threadExecution.exitCode() == 0) {
                    threadCount = firstInt(threadExecution.stdout());
                }
            }

            if (heapPct > 90 || (oldPct != null && oldPct > 90)) warning = true;
            evidence.append("pid=").append(pid)
                    .append(" heapUsed=").append(heapPct < 0 ? "unknown" : fmt(heapPct) + "%")
                    .append(" oldGen=").append(oldPct == null ? "unknown" : fmt(oldPct) + "%")
                    .append(" threads=").append(threadCount == null ? "unknown" : threadCount)
                    .append("; ");
        }
        return check(CHECK_JVM, warning ? STATUS_WARNING : STATUS_OK, commands,
                evidence.toString(), sampleWindow, collectedAt);
    }

    /* ── 判定与解析辅助 ─────────────────────────────────────────────────── */

    private static int samples(HostDiagnosisRequest request) {
        return Math.max(2, Math.min(4, request.sampleSeconds()));
    }

    private static boolean isPermissionDenied(Execution execution) {
        return execution.exitCode() != 0
                && PERMISSION_ERROR.matcher(execution.stderr()).find();
    }

    private static boolean isUnavailable(Execution execution) {
        if (execution.exitCode() == 127) return true;
        String combined = execution.stdout() + " " + execution.stderr();
        return COMMAND_UNAVAILABLE.matcher(combined).find();
    }

    /** 解析 vmstat 数据行：首行为开机以来均值，多于一行时丢弃；返回 {maxR, avgUs, avgSy, avgWa}。 */
    private static double[] parseVmstat(String stdout) {
        List<String[]> rows = new ArrayList<>();
        for (String line : stdout.split("\n")) {
            String[] fields = line.trim().split("\\s+");
            if (fields.length < 16 || !fields[0].matches("\\d+")) continue;
            rows.add(fields);
        }
        int start = rows.size() > 1 ? 1 : 0;
        double maxR = -1;
        double sumUs = 0;
        double sumSy = 0;
        double sumWa = 0;
        int count = 0;
        for (int i = start; i < rows.size(); i++) {
            String[] fields = rows.get(i);
            double r = doubleOf(fields[0]);
            double us = doubleOf(fields[12]);
            double sy = doubleOf(fields[13]);
            double wa = doubleOf(fields[15]);
            if (Double.isNaN(us) || Double.isNaN(sy) || Double.isNaN(wa)) continue;
            maxR = Math.max(maxR, r);
            sumUs += us;
            sumSy += sy;
            sumWa += wa;
            count++;
        }
        if (count == 0) return null;
        return new double[]{maxR, sumUs / count, sumSy / count, sumWa / count};
    }

    /** 解析 top 单帧的 %Cpu(s) 行，返回 {0, us, sy, wa}。 */
    private static double[] parseTop(String stdout) {
        Matcher matcher = TOP_CPU.matcher(stdout);
        if (!matcher.find()) return null;
        return new double[]{0, doubleOf(matcher.group(1)), doubleOf(matcher.group(2)),
                doubleOf(matcher.group(3))};
    }

    /** 解析 free -m：返回 {memTotal, memAvailable, swapTotal, swapUsed}，解析失败返回 null。 */
    private static long[] parseFree(String stdout) {
        Long memTotal = null;
        Long memAvailable = null;
        long swapTotal = 0;
        long swapUsed = 0;
        for (String line : stdout.split("\n")) {
            String[] fields = line.trim().split("\\s+");
            if (fields.length >= 7 && "Mem:".equals(fields[0])) {
                memTotal = longOf(fields[1], -1);
                memAvailable = longOf(fields[6], -1);
            } else if (fields.length >= 3 && "Swap:".equals(fields[0])) {
                swapTotal = longOf(fields[1], 0);
                swapUsed = longOf(fields[2], 0);
            }
        }
        if (memTotal == null || memAvailable == null || memTotal <= 0 || memAvailable < 0) {
            return null;
        }
        return new long[]{memTotal, memAvailable, swapTotal, swapUsed};
    }

    /** 解析 df -P / df -iP：返回 [挂载点, 百分比数值] 列表。 */
    private static List<String[]> parseDf(String stdout) {
        List<String[]> rows = new ArrayList<>();
        for (String line : stdout.split("\n")) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("Filesystem")) continue;
            String[] fields = trimmed.split("\\s+");
            int pctIndex = -1;
            for (int i = 0; i < fields.length; i++) {
                if (fields[i].endsWith("%")) pctIndex = i;
            }
            if (pctIndex < 0) continue;
            String pct = fields[pctIndex].substring(0, fields[pctIndex].length() - 1);
            if (!pct.matches("\\d+")) continue;
            rows.add(new String[]{fields[fields.length - 1], pct});
        }
        return rows;
    }

    private static int maxPct(List<String[]> rows) {
        int max = 0;
        for (String[] row : rows) {
            max = Math.max(max, Integer.parseInt(row[1]));
        }
        return max;
    }

    /** 解析 iostat -x 最后一个 Device 块。 */
    private static List<IoRow> parseIostat(String stdout) {
        String[] lines = stdout.split("\n");
        int headerIndex = -1;
        for (int i = 0; i < lines.length; i++) {
            if (lines[i].trim().startsWith("Device")) headerIndex = i;
        }
        if (headerIndex < 0) return List.of();
        String[] header = lines[headerIndex].trim().split("\\s+");
        int utilIndex = -1;
        List<Integer> awaitIndexes = new ArrayList<>();
        for (int i = 0; i < header.length; i++) {
            if ("%util".equals(header[i])) utilIndex = i;
            if ("await".equals(header[i]) || header[i].endsWith("_await")) awaitIndexes.add(i);
        }
        if (utilIndex < 0) return List.of();
        List<IoRow> rows = new ArrayList<>();
        for (int i = headerIndex + 1; i < lines.length; i++) {
            String[] fields = lines[i].trim().split("\\s+");
            if (fields.length < header.length || !lines[i].trim().matches("\\S+.*")
                    || fields[0].isEmpty() || !Character.isLetterOrDigit(fields[0].charAt(0))) {
                continue;
            }
            double util = doubleOf(fields[utilIndex]);
            if (Double.isNaN(util)) continue;
            double await = 0;
            for (int index : awaitIndexes) {
                if (index < fields.length) {
                    double value = doubleOf(fields[index]);
                    if (!Double.isNaN(value)) await = Math.max(await, value);
                }
            }
            rows.add(new IoRow(fields[0], await, util));
        }
        return rows;
    }

    private static List<String> parseFailedUnits(String stdout) {
        List<String> units = new ArrayList<>();
        for (String line : stdout.split("\n")) {
            String trimmed = line.replace("●", " ").trim();
            if (!trimmed.contains(" failed ")) continue;
            String unit = trimmed.split("\\s+")[0];
            if (!unit.isEmpty() && !units.contains(unit)) units.add(unit);
        }
        return units;
    }

    private static int redisPort(String pgrepOutput) {
        Matcher matcher = REDIS_PORT.matcher(pgrepOutput);
        return matcher.find() ? Integer.parseInt(matcher.group(1)) : 6379;
    }

    private static Map<String, String> parseRedisInfo(String stdout) {
        Map<String, String> kv = new LinkedHashMap<>();
        for (String line : stdout.split("\n")) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("#")) continue;
            int colon = trimmed.indexOf(':');
            if (colon <= 0) continue;
            kv.put(trimmed.substring(0, colon), trimmed.substring(colon + 1));
        }
        return kv;
    }

    /** 解析 GC.heap_info 中所有 total/used 行，返回 used/total 百分比，解析失败返回 -1。 */
    private static double parseHeapUsedPct(String stdout) {
        Matcher matcher = HEAP_USAGE.matcher(stdout);
        long total = 0;
        long used = 0;
        while (matcher.find()) {
            total += Long.parseLong(matcher.group(1));
            used += Long.parseLong(matcher.group(2));
        }
        return total <= 0 ? -1 : used * 100.0 / total;
    }

    /** 取 jstat -gcutil 最后一个数值行的老年代列（O，第 4 列）。 */
    private static Double parseJstatOld(String stdout) {
        String[] lines = stdout.trim().split("\n");
        for (int i = lines.length - 1; i >= 0; i--) {
            String[] fields = lines[i].trim().split("\\s+");
            if (fields.length >= 4 && fields[0].matches("[0-9.]+")) {
                double value = doubleOf(fields[3]);
                if (!Double.isNaN(value)) return value;
            }
        }
        return null;
    }

    private static Double firstDouble(String stdout) {
        String trimmed = stdout.trim();
        if (trimmed.isEmpty()) return null;
        double value = doubleOf(trimmed.split("\\s+")[0]);
        return Double.isNaN(value) ? null : value;
    }

    private static Integer firstInt(String stdout) {
        String trimmed = stdout.trim();
        return trimmed.matches("\\d+") ? Integer.parseInt(trimmed.split("\\s+")[0]) : null;
    }

    private static double doubleOf(String value) {
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException ex) {
            return Double.NaN;
        }
    }

    private static long longOf(String value, long fallback) {
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException ex) {
            return fallback;
        }
    }

    private static String fmt(double value) {
        return String.format(Locale.ROOT, "%.1f", value);
    }

    private static String brief(String value) {
        if (value == null) return "";
        String singleLine = value.replace('\n', ' ').replace('\r', ' ')
                .replaceAll("\\s+", " ").trim();
        return singleLine.length() <= MAX_EVIDENCE_LENGTH
                ? singleLine
                : singleLine.substring(0, MAX_EVIDENCE_LENGTH) + "...";
    }

    private static String text(String value) {
        return value == null ? "" : value;
    }

    private static HostCheck check(String name, String status, List<String> commands,
                                   String evidence, String sampleWindow, Instant collectedAt) {
        return new HostCheck(name, status, List.copyOf(commands), brief(evidence), sampleWindow,
                collectedAt.toString());
    }

    /* ── 对外模型 ───────────────────────────────────────────────────────── */

    public record HostScope(String runtimeId, int sampleSeconds) {}

    public record HostCheck(String name, String status, List<String> commands, String evidence,
                            String sampleWindow, String collectedAt) {}

    public record HostDiagnosisResult(HostScope scope, String startedAt, String endedAt,
                                      long durationMs, List<HostCheck> checks,
                                      String overallStatus, boolean unverified,
                                      boolean truncated) {}

    /* ── 内部运行态 ─────────────────────────────────────────────────────── */

    private record IoRow(String device, double await, double util) {}

    private record Execution(int exitCode, String stdout, String stderr, Instant collectedAt) {}

    private static final class Run {
        private final OperationRuntime runtime;
        private final HostDiagnosisRequest request;
        private final Instant deadline;
        private int commandsUsed;
        private boolean truncated;

        private Run(OperationRuntime runtime, HostDiagnosisRequest request, Instant startedAt) {
            this.runtime = runtime;
            this.request = request;
            this.deadline = startedAt.plusMillis(TOTAL_TIMEOUT_MS);
        }

        private Execution execute(String command) {
            if (commandsUsed >= MAX_COMMANDS || Instant.now().isAfter(deadline)) {
                truncated = true;
                return null;
            }
            commandsUsed++;
            try {
                OperationRuntime.CommandResult result = runtime.execute(command, COMMAND_TIMEOUT_MS);
                return new Execution(result.exitCode(), text(result.stdout()),
                        text(result.stderr()), Instant.now());
            } catch (IOException ex) {
                String message = ex.getMessage();
                return new Execution(-1, "",
                        message == null || message.isBlank() ? "COMMAND_EXECUTION_FAILED" : message,
                        Instant.now());
            }
        }
    }
}
