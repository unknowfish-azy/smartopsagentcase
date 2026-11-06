package com.smartops.operations;

import java.io.IOException;

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
    @Override void close();

    interface OutputListener {
        void onOutput(String output);
        default void onClosed(Integer exitCode) {}
    }
}
