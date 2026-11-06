package com.smartops.config;

import com.smartops.security.CurrentUserArgumentResolver;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

/**
 * SEC-08：注册 {@code @CurrentUser} 参数解析器，让 controller 直接拿到会话用户 id，
 * 不再读取客户端自报的 {@code X-User-Id} 请求头。
 */
@Configuration
public class WebMvcArgumentConfig implements WebMvcConfigurer {

    @Override
    public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new CurrentUserArgumentResolver());
    }
}
