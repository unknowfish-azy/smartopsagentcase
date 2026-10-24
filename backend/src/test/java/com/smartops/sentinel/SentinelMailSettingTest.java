package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 邮件渠道的"是否已配置"判定。
 *
 * <p>这个判定的重要性在于：错判成"已配置"会在没发信的情况下写出 `sent`，
 * 让运维误以为通知到了。所以只要缺必填项就必须是未配置。</p>
 */
class SentinelMailSettingTest {

    private static SentinelMailSetting setting(String host, int port, String user, String pass, String from) {
        return new SentinelMailSetting(host, port, user, pass, from, false, 8000);
    }

    @Test
    @DisplayName("默认配置（未填任何项）视为未配置")
    void emptyIsNotConfigured() {
        assertFalse(setting("", 25, "", "", "").configured());
    }

    @Test
    @DisplayName("只有主机没有发件人，不算配置完整")
    void hostWithoutFromIsNotConfigured() {
        assertFalse(setting("smtp.example.test", 587, "", "", "").configured());
    }

    @Test
    @DisplayName("主机 + 发件人即可（无认证的中继）")
    void hostAndFromIsConfigured() {
        assertTrue(setting("smtp.example.test", 25, "", "", "ops@example.test").configured());
    }

    @Test
    @DisplayName("有账号却没有密码，视为配置不完整而不是无认证")
    void userWithoutPasswordIsNotConfigured() {
        // 否则会用空密码去认证，得到一个含糊的认证失败而不是"没配好"
        assertFalse(setting("smtp.example.test", 587, "ops@example.test", "", "ops@example.test").configured());
    }

    @Test
    @DisplayName("账号 + 密码 + 发件人完整")
    void fullCredentialsAreConfigured() {
        assertTrue(setting("smtp.example.test", 587, "ops@example.test", "secret", "ops@example.test").configured());
    }

    @Test
    @DisplayName("端口为 0 视为未配置（避免连到随机端口）")
    void zeroPortIsNotConfigured() {
        assertFalse(setting("smtp.example.test", 0, "", "", "ops@example.test").configured());
    }

    @Test
    @DisplayName("自述信息不包含密码")
    void describeNeverLeaksPassword() {
        String described = setting("smtp.example.test", 587, "ops@example.test", "topsecret", "ops@example.test").describe();
        assertTrue(described.contains("smtp.example.test"));
        assertTrue(described.contains("587"));
        assertNotEquals(true, described.contains("topsecret"), "密码绝不能出现在日志自述里");
    }

    @Test
    @DisplayName("properties 反映认证与 STARTTLS 设置")
    void propertiesMirrorConfiguration() {
        var withAuth = new SentinelMailSetting("smtp.example.test", 587, "ops@example.test", "secret", "ops@example.test", true, 5000);
        assertTrue(Boolean.parseBoolean(withAuth.properties().getProperty("mail.smtp.auth")));
        assertTrue(Boolean.parseBoolean(withAuth.properties().getProperty("mail.smtp.starttls.enable")));
        assertTrue(Boolean.parseBoolean(withAuth.properties().getProperty("mail.smtp.starttls.enable")),
                "STARTTLS 开启时仍保持证书校验（不设置 trust 全放行）");
        assertFalse(withAuth.properties().containsKey("mail.smtp.ssl.trust"),
                "不得为了连通性关闭证书校验");

        var withoutAuth = setting("smtp.example.test", 25, "", "", "ops@example.test");
        assertFalse(Boolean.parseBoolean(withoutAuth.properties().getProperty("mail.smtp.auth")));
    }
}
