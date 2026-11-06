package com.smartops.logging;

import ch.qos.logback.classic.pattern.ClassicConverter;
import ch.qos.logback.classic.spi.ILoggingEvent;

/**
 * SEC-11 框架级日志脱敏：对 logback 输出消息中的敏感片段做掩码。
 * 注册词为 {@code maskedMsg}，用法：{@code %maskedMsg}。
 */
public class MaskingConverter extends ClassicConverter {

    @Override
    public String convert(ILoggingEvent event) {
        return LogMasker.mask(event.getFormattedMessage());
    }
}
