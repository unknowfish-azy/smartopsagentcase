package com.smartops.diagnostics.host;

import com.smartops.diagnostics.host.HostDiagnosisService.HostCheck;
import com.smartops.diagnostics.host.HostDiagnosisService.HostDiagnosisResult;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class HostDiagnosisServiceTest {

    private static final String VMSTAT_HEALTHY = """
            procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
             r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
             1  0      0 7154300 18532 512340    0    0     1     2   25   40  1  1 98  0  0
             0  0      0 7154220 18532 512340    0    0     0     0   30   45  1  1 98  0  0
            """;
    private static final String VMSTAT_BUSY = """
            procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
             r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
             2  0      0 7154300 18532 512340    0    0     1     2   25   40 85 10  5  0  0
             3  0      0 7154220 18532 512340    0    0     0     0   30   45 80 15  5  0  0
            """;
    private static final String FREE_HEALTHY = """
                          total        used        free      shared  buff/cache   available
            Mem:           7824        3120        2900          12        1804        4300
            Swap:          2047           0        2047
            """;
    private static final String FREE_EXHAUSTED = """
                          total        used        free      shared  buff/cache   available
            Mem:           7824        7200         120          12         504         300
            Swap:          2047           0        2047
            """;
    private static final String DF_HEALTHY = """
            Filesystem     1024-blocks    Used Available Capacity Mounted on
            /dev/sda1        51200000 20480000  30720000      40% /
            tmpfs             4000000       0   4000000       0% /run
            """;
    private static final String DF_FULL = """
            Filesystem     1024-blocks     Used Available Capacity Mounted on
            /dev/sda1        51200000 49152000   2048000      96% /
            """;
    private static final String DF_INODE_HEALTHY = """
            Filesystem      Inodes  IUsed   IFree IUse% Mounted on
            /dev/sda1      3276800 120000 3156800    4% /
            """;
    private static final String IOSTAT_HEALTHY = """
            Linux 5.15.0 (host) \t11/06/2026 \t_x86_64_\t(4 CPU)

            Device            r/s     w/s  rMB/s  wMB/s  await  %util
            sda              1.00    2.00   0.10   0.20   3.00   5.00

            Device            r/s     w/s  rMB/s  wMB/s  await  %util
            sda              1.10    2.10   0.11   0.21   3.10   5.10
            """;
    private static final String SYSTEMD_FAILED_UNITS = """
              UNIT           LOAD   ACTIVE SUB    DESCRIPTION
            ● redis.service loaded failed failed Redis Server
            ● nginx.service loaded failed failed Nginx

            2 loaded units listed.
            """;

    @Test
    void healthy_host_has_no_warning_or_failed_and_overall_ok() {
        HostDiagnosisResult result = diagnose(healthyRuntime());

        assertThat(result.checks()).hasSize(11);
        assertThat(result.checks()).extracting(HostCheck::name).containsExactly(
                "CPU", "LOAD", "MEMORY", "DISK", "IO", "SYSTEMD", "TIME_SYNC",
                "REDIS_REPLICATION", "REDIS_PERSISTENCE", "NGINX_UPSTREAM", "JVM");
        assertThat(result.checks()).extracting(HostCheck::status)
                .doesNotContain("WARNING", "FAILED");
        assertThat(result.overallStatus()).isEqualTo("OK");
        assertThat(result.unverified()).isFalse();
        assertThat(result.truncated()).isFalse();
    }

    @Test
    void high_cpu_from_vmstat_is_warning() {
        StubRuntime runtime = healthyRuntime().reply("vmstat", 0, VMSTAT_BUSY, "");

        HostDiagnosisResult result = diagnose(runtime);

        assertThat(check(result, "CPU").status()).isEqualTo("WARNING");
        assertThat(check(result, "CPU").evidence()).contains("us=80.0");
        assertThat(result.overallStatus()).isEqualTo("WARNING");
    }

    @Test
    void disk_at_96_percent_is_failed() {
        StubRuntime runtime = healthyRuntime().reply("df -P", 0, DF_FULL, "");

        HostDiagnosisResult result = diagnose(runtime);

        assertThat(check(result, "DISK").status()).isEqualTo("FAILED");
        assertThat(check(result, "DISK").evidence()).contains("96%");
        assertThat(result.overallStatus()).isEqualTo("FAILED");
    }

    @Test
    void memory_available_below_5_percent_is_failed() {
        StubRuntime runtime = healthyRuntime().reply("free -m", 0, FREE_EXHAUSTED, "");

        HostDiagnosisResult result = diagnose(runtime);

        assertThat(check(result, "MEMORY").status()).isEqualTo("FAILED");
        assertThat(check(result, "MEMORY").evidence()).contains("available=300MB");
        assertThat(result.overallStatus()).isEqualTo("FAILED");
    }

    @Test
    void systemd_failed_units_are_failed_and_evidence_lists_unit_names() {
        StubRuntime runtime = healthyRuntime()
                .reply("systemctl --failed", 0, SYSTEMD_FAILED_UNITS, "")
                .reply("is-system-running", 0, "degraded\n", "");

        HostDiagnosisResult result = diagnose(runtime);

        assertThat(check(result, "SYSTEMD").status()).isEqualTo("FAILED");
        assertThat(check(result, "SYSTEMD").evidence()).contains("redis.service");
        assertThat(check(result, "SYSTEMD").evidence()).contains("nginx.service");
        assertThat(result.overallStatus()).isEqualTo("FAILED");
    }

    @Test
    void ntp_not_synchronized_is_warning() {
        StubRuntime runtime = healthyRuntime().reply("timedatectl", 0, "no\n", "");

        HostDiagnosisResult result = diagnose(runtime);

        assertThat(check(result, "TIME_SYNC").status()).isEqualTo("WARNING");
        assertThat(check(result, "TIME_SYNC").evidence()).contains("NTPSynchronized=no");
        assertThat(result.overallStatus()).isEqualTo("WARNING");
    }

    @Test
    void redis_slave_with_master_link_down_is_failed() {
        StubRuntime runtime = healthyRuntime()
                .reply("redis-server", 0, "1234 /usr/bin/redis-server 127.0.0.1:6379\n", "")
                .reply("info replication", 0, """
                        # Replication
                        role:slave
                        master_host:10.0.0.5
                        master_link_status:down
                        master_last_io_seconds_ago:25
                        """, "")
                .reply("info persistence", 0, """
                        rdb_last_bgsave_status:ok
                        aof_last_bgrewrite_status:ok
                        loading:0
                        """, "");

        HostDiagnosisResult result = diagnose(runtime);

        assertThat(check(result, "REDIS_REPLICATION").status()).isEqualTo("FAILED");
        assertThat(check(result, "REDIS_REPLICATION").evidence())
                .contains("master_link_status=down");
        assertThat(check(result, "REDIS_PERSISTENCE").status()).isEqualTo("OK");
        assertThat(result.overallStatus()).isEqualTo("FAILED");
    }

    @Test
    void missing_nginx_and_java_are_not_applicable_never_failed() {
        HostDiagnosisResult result = diagnose(healthyRuntime());

        assertThat(check(result, "NGINX_UPSTREAM").status()).isEqualTo("NOT_APPLICABLE");
        assertThat(check(result, "JVM").status()).isEqualTo("NOT_APPLICABLE");
        assertThat(result.checks()).extracting(HostCheck::status).doesNotContain("FAILED");
    }

    @Test
    void java_process_without_jcmd_is_unverified_and_flags_result() {
        StubRuntime runtime = healthyRuntime()
                .reply("\"java\"", 0, "4321 /opt/jdk/bin/java -jar app.jar\n", "")
                .reply("VM.version", 127, "", "bash: jcmd: command not found");

        HostDiagnosisResult result = diagnose(runtime);

        assertThat(check(result, "JVM").status()).isEqualTo("UNVERIFIED");
        assertThat(check(result, "JVM").evidence()).contains("jcmd");
        assertThat(result.unverified()).isTrue();
        assertThat(result.overallStatus()).isEqualTo("INCOMPLETE");
    }

    @Test
    void command_budget_exhaustion_truncates_and_marks_remaining_checks_unverified() {
        // Redis/nginx 均存在时，按检查顺序会把 14 条命令预算耗尽：
        // 前 13 条给出真实结论，nginx -t 起不再执行，剩余检查必须如实标 UNVERIFIED。
        HostDiagnosisResult result = diagnose(heavyRuntime());

        assertThat(result.truncated()).isTrue();
        assertThat(check(result, "REDIS_REPLICATION").status()).isEqualTo("OK");
        assertThat(check(result, "REDIS_PERSISTENCE").status()).isEqualTo("OK");
        assertThat(check(result, "NGINX_UPSTREAM").status()).isEqualTo("UNVERIFIED");
        assertThat(check(result, "NGINX_UPSTREAM").evidence()).contains("预算");
        assertThat(check(result, "JVM").status()).isEqualTo("UNVERIFIED");
        assertThat(check(result, "JVM").evidence()).contains("预算");
        assertThat(result.unverified()).isTrue();
        assertThat(result.overallStatus()).isEqualTo("INCOMPLETE");
        assertThat(result.checks()).extracting(HostCheck::status).doesNotContain("FAILED");
    }

    /* ── 测试替身与夹具 ─────────────────────────────────────────────────── */

    private static HostDiagnosisResult diagnose(StubRuntime runtime) {
        OperationRuntimeRegistry registry = new OperationRuntimeRegistry();
        String runtimeId = registry.register(runtime);
        return new HostDiagnosisService(registry)
                .diagnose(runtime.userId(), new HostDiagnosisRequest(runtimeId, 2));
    }

    private static HostCheck check(HostDiagnosisResult result, String name) {
        return result.checks().stream()
                .filter(check -> name.equals(check.name()))
                .findFirst()
                .orElseThrow();
    }

    /**
     * 健康主机：vmstat/load/free/df/iostat 均正常，systemd 无失败单元，NTP 已同步，
     * 无 redis 进程、无 nginx、无 java 进程。
     */
    private static StubRuntime healthyRuntime() {
        return new StubRuntime(1L)
                .reply("vmstat", 0, VMSTAT_HEALTHY, "")
                .reply("/proc/loadavg", 0, "0.20 0.30 0.40 1/200 1234\n", "")
                .reply("nproc", 0, "4\n", "")
                .reply("free -m", 0, FREE_HEALTHY, "")
                .reply("df -iP", 0, DF_INODE_HEALTHY, "")
                .reply("df -P", 0, DF_HEALTHY, "")
                .reply("iostat", 0, IOSTAT_HEALTHY, "")
                .reply("systemctl --failed", 0, "0 loaded units listed.\n", "")
                .reply("is-system-running", 0, "running\n", "")
                .reply("timedatectl", 0, "yes\n", "")
                .reply("redis-server", 1, "", "")
                .reply("nginx -v", 127, "", "bash: nginx: command not found")
                .reply("\"java\"", 1, "", "")
                .fallback(1, "", "");
    }

    /** 重负载主机：redis 与 nginx 都存在，前 13 条命令即用掉预算，用于验证截断语义。 */
    private static StubRuntime heavyRuntime() {
        return healthyRuntime()
                .reply("redis-server", 0, "5678 /usr/bin/redis-server 127.0.0.1:6379\n", "")
                .reply("info replication", 0, """
                        # Replication
                        role:master
                        connected_slaves:1
                        """, "")
                .reply("info persistence", 0, """
                        rdb_last_bgsave_status:ok
                        aof_last_bgrewrite_status:ok
                        loading:0
                        """, "")
                .reply("nginx -v", 0, "nginx version: nginx/1.24.0\n", "")
                .reply("nginx -t", 0, "nginx: configuration file /etc/nginx/nginx.conf test is successful\n", "");
    }

    private static final class StubRuntime implements OperationRuntime {
        private final Long userId;
        private final Map<String, CommandResult> replies = new LinkedHashMap<>();
        private final List<String> commands = new ArrayList<>();
        private CommandResult fallback = new CommandResult(0, "", "");

        private StubRuntime(Long userId) {
            this.userId = userId;
        }

        private StubRuntime reply(String commandFragment, int exitCode, String stdout,
                                  String stderr) {
            replies.put(commandFragment, new CommandResult(exitCode, stdout, stderr));
            return this;
        }

        private StubRuntime fallback(int exitCode, String stdout, String stderr) {
            this.fallback = new CommandResult(exitCode, stdout, stderr);
            return this;
        }

        @Override
        public CommandResult execute(String command, long timeoutMillis) {
            commands.add(command);
            for (Map.Entry<String, CommandResult> reply : replies.entrySet()) {
                if (command.contains(reply.getKey())) return reply.getValue();
            }
            return fallback;
        }

        public String id() { return "stub-runtime"; }
        public Long userId() { return userId; }
        public Long sessionId() { return 1L; }
        public void write(String input) { }
        public void resize(int columns, int rows) { }
        public void onOutput(OutputListener listener) { }
        public boolean isOpen() { return true; }
        public void close() { }
    }
}
