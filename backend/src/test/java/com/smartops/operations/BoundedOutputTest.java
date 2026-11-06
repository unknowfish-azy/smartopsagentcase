package com.smartops.operations;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Arrays;

import static org.assertj.core.api.Assertions.assertThat;

class BoundedOutputTest {
    @Test
    void keepsOnlyBudgetAndFlagsTruncationForHugeOutput() throws IOException {
        int limit = 64 * 1024;
        BoundedOutput output = new BoundedOutput(limit);
        byte[] chunk = new byte[1024];
        Arrays.fill(chunk, (byte) 'x');
        // 100 MB 输出：只应保留限额内的字节，不能按原量级进入堆内存。
        for (int index = 0; index < 100 * 1024; index++) {
            output.stream().write(chunk);
        }

        assertThat(output.keptBytes()).isLessThanOrEqualTo(limit);
        assertThat(output.truncated()).isTrue();
        assertThat(output.text().length()).isLessThanOrEqualTo(limit);
    }

    @Test
    void doesNotFlagTruncationWhenOutputFitsBudget() throws IOException {
        BoundedOutput output = new BoundedOutput(1024);
        output.stream().write("hello".getBytes(java.nio.charset.StandardCharsets.UTF_8));

        assertThat(output.text()).isEqualTo("hello");
        assertThat(output.truncated()).isFalse();
    }

    @Test
    void singleByteWritesAlsoRespectBudget() throws IOException {
        BoundedOutput output = new BoundedOutput(3);
        output.stream().write('a');
        output.stream().write('b');
        output.stream().write('c');
        output.stream().write('d');

        assertThat(output.text()).isEqualTo("abc");
        assertThat(output.truncated()).isTrue();
    }
}
