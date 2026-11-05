package com.smartops.diagnostics.database;

import com.smartops.common.crypto.AesGcmCryptoService;
import com.smartops.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 数据库诊断凭据解析（OPS-07）。
 *
 * <p>引用格式与 {@link com.smartops.cloud.CloudCredentialResolver} 保持一致：
 * {@code credential:<operation_credential.id>} 走 AES-GCM 密文，
 * {@code env:<NAME>} 由部署方注入。owner 隔离由 SQL 的 {@code user_id=?} 保证，
 * 即使拿到他人的 credential id 也读不出密文。</p>
 *
 * <p>明文格式固定为 {@code username:password}，在<b>第一个</b>冒号处切分，
 * 因此密码本身可以包含冒号。失败一律给稳定错误码，且 {@link DatabaseCredential#toString()}
 * 不输出密码。</p>
 */
@Component
public class DatabaseCredentialResolver {

    private final JdbcTemplate jdbc;
    private final AesGcmCryptoService crypto;

    public DatabaseCredentialResolver(JdbcTemplate jdbc, AesGcmCryptoService crypto) {
        this.jdbc = jdbc;
        this.crypto = crypto;
    }

    public static boolean isValidRef(String credentialRef) {
        if (credentialRef == null) {
            return false;
        }
        String ref = credentialRef.trim();
        if (ref.startsWith("credential:")) {
            String id = ref.substring("credential:".length());
            return !id.isEmpty() && id.chars().allMatch(Character::isDigit);
        }
        if (ref.startsWith("env:")) {
            String name = ref.substring("env:".length());
            return !name.isBlank() && name.chars().allMatch(ch -> Character.isLetterOrDigit(ch) || ch == '_');
        }
        return false;
    }

    public DatabaseCredential resolve(Long ownerUserId, String credentialRef) {
        if (!isValidRef(credentialRef)) {
            throw new BusinessException(400,
                    "DB_CREDENTIAL_REF_INVALID: 凭据引用无效，仅支持 credential:<id> 或 env:<NAME>");
        }
        String ref = credentialRef.trim();
        String plaintext;
        String source;
        if (ref.startsWith("credential:")) {
            source = "CREDENTIAL_STORE";
            plaintext = fromCredentialStore(ownerUserId, Long.parseLong(ref.substring("credential:".length())));
        } else {
            source = "ENV";
            String name = ref.substring("env:".length());
            plaintext = System.getenv(name);
            if (plaintext == null || plaintext.isBlank()) {
                throw new BusinessException(400, "DB_CREDENTIAL_UNAVAILABLE: 环境变量 " + name + " 未设置");
            }
        }
        return parseSecret(plaintext, source);
    }

    private String fromCredentialStore(Long ownerUserId, long credentialId) {
        // 只允许账号所有者本人的凭据，避免跨团队借用他人数据库账号。
        List<String> ciphertext = jdbc.queryForList(
                "SELECT secret_ciphertext FROM operation_credential WHERE id=? AND user_id=?",
                String.class, credentialId, ownerUserId);
        if (ciphertext.isEmpty()) {
            throw new BusinessException(400, "DB_CREDENTIAL_UNAVAILABLE: 凭据不存在或不属于该账号所有者");
        }
        try {
            return crypto.decrypt(ciphertext.get(0));
        } catch (RuntimeException e) {
            // 解密失败的原因（密钥错误）对调用方没有意义，但要与"凭据不存在"区分开。
            throw new BusinessException(400, "DB_CREDENTIAL_UNREADABLE: 凭据解密失败，请检查加密密钥配置");
        }
    }

    private DatabaseCredential parseSecret(String plaintext, String source) {
        int separator = plaintext.indexOf(':');
        if (separator <= 0 || separator == plaintext.length() - 1) {
            throw new BusinessException(400, "DB_CREDENTIAL_MALFORMED: 凭据格式应为 username:password");
        }
        return new DatabaseCredential(plaintext.substring(0, separator), plaintext.substring(separator + 1), source);
    }

    /** 解析结果；toString 只暴露用户名与来源，密码永不出现在日志里。 */
    public record DatabaseCredential(String username, String password, String source) {
        @Override
        public String toString() {
            return "DatabaseCredential[username=" + username + ", password=****, source=" + source + "]";
        }
    }
}
