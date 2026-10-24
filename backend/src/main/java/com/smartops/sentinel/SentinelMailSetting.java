package com.smartops.sentinel;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.Properties;

/**
 * 邮件渠道配置与发送。
 *
 * <p><b>为什么这是一个独立的 Component 而不是几个 @Value</b>：邮件需要 6 个以上参数
 * （主机、端口、账号、密码、发件人、收件人、TLS），散落成构造参数会让 {@link SentinelNotifier}
 * 的签名难以阅读。同时"是否已配置"是一个整体判断——缺任何一项都不该尝试发信。</p>
 *
 * <p><b>未配置时不发信</b>：{@link #configured()} 为 false 时调用方记 `not_configured`。
 * 这是本轮最重要的一条：宁可显示"没配"，也不能在没发出去的情况下写"已发送"。</p>
 */
@Component
public class SentinelMailSetting {

    private static final Logger log = LoggerFactory.getLogger(SentinelMailSetting.class);

    private final String host;
    private final int port;
    private final String username;
    private final String password;
    private final String from;
    private final boolean startTls;
    private final long timeoutMillis;

    public SentinelMailSetting(
            @Value("${smartops.sentinel.notify.email.host:}") String host,
            @Value("${smartops.sentinel.notify.email.port:25}") int port,
            @Value("${smartops.sentinel.notify.email.username:}") String username,
            @Value("${smartops.sentinel.notify.email.password:}") String password,
            @Value("${smartops.sentinel.notify.email.from:}") String from,
            @Value("${smartops.sentinel.notify.email.starttls:false}") boolean startTls,
            @Value("${smartops.sentinel.notify.email.timeout-ms:8000}") long timeoutMillis) {
        this.host = host == null ? "" : host.trim();
        this.port = port;
        this.username = username == null ? "" : username.trim();
        this.password = password == null ? "" : password;
        this.from = from == null ? "" : from.trim();
        this.startTls = startTls;
        this.timeoutMillis = Math.max(1000, timeoutMillis);
    }

    /** 主机与发件人都必须有；有账号才需要密码。缺一项就视为未配置。 */
    public boolean configured() {
        return !host.isEmpty() && !from.isEmpty() && port > 0
                && (username.isEmpty() || !password.isEmpty());
    }

    /** 收件人来自规则配置，不在这里定死。 */
    public Properties properties() {
        Properties properties = new Properties();
        properties.put("mail.smtp.host", host);
        properties.put("mail.smtp.port", String.valueOf(port));
        properties.put("mail.smtp.connectiontimeout", String.valueOf(timeoutMillis));
        properties.put("mail.smtp.timeout", String.valueOf(timeoutMillis));
        properties.put("mail.smtp.writetimeout", String.valueOf(timeoutMillis));
        // 默认不信任任意证书：开启 STARTTLS 但保持校验，避免把凭据发给伪装服务器
        properties.put("mail.smtp.starttls.enable", String.valueOf(startTls));
        properties.put("mail.smtp.auth", String.valueOf(!username.isEmpty()));
        return properties;
    }

    public String host() { return host; }
    public int port() { return port; }
    public String username() { return username; }
    public String password() { return password; }
    public String from() { return from; }

    /** 日志与错误信息里用的自述，**不含密码**。 */
    public String describe() {
        return host + ":" + port + (username.isEmpty() ? "（无认证）" : "（账号 " + username + "）");
    }

    void logIfMisconfigured() {
        if (!configured() && (!host.isEmpty() || !from.isEmpty())) {
            log.warn("sentinel email channel partially configured (host='{}', from='{}'), will report not_configured",
                    host, from);
        }
    }
}
