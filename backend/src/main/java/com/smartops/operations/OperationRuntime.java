package com.smartops.operations;

import java.io.IOException;
import java.util.function.BooleanSupplier;

public interface OperationRuntime extends AutoCloseable {
    record CommandResult(int exitCode, String stdout, String stderr, boolean truncated) {
        public CommandResult(int exitCode, String stdout, String stderr) {
            this(exitCode, stdout, stderr, false);
        }
    }

    String id();
    Long userId();
    Long sessionId();
    void write(String input) throws IOException;
    void resize(int columns, int rows) throws IOException;
    void onOutput(OutputListener listener);
    boolean isOpen();
    default CommandResult execute(String command, long timeoutMillis) throws IOException {
        throw new IOException("RUNTIME_EXEC_NOT_SUPPORTED");
    }
    /** PERF-06：三参 execute 带取消钩子；默认实现委托两参版本（不支持取消传播）。 */
    default CommandResult execute(String command, long timeoutMillis, BooleanSupplier cancellationRequested) throws IOException {
        return execute(command, timeoutMillis);
    }
    @Override void close();

    interface OutputListener {
        void onOutput(String output);
        default void onClosed(Integer exitCode) {}
    }
}
