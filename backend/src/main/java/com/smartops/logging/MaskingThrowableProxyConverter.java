package com.smartops.logging;

import ch.qos.logback.classic.pattern.ThrowableProxyConverter;
import ch.qos.logback.classic.spi.IThrowableProxy;

/**
 * SEC-11 框架级日志脱敏：对异常栈输出（含首行 {@code ExceptionClass: message}）做掩码。
 * 注册词为 {@code maskedEx}，用法：{@code %maskedEx}。
 *
 * <p>异常消息可能携带含敏感查询参数的 URL、凭据等，需在落盘/控制台输出前脱敏。</p>
 */
public class MaskingThrowableProxyConverter extends ThrowableProxyConverter {

    @Override
    protected String throwableProxyToString(IThrowableProxy tp) {
        return LogMasker.mask(super.throwableProxyToString(tp));
    }
}
