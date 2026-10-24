package com.smartops.common.crypto;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * API Key 加密服务。
 *
 * 使用：
 *     AES-256-GCM
 *
 * API Key 不以明文形式写入数据库。
 *
 * 环境变量：
 *
 * SMARTOPS_API_KEY_ENCRYPTION_KEY
 *
 * 要求：
 *
 *     Base64 编码后的 32 字节密钥
 */
@Service
public class AesGcmCryptoService {

    private static final String AES = "AES";

    private static final String TRANSFORMATION =
            "AES/GCM/NoPadding";

    private static final int IV_LENGTH = 12;

    private static final int TAG_LENGTH = 128;

    private final byte[] secretKey;

    private final SecureRandom secureRandom =
            new SecureRandom();

    public AesGcmCryptoService(
            @Value("${smartops.security.api-key-encryption-key:}")
            String encodedKey
    ) {
        if (encodedKey == null ||
                encodedKey.isBlank()) {

            throw new IllegalStateException(
                    "未配置 SMARTOPS_API_KEY_ENCRYPTION_KEY"
            );
        }

        try {
            this.secretKey =
                    Base64.getDecoder()
                            .decode(encodedKey);
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException(
                    "SMARTOPS_API_KEY_ENCRYPTION_KEY 不是有效 Base64",
                    e
            );
        }

        if (this.secretKey.length != 32) {
            throw new IllegalStateException(
                    "API Key 加密密钥必须为 32 字节"
            );
        }
    }

    public String encrypt(String plainText) {
        if (plainText == null ||
                plainText.isBlank()) {

            throw new IllegalArgumentException(
                    "待加密内容不能为空"
            );
        }

        try {
            byte[] iv =
                    new byte[IV_LENGTH];

            secureRandom.nextBytes(iv);

            Cipher cipher =
                    Cipher.getInstance(
                            TRANSFORMATION
                    );

            SecretKeySpec key =
                    new SecretKeySpec(
                            secretKey,
                            AES
                    );

            GCMParameterSpec spec =
                    new GCMParameterSpec(
                            TAG_LENGTH,
                            iv
                    );

            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    key,
                    spec
            );

            byte[] encrypted =
                    cipher.doFinal(
                            plainText.getBytes(
                                    StandardCharsets.UTF_8
                            )
                    );

            byte[] combined =
                    new byte[
                            iv.length
                                    + encrypted.length
                            ];

            System.arraycopy(
                    iv,
                    0,
                    combined,
                    0,
                    iv.length
            );

            System.arraycopy(
                    encrypted,
                    0,
                    combined,
                    iv.length,
                    encrypted.length
            );

            return Base64.getEncoder()
                    .encodeToString(
                            combined
                    );

        } catch (Exception e) {
            throw new IllegalStateException(
                    "API Key 加密失败",
                    e
            );
        }
    }

    public String decrypt(String cipherText) {
        if (cipherText == null ||
                cipherText.isBlank()) {

            throw new IllegalArgumentException(
                    "密文不能为空"
            );
        }

        try {
            byte[] combined =
                    Base64.getDecoder()
                            .decode(cipherText);

            if (combined.length <= IV_LENGTH) {
                throw new IllegalArgumentException(
                        "密文格式无效"
                );
            }

            byte[] iv =
                    new byte[IV_LENGTH];

            byte[] encrypted =
                    new byte[
                            combined.length
                                    - IV_LENGTH
                            ];

            System.arraycopy(
                    combined,
                    0,
                    iv,
                    0,
                    IV_LENGTH
            );

            System.arraycopy(
                    combined,
                    IV_LENGTH,
                    encrypted,
                    0,
                    encrypted.length
            );

            Cipher cipher =
                    Cipher.getInstance(
                            TRANSFORMATION
                    );

            SecretKeySpec key =
                    new SecretKeySpec(
                            secretKey,
                            AES
                    );

            GCMParameterSpec spec =
                    new GCMParameterSpec(
                            TAG_LENGTH,
                            iv
                    );

            cipher.init(
                    Cipher.DECRYPT_MODE,
                    key,
                    spec
            );

            byte[] plainText =
                    cipher.doFinal(
                            encrypted
                    );

            return new String(
                    plainText,
                    StandardCharsets.UTF_8
            );

        } catch (Exception e) {
            throw new IllegalStateException(
                    "API Key 解密失败",
                    e
            );
        }
    }
}