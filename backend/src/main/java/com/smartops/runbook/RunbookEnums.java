package com.smartops.runbook;

import com.smartops.exception.BusinessException;

/**
 * Runbook 的状态与枚举口径。
 *
 * <p>集中在一处的原因：这些值是数据库列的真实取值，散落在多个类里很容易出现
 * "写入 SUCCESS、查询 SUCCEEDED" 这类静默不一致。任何新增状态都必须同时
 * 定义：允许的转移、失败状态、未知状态和回滚方式。</p>
 */
public final class RunbookEnums {

    private RunbookEnums() {}

    /** 适用环境。PROD 目标会自动提高所需确认次数。 */
    public enum Environment {
        DEV, STAGING, PROD;

        public static Environment of(String value) {
            String text = value == null ? "" : value.trim().toUpperCase(java.util.Locale.ROOT);
            for (Environment item : values()) {
                if (item.name().equals(text)) return item;
            }
            throw new BusinessException(400, "RUNBOOK_ENVIRONMENT_INVALID");
        }

        public boolean production() { return this == PROD; }
    }

    /** 风险等级；Runbook 声明值与步骤实际内容取较高者。 */
    public enum Risk {
        LOW, MEDIUM, HIGH, CRITICAL;

        public static Risk of(String value) {
            String text = value == null ? "" : value.trim().toUpperCase(java.util.Locale.ROOT);
            for (Risk item : values()) {
                if (item.name().equals(text)) return item;
            }
            throw new BusinessException(400, "RUNBOOK_RISK_INVALID");
        }

        public static Risk max(Risk left, Risk right) {
            if (left == null) return right;
            if (right == null) return left;
            return left.ordinal() >= right.ordinal() ? left : right;
        }
    }

    /** 步骤阶段。执行顺序固定：前置检查 → 执行 → 后置检查；回滚单独触发。 */
    public enum Phase {
        PRE_CHECK, EXECUTE, POST_CHECK, ROLLBACK;

        public static Phase of(String value) {
            String text = value == null ? "" : value.trim().toUpperCase(java.util.Locale.ROOT);
            for (Phase item : values()) {
                if (item.name().equals(text)) return item;
            }
            throw new BusinessException(400, "RUNBOOK_STEP_PHASE_INVALID");
        }
    }

    /** 步骤失败后的分支。 */
    public enum OnFailure {
        ABORT, CONTINUE, ROLLBACK;

        public static OnFailure of(String value) {
            if (value == null || value.isBlank()) return ABORT;
            String text = value.trim().toUpperCase(java.util.Locale.ROOT);
            for (OnFailure item : values()) {
                if (item.name().equals(text)) return item;
            }
            throw new BusinessException(400, "RUNBOOK_STEP_ON_FAILURE_INVALID");
        }
    }

    /** 触发方式。三种触发共用同一条"计划 → 审批 → 执行"链。 */
    public enum Trigger {
        MANUAL, SCHEDULE, ALERT;

        public static Trigger of(String value) {
            String text = value == null ? "MANUAL" : value.trim().toUpperCase(java.util.Locale.ROOT);
            for (Trigger item : values()) {
                if (item.name().equals(text)) return item;
            }
            throw new BusinessException(400, "RUNBOOK_TRIGGER_INVALID");
        }
    }

    /** 作业运行状态。终态之外的状态必须能被取消或有明确的下一步。 */
    public enum RunStatus {
        AWAITING_TARGETS, PENDING_APPROVAL, APPROVED, RUNNING,
        SUCCEEDED, PARTIAL, FAILED, UNKNOWN, CANCELLED,
        ROLLING_BACK, ROLLED_BACK, ROLLBACK_FAILED;

        public boolean terminal() {
            return this == SUCCEEDED || this == PARTIAL || this == FAILED || this == UNKNOWN
                    || this == CANCELLED || this == ROLLED_BACK || this == ROLLBACK_FAILED;
        }

        /** 允许发起回滚的状态：已经产生远端副作用，且不是"从未执行"。 */
        public boolean rollbackable() {
            return this == PARTIAL || this == FAILED || this == UNKNOWN || this == ROLLBACK_FAILED;
        }
    }

    /** 单目标结果。UNKNOWN 表示命令已派发但结果不可确认，禁止直接重试写操作。 */
    public enum TargetStatus {
        PENDING, RUNNING, SUCCEEDED, FAILED, UNKNOWN, TIMEOUT, CANCELLED, SKIPPED,
        ROLLED_BACK, ROLLBACK_FAILED
    }
}
