package com.smartops.operations;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * 命令输出预算：只保留前 limitBytes 字节，超出部分直接丢弃并记录截断。
 *
 * <p>用于 SSH exec 通道的 stdout/stderr 收集。100 MB 输出不会按原量级进入堆内存，
 * 下游可通过 {@link #truncated()} 知道展示内容不完整。</p>
 */
public final class BoundedOutput {
    private final long limitBytes;
    private final ByteArrayOutputStream kept;
    private long droppedBytes;

    public BoundedOutput(long limitBytes) {
        this.limitBytes = Math.max(0, limitBytes);
        int initial = (int) Math.min(this.limitBytes, 64 * 1024L);
        this.kept = new ByteArrayOutputStream(initial);
    }

    public OutputStream stream() {
        return new OutputStream() {
            @Override
            public void write(int b) {
                synchronized (BoundedOutput.this) {
                    if (kept.size() < limitBytes) {
                        kept.write(b);
                    } else {
                        droppedBytes++;
                    }
                }
            }

            @Override
            public void write(byte[] bytes, int offset, int length) {
                synchronized (BoundedOutput.this) {
                    long remaining = limitBytes - kept.size();
                    if (remaining <= 0) {
                        droppedBytes += length;
                        return;
                    }
                    int keep = (int) Math.min(remaining, length);
                    kept.write(bytes, offset, keep);
                    droppedBytes += length - keep;
                }
            }
        };
    }

    public synchronized String text() {
        return new String(kept.toByteArray(), StandardCharsets.UTF_8);
    }

    public synchronized boolean truncated() {
        return droppedBytes > 0;
    }

    public synchronized long keptBytes() {
        return kept.size();
    }

    public long limitBytes() {
        return limitBytes;
    }
}
