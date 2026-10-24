package com.smartops.config;

import com.smartops.security.InternalTokenAuthenticationFilter;
import com.smartops.security.TrustedUserIdFilter;
import com.smartops.security.AccountStateFilter;
import com.smartops.security.AdminConfirmationFilter;
import com.smartops.security.UserAccountService;
import com.smartops.security.SecurityAuditService;
import com.smartops.security.SessionUser;
import com.smartops.security.AdminMfaService;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

import java.io.IOException;

@Configuration
public class SecurityConfig {
    private static final String[] INTERNAL = { "/api/model-connections/*/runtime", "/api/model-connections/*/invoke", "/api/inspector/check", "/api/inspector/verify", "/api/inspector/replan" };
    private final InternalTokenAuthenticationFilter internal;
    public SecurityConfig(InternalTokenAuthenticationFilter internal) { this.internal = internal; }

    @Bean
    CsrfTokenRepository csrfTokenRepository() { return new HttpSessionCsrfTokenRepository(); }

    @Bean
    org.springframework.security.web.session.HttpSessionEventPublisher sessionEvents() {
        return new org.springframework.security.web.session.HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, CsrfTokenRepository csrf, UserAccountService accounts, SecurityAuditService audit, HandlerMappingIntrospector introspector, AdminMfaService mfa) throws Exception {
        var administrativeRoutes = new MvcRequestMatcher(introspector, "/api/admin/**");
        http.cors(org.springframework.security.config.Customizer.withDefaults())
                .csrf(config -> config.csrfTokenRepository(csrf).csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler()).ignoringRequestMatchers(INTERNAL).ignoringRequestMatchers("/v1/models", "/v1/chat/completions")
                        // 本地图形点选校验与 /api/auth/login、/api/auth/register 一样属于匿名登录引导流程，
                        // 前端在拿到会话前无法带 CSRF 头；它只签发一次性 token，真正的登录/注册请求仍然校验 CSRF。
                        .ignoringRequestMatchers("/api/auth/human-verification/verify"))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/favicon.ico", "/actuator/health", "/error", "/api/auth/session", "/api/auth/login", "/api/auth/register", "/api/auth/registration",
                                "/api/auth/human-verification", "/api/auth/human-verification/verify").permitAll()
                        .requestMatchers(INTERNAL).permitAll()
                        .requestMatchers(HttpMethod.GET, "/v1/models").permitAll()
                        .requestMatchers(HttpMethod.POST, "/v1/chat/completions").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/auth/mfa/complete", "/api/auth/mfa/cancel").permitAll()
                        .requestMatchers(administrativeRoutes).hasRole("ADMIN")
                        .requestMatchers(HttpMethod.POST, "/api/servers", "/api/servers/**").hasRole("ADMIN")
                        .requestMatchers(HttpMethod.PUT, "/api/servers/**").hasRole("ADMIN")
                        .requestMatchers(HttpMethod.DELETE, "/api/servers/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((request, response, error) -> reply(response, 401, "请先登录"))
                        .accessDeniedHandler((request, response, error) -> reply(response, 403, "权限不足或安全令牌已失效，请刷新后重试")))
                .logout(logout -> logout.logoutUrl("/api/auth/logout").invalidateHttpSession(true).clearAuthentication(true)
                        .addLogoutHandler((request, response, auth) -> {
                            if (auth != null && auth.getPrincipal() instanceof SessionUser user) audit.record(user, "LOGOUT", user.id().toString(), "SUCCESS");
                        })
                        .deleteCookies("JSESSIONID").logoutSuccessHandler((request, response, auth) -> reply(response, 200, "已退出登录")))
                .addFilterAfter(new AccountStateFilter(accounts, mfa), SecurityContextHolderFilter.class)
                .addFilterAfter(new AdminConfirmationFilter(accounts, administrativeRoutes), AuthorizationFilter.class)
                .addFilterBefore(internal, UsernamePasswordAuthenticationFilter.class)
                .addFilterAfter(new TrustedUserIdFilter(), AnonymousAuthenticationFilter.class);
        return http.build();
    }

    private static void reply(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":" + status + ",\"message\":\"" + message + "\"}");
    }
}
