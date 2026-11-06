package com.smartops.security;

import com.smartops.exception.BusinessException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.MethodParameter;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

/**
 * SEC-08：解析 {@link CurrentUser} 标注的参数。
 *
 * <p>身份来源是认证主体 {@link SessionUser}，而不是客户端请求头；
 * 无会话主体时 401 fail-closed（不再有 {@code defaultValue = "1"} 的回落）。</p>
 */
public class CurrentUserArgumentResolver implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        if (!parameter.hasParameterAnnotation(CurrentUser.class)) {
            return false;
        }
        Class<?> type = parameter.getParameterType();
        return Long.class.equals(type) || long.class.equals(type) || SessionUser.class.equals(type);
    }

    @Override
    public Object resolveArgument(MethodParameter parameter, ModelAndViewContainer mavContainer,
                                  NativeWebRequest webRequest, WebDataBinderFactory binderFactory) {
        HttpServletRequest request = webRequest.getNativeRequest(HttpServletRequest.class);
        if (request == null) {
            throw new BusinessException(401, "需要登录会话");
        }
        SessionUser user = CurrentSessions.require(request);
        Class<?> type = parameter.getParameterType();
        if (SessionUser.class.equals(type)) {
            return user;
        }
        return user.id();
    }
}
