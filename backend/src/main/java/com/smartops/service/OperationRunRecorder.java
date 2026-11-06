package com.smartops.service;

import com.smartops.operations.OperationRuntime;

import java.time.Instant;

/**
 * 运行记录的权威写入接口。
 *
 * <p>Java 侧 Run 是执行事实的唯一权威来源：Python/前端只能读取它，不能另建一套状态。
 * 除基础的 start/record/finish 外，这里用 default 方法补齐执行恢复所需的
 * 幂等、租约心跳、取消和证据写入；旧实现（如测试替身）无需改动即可继续工作。</p>
 */
public interface OperationRunRecorder {

    RunHandle start(String traceId, Long userId, OperationRuntime runtime, String toolId, Instant startedAt);

    /**
     * 带治理字段的启动。
     *
     * <p>默认实现退化为旧签名，保证既有调用方与测试替身不被破坏；
     * JDBC 实现会真正落库幂等键、绝对 deadline、租约与输出预算。</p>
     */
    default RunHandle start(RunSpec spec) {
        return start(spec.traceId(), spec.userId(), spec.runtime(), spec.toolId(), spec.startedAt());
    }

    void recordCommand(RunHandle run, int sequence, String command, int exitCode,
                       String stdout, String stderr, Instant startedAt, Instant endedAt);

    /** 记录一条命令结果，并显式标记输出是否被截断。 */
    default void recordCommand(RunHandle run, int sequence, String command, int exitCode,
                               String stdout, String stderr, Instant startedAt, Instant endedAt,
                               boolean truncated) {
        recordCommand(run, sequence, command, exitCode, stdout, stderr, startedAt, endedAt);
    }

    void finish(RunHandle run, String status, Instant endedAt);

    /** 心跳：证明本进程仍持有该 Run，供恢复扫描区分“执行中”与“悬挂”。 */
    default void heartbeat(RunHandle run) {}

    /** 查询是否有人请求取消（在命令之间轮询，不中断远端已在执行的命令）。 */
    default boolean cancelRequested(RunHandle run) { return false; }

    /** 写入结构化证据（例如“远端状态不确定，需人工核验”）。 */
    default void recordEvidence(RunHandle run, String type, String content) {}

    /**
     * 记录一次未真正执行的调用（未审批拒绝 / 模板 / 不可用）。
     *
     * <p>这类调用不进入 RUNNING，也不占用租约；但“拒绝和不可用”同样必须可追溯，
     * 不能只留应用日志。默认空实现保证既有测试替身无需改动。</p>
     *
     * @param status REJECTED（拒绝）或 NOT_IMPLEMENTED（模板/不可用）
     * @param reason 稳定错误码 + 原因，写入证据供审计核对
     */
    default void recordBlockedAttempt(String traceId, Long userId, String runtimeId, String toolId,
                                      String status, String reason, Instant at) {}

    /**
     * 一次运行的治理参数。
     *
     * @param idempotencyKey 非空时同一用户同一键只允许启动一次；重复启动必须拒绝而不是重跑
     * @param deadlineAt     整个 Run 的绝对截止时间，不是单条命令超时
     * @param maxOutputBytes 单条命令落库的输出预算，超出部分截断并标记
     * @param leaseMs        租约时长，超过无心跳即视为悬挂
     */
    record RunSpec(String traceId, Long userId, OperationRuntime runtime, String toolId,
                   String idempotencyKey, Instant startedAt, Instant deadlineAt,
                   int maxOutputBytes, long leaseMs) {}

    record RunHandle(Long id, String traceId) {}
}
