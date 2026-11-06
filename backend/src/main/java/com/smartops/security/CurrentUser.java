package com.smartops.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * SEC-08/SEC-15：标注在 controller 方法参数上，从已认证的会话主体解析当前用户 id，
 * 而不是信任客户端自报的 {@code X-User-Id} 请求头。
 *
 * <p>支持的参数类型：
 * <ul>
 *   <li>{@code Long} —— 解析为 {@link SessionUser#id()}（最常见用法）</li>
 *   <li>{@link SessionUser} —— 解析为完整会话主体</li>
 * </ul>
 * 非会话主体（匿名 / 内部 token）会 fail-closed：返回 401，不再回落到 {@code defaultValue = "1"}。
 *
 * @see CurrentUserArgumentResolver
 */
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentUser {
}
