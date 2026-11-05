package com.smartops.cloud;

import com.smartops.common.crypto.AesGcmCryptoService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 凭据引用解析（OPS-02）。
 *
 * 支持两种引用，二者都不把明文写进 cloud_account：
 *   credential:<operation_credential.id>  归属账号所有者，密文用既有 AES-GCM 解密
 *   env:<ENVIRONMENT_VARIABLE>            由部署方注入，值为 accessKeyId:accessKeySecret
 *
 * 解析失败一律给出稳定错误码，不回落、不打印明文。
 */
@Component
public class CloudCredentialResolver {

    private final JdbcTemplate jdbc;
    private final AesGcmCryptoService crypto;

    public CloudCredentialResolver(JdbcTemplate jdbc, AesGcmCryptoService crypto) {
        this.jdbc = jdbc;
        this.crypto = crypto;
    }

    public static boolean isValidRef(String credentialRef) {
        if (credentialRef == null) {
            return false;
        }
        String ref = credentialRef.trim();
        if (ref.startsWith("credential:")) {
            return ref.length() > "credential:".length() && ref.substring("credential:".length()).chars().allMatch(Character::isDigit);
        }
        if (ref.startsWith("env:")) {
            String name = ref.substring("env:".length());
            return !name.isBlank() && name.chars().allMatch(ch -> Character.isLetterOrDigit(ch) || ch == '_');
        }
        return false;
    }

    public CloudCredentials resolve(Long ownerUserId, String credentialRef) {
        if (!isValidRef(credentialRef)) {
            throw new CloudProviderException("CLOUD_CREDENTIAL_REF_INVALID",
                    "凭据引用无效，仅支持 credential:<id> 或 env:<NAME>");
        }
        String ref = credentialRef.trim();
        String plaintext;
        if (ref.startsWith("credential:")) {
            plaintext = fromCredentialStore(ownerUserId, Long.parseLong(ref.substring("credential:".length())));
        } else {
            String name = ref.substring("env:".length());
            plaintext = System.getenv(name);
            if (plaintext == null || plaintext.isBlank()) {
                throw new CloudProviderException("CLOUD_CREDENTIAL_UNAVAILABLE",
                        "环境变量 " + name + " 未设置，无法读取云账号凭据");
            }
        }
        return parseSecret(plaintext);
    }

    private String fromCredentialStore(Long ownerUserId, long credentialId) {
        // 只允许账号所有者本人的凭据，避免跨团队借用他人密钥。
        List<String> ciphertext = jdbc.queryForList(
                "SELECT secret_ciphertext FROM operation_credential WHERE id=? AND user_id=?",
                String.class, credentialId, ownerUserId);
        if (ciphertext.isEmpty()) {
            throw new CloudProviderException("CLOUD_CREDENTIAL_UNAVAILABLE", "凭据不存在或不属于该账号所有者");
        }
        try {
            return crypto.decrypt(ciphertext.get(0));
        } catch (RuntimeException e) {
            throw new CloudProviderException("CLOUD_CREDENTIAL_UNREADABLE",
                    "凭据解密失败，请检查加密密钥配置", false, e);
        }
    }

    private CloudCredentials parseSecret(String plaintext) {
        int separator = plaintext.indexOf(':');
        if (separator <= 0 || separator == plaintext.length() - 1) {
            throw new CloudProviderException("CLOUD_CREDENTIAL_MALFORMED",
                    "凭据格式应为 accessKeyId:accessKeySecret");
        }
        return new CloudCredentials(plaintext.substring(0, separator), plaintext.substring(separator + 1));
    }
}
