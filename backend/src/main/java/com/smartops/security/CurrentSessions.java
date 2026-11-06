package com.smartops.security;

import com.smartops.exception.BusinessException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;

/**
 * SEC-08/SEC-15：统一从认证主体解析用户身份，绝不信任客户端自报的 {@code X-User-Id} 头。
 *
 * <p>session 认证下 principal 链为 {@code Authentication -> SessionUser}；
 * 内部 token 认证的 principal 不是 SessionUser（系统语义，无归属用户）。</p>
 */
public final class CurrentSessions {

    private CurrentSessions() { }

    /** 必须是登录会话用户；否则 401 fail-closed（不落 default 1）。 */
    public static SessionUser require(HttpServletRequest request) {
        SessionUser user = optional(request);
        if (user == null) throw new BusinessException(401, "需要登录会话");
        return user;
    }

    /** 登录会话用户；内部 token/匿名返回 null，由调用方决定 fail-closed 语义。 */
    public static SessionUser optional(HttpServletRequest request) {
        var principal = request.getUserPrincipal();
        if (principal instanceof Authentication authentication
                && authentication.getPrincipal() instanceof SessionUser user) {
            return user;
        }
        return null;
    }
}
