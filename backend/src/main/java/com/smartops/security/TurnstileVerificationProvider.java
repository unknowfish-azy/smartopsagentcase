package com.smartops.security;

import com.fasterxml.jackson.databind.JsonNode;
import com.smartops.exception.BusinessException;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;

import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;

/**
 * Cloudflare Turnstile 供应商（可选）。配置了 site-key / secret-key / hostnames 时由
 * {@link HumanVerificationProviderConfig} 装配；未配置时改用 {@link LocalGraphicalVerificationProvider}。
 */
public class TurnstileVerificationProvider implements HumanVerificationProvider {
    static final String ENDPOINT = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
    private final HumanVerificationSettings settings;
    private final RestClient client;

    public TurnstileVerificationProvider(HumanVerificationSettings settings) {
        this(settings, createClient());
    }

    TurnstileVerificationProvider(HumanVerificationSettings settings, RestClient client) {
        this.settings = settings;
        this.client = client;
    }

    private static RestClient createClient() {
        var transport = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).followRedirects(HttpClient.Redirect.NEVER).build();
        var factory = new JdkClientHttpRequestFactory(transport);
        factory.setReadTimeout(Duration.ofSeconds(5));
        return RestClient.builder().requestFactory(factory).build();
    }

    @Override
    public Result verify(String token) {
        var body = new LinkedMultiValueMap<String, String>();
        body.add("secret", settings.secretKey);
        body.add("response", token);
        try {
            JsonNode result = client.post().uri(ENDPOINT).contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .body(body).retrieve().body(JsonNode.class);
            if (result == null || !result.path("success").isBoolean()) throw new IllegalStateException();
            if (!result.path("success").booleanValue()) return new Result(false, null, null, null, null);
            return new Result(true, result.path("hostname").asText(), result.path("action").asText(),
                    result.path("cdata").asText(), Instant.parse(result.path("challenge_ts").asText()));
        } catch (Exception unavailable) {
            throw new BusinessException(503, "人机验证服务暂时不可用，请稍后重试");
        }
    }
}
