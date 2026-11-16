package com.smartops.operations;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/** 真实服务器监控采样：复用在线 SSH runtime 的 exec 通道，不新增连接。 */
@Service
@RequiredArgsConstructor
public class ServerMonitorService {

    /** 单次采样命令：分区输出 + 双采样 /proc/stat（间隔 0.4s）。 */
    static final String SAMPLING_COMMAND =
            "echo ===STAT1; head -1 /proc/stat; echo ===LOAD; cat /proc/loadavg; echo ===MEM; head -5 /proc/meminfo; "
                    + "echo ===DISK; df -kP / | tail -1; echo ===NET; cat /proc/net/dev; sleep 0.4; echo ===STAT2; head -1 /proc/stat";

    private static final long SAMPLING_TIMEOUT_MILLIS = 6000;

    private final OperationRuntimeRegistry registry;

    public ServerMonitorSample sample(Long userId, String runtimeId) {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!runtime.isOpen()) return ServerMonitorSample.unsupported("RUNTIME_CLOSED");
        try {
            OperationRuntime.CommandResult result = runtime.execute(SAMPLING_COMMAND, SAMPLING_TIMEOUT_MILLIS);
            if (result.exitCode() != 0) {
                return ServerMonitorSample.unsupported("SAMPLING_EXIT_" + result.exitCode());
            }
            return ServerMonitorSampleParser.parse(result.stdout());
        } catch (Exception e) {
            return ServerMonitorSample.unsupported(e.getMessage() == null ? "SAMPLING_FAILED" : e.getMessage());
        }
    }
}
