package com.smartops.sentinel;

import com.smartops.service.TeamNotificationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Properties;
import java.util.Map;
import java.util.Set;

/**
 * 告警通知投递器。
 *
 * <p>三种渠道的**真实能力边界**必须说清，不能一律写"已发送"：</p>
 *
 * <table>
 *   <tr><th>渠道</th><th>当前实现</th></tr>
 *   <tr><td>站内</td><td>复用既有 {@link TeamNotificationService}，真实写入</td></tr>
 *   <tr><td>Webhook</td><td>真实 HTTP POST（带重试），受 SSRF 策略约束</td></tr>
 *   <tr><td>邮件</td><td>**未接入 SMTP**：如实记 `not_configured`，不谎称已发送</td></tr>
 * </table>
 *
 * <p>为什么不假装支持邮件：发邮件需要 SMTP 主机、凭据与出站白名单，这些属于部署配置。
 * 在没有配置的情况下返回"已发送"，等于给运维一个虚假的"已经通知到了"的判断 ——
 * 那比不通知更危险。</p>
 */
@Service
public class SentinelNotifier {

    private static final Logger log = LoggerFactory.getLogger(SentinelNotifier.class);

    /** 单次投递结果。 */
    public enum Outcome {
        SENT("sent"), FAILED("failed"), NOT_CONFIGURED("not_configured"), REJECTED("rejected");
        private final String code;
        Outcome(String code) { this.code = code; }
        public String code() { return code; }
    }

    private final JdbcTemplate jdbc;
    private final TeamNotificationService notifications;
    private final Clock clock;
    private final int maxAttempts;
    private final Set<String> allowedWebhookHosts;
    private final HttpClient client;
    private final Duration readTimeout;
    private final SentinelMailSetting mail;

    public SentinelNotifier(JdbcTemplate jdbc, TeamNotificationService notifications,
                            @org.springframework.beans.factory.annotation.Qualifier("mfaClock") Clock clock,
                            @Value("${smartops.sentinel.notify.webhook.max-attempts:2}") int maxAttempts,
                            @Value("${smartops.sentinel.notify.webhook.allow-hosts:}") String allowHosts,
                            @Value("${smartops.sentinel.notify.webhook.connect-timeout-ms:3000}") long connectTimeoutMs,
                            @Value("${smartops.sentinel.notify.webhook.read-timeout-ms:5000}") long readTimeoutMs,
                            SentinelMailSetting mail) {
        this.jdbc = jdbc;
        this.notifications = notifications;
        this.clock = clock;
        this.maxAttempts = Math.max(1, Math.min(5, maxAttempts));
        this.allowedWebhookHosts = SentinelWebhookPolicy.parseAllowedHosts(allowHosts);
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(Math.max(500, connectTimeoutMs)))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        this.readTimeout = Duration.ofMillis(Math.max(500, readTimeoutMs));
        this.mail = mail;
    }

    /**
     * 投递一条告警的全部渠道。
     *
     * <p>逐渠道记录结果（`sent` / `failed` / `not_configured` / `rejected`），
     * 让"发出去了"和"对方收到了"可区分。</p>
     */
    public Map<String, String> deliver(long alertId, long userId, String channels, String webhookUrl,
                                       String emailTo, String title, String body) {
        Map<String, String> results = new LinkedHashMap<>();
        // 先清掉该告警的旧投递记录，避免多次通知时状态叠加、无法判断最新一次
        jdbc.update("DELETE FROM sentinel_notification WHERE alert_id=?", alertId);

        for (String rawChannel : (channels == null ? "inapp" : channels).split(",")) {
            String channel = rawChannel.trim();
            if (channel.isEmpty()) continue;
            switch (channel) {
                case "inapp" -> results.put(channel, deliverInApp(alertId, userId, title, body).code());
                case "webhook" -> results.put(channel, deliverWebhook(alertId, webhookUrl, title, body).code());
                case "email" -> results.put(channel, deliverEmail(alertId, emailTo, title, body).code());
                default -> results.put(channel, record(alertId, channel, null,
                        Outcome.REJECTED, "不支持的渠道").code());
            }
        }
        return results;
    }

    /**
     * 邮件投递。
     *
     * <p>三种状态要分清：</p>
     * <ul>
     *   <li>{@code not_configured} —— 没配 SMTP 主机或发件人，**不尝试发信**；</li>
     *   <li>{@code rejected} —— 配了但缺收件人，属于规则没填全；</li>
     *   <li>{@code sent} / {@code failed} —— 真实发送的结果。</li>
     * </ul>
     */
    private Outcome deliverEmail(long alertId, String to, String title, String body) {
        if (!mail.configured()) {
            mail.logIfMisconfigured();
            return record(alertId, "email", to, Outcome.NOT_CONFIGURED,
                    "未配置 SMTP（需要 smartops.sentinel.notify.email.host 与 from）");
        }
        if (to == null || to.isBlank()) {
            return record(alertId, "email", null, Outcome.REJECTED, "规则未填写收件人");
        }
        try {
            Properties properties = mail.properties();
            jakarta.mail.Session session;
            if (mail.username().isEmpty()) {
                session = jakarta.mail.Session.getInstance(properties);
            } else {
                session = jakarta.mail.Session.getInstance(properties,
                        new jakarta.mail.Authenticator() {
                            @Override protected jakarta.mail.PasswordAuthentication getPasswordAuthentication() {
                                return new jakarta.mail.PasswordAuthentication(mail.username(), mail.password());
                            }
                        });
            }
            var message = new jakarta.mail.internet.MimeMessage(session);
            message.setFrom(new jakarta.mail.internet.InternetAddress(mail.from()));
            // 收件人用逗号或分号分隔；逐个 add 而不是拼成一个字符串，避免解析歧义
            for (String address : to.split("[,;]")) {
                String trimmed = address.trim();
                if (!trimmed.isEmpty()) {
                    message.addRecipient(jakarta.mail.Message.RecipientType.TO,
                            new jakarta.mail.internet.InternetAddress(trimmed));
                }
            }
            message.setSubject(title == null ? "智维Agent 告警" : title, "UTF-8");
            message.setText((title == null ? "" : title + "\n\n") + (body == null ? "" : body), "UTF-8");
            message.setSentDate(java.util.Date.from(clock.instant()));
            jakarta.mail.Transport.send(message);
            return record(alertId, "email", to, Outcome.SENT, null);
        } catch (Exception failure) {
            log.debug("sentinel email delivery failed", failure);
            return record(alertId, "email", to, Outcome.FAILED,
                    truncate(failure.getClass().getSimpleName() + ": " + failure.getMessage(), 400));
        }
    }

    private Outcome deliverInApp(long alertId, long userId, String title, String body) {
        try {
            notifications.notifyUser(userId, null, "SENTINEL_ALERT", String.valueOf(alertId),
                    truncate(title, 180) + (body == null || body.isBlank() ? "" : " — " + truncate(body, 300)));
            return record(alertId, "inapp", String.valueOf(userId), Outcome.SENT, null);
        } catch (RuntimeException failure) {
            return record(alertId, "inapp", String.valueOf(userId), Outcome.FAILED, truncate(failure.getMessage(), 500));
        }
    }

    private Outcome deliverWebhook(long alertId, String url, String title, String body) {
        String rejection = SentinelWebhookPolicy.rejectionReason(url, allowedWebhookHosts);
        if (rejection != null) {
            // 地址不安全：不发起请求，也不假装投递过
            return record(alertId, "webhook", url, Outcome.REJECTED, rejection);
        }
        String payload = "{\"alertId\":" + alertId
                + ",\"title\":\"" + escape(title) + "\""
                + ",\"body\":\"" + escape(body) + "\""
                + ",\"sentAt\":\"" + clock.instant() + "\"}";
        String lastError = null;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                HttpRequest request = HttpRequest.newBuilder(URI.create(url.trim()))
                        .timeout(readTimeout)
                        .header("Content-Type", "application/json; charset=utf-8")
                        .header("User-Agent", "SmartOps-Sentinel/1.0")
                        .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                        .build();
                HttpResponse<Void> response = client.send(request, HttpResponse.BodyHandlers.discarding());
                if (response.statusCode() >= 200 && response.statusCode() < 300) {
                    markAttempt(alertId, "webhook", attempt);
                    return record(alertId, "webhook", url, Outcome.SENT, null);
                }
                lastError = "HTTP " + response.statusCode();
                // 4xx 重试没有意义（对方明确拒绝），直接失败
                if (response.statusCode() >= 400 && response.statusCode() < 500) break;
            } catch (Exception failure) {
                lastError = truncate(failure.getClass().getSimpleName() + ": " + failure.getMessage(), 400);
                log.debug("sentinel webhook attempt {} failed", attempt, failure);
            }
        }
        markAttempt(alertId, "webhook", maxAttempts);
        return record(alertId, "webhook", url, Outcome.FAILED, lastError);
    }

    /** 允许投递的内网主机白名单，供规则保存时校验共用同一份配置。 */
    public Set<String> allowedWebhookHosts() {
        return allowedWebhookHosts;
    }

    /** 记录一次投递结果并返回状态。 */
    private Outcome record(long alertId, String channel, String target, Outcome outcome, String error) {
        try {
            jdbc.update("""
                    INSERT INTO sentinel_notification(alert_id,channel,target,status,attempts,error_detail,sent_at)
                    VALUES(?,?,?,?,0,?,?)
                    """, alertId, channel, truncate(target, 255), outcome.code(), truncate(error, 500),
                    Outcome.SENT.equals(outcome) ? java.sql.Timestamp.from(clock.instant()) : null);
        } catch (RuntimeException failure) {
            log.warn("sentinel notification record failed: {}", failure.getMessage());
        }
        return outcome;
    }

    private void markAttempt(long alertId, String channel, int attempts) {
        jdbc.update("UPDATE sentinel_notification SET attempts=? WHERE alert_id=? AND channel=?",
                attempts, alertId, channel);
    }

    private static String escape(String value) {
        if (value == null) return "";
        return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
    }

    private static String truncate(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }
}
