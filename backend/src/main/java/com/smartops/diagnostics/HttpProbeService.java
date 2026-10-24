package com.smartops.diagnostics;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartops.exception.BusinessException;
import com.smartops.security.SessionUser;
import org.springframework.stereotype.Service;
import java.net.SocketTimeoutException;
import java.util.Locale;

@Service
public class HttpProbeService {
    private final DiagnosticTargetPolicy policy;
    private final DiagnosticProbeLimiter limiter;
    private final DiagnosticTransport transport;
    private final ObjectMapper json;

    public HttpProbeService(DiagnosticTargetPolicy policy, DiagnosticProbeLimiter limiter, DiagnosticTransport transport, ObjectMapper json) {
        this.policy = policy;
        this.limiter = limiter;
        this.transport = transport;
        this.json = json;
    }

    public Result check(SessionUser user, Request request) {
        var target = policy.require(user, request.targetId());
        String method = request.method() == null ? "GET" : request.method().toUpperCase(Locale.ROOT);
        if (!method.equals("GET") && !method.equals("HEAD")) throw new BusinessException(400, "HTTP 检查仅支持 GET 或 HEAD");
        if (method.equals("HEAD") && request.assertionPath() != null) throw new BusinessException(400, "HEAD 请求不能检查正文断言");
        if (request.assertionPath() != null && !request.assertionPath().matches("[A-Za-z0-9_.-]{1,128}(\\.[A-Za-z0-9_.-]{1,128})*")) throw new BusinessException(400, "JSON 断言路径无效");
        validateAssertion(request);
        try (var lease = limiter.acquire(user.id())) {
            long started = System.nanoTime();
            DiagnosticTransport.HttpResult response;
            try {
                response = transport.http(target, method);
            } catch (SocketTimeoutException ex) {
                return failed("TIMEOUT", "目标连接或读取超时", started);
            } catch (javax.net.ssl.SSLException ex) {
                return failed("TLS_ERROR", "TLS 握手或证书校验失败", started);
            } catch (java.net.ConnectException ex) {
                return failed("CONNECTION_REFUSED", "目标拒绝连接", started);
            } catch (Exception ex) {
                return failed("NETWORK_ERROR", "无法完成目标检查", started);
            }
            String assertion = evaluate(response, request);
            String status = response.statusCode() == target.expectedStatus()
                    && (assertion.equals("PASS") || assertion.equals("NOT_REQUESTED")) ? "HEALTHY" : "UNHEALTHY";
            String errorCategory = status.equals("HEALTHY") ? null
                    : "ASSERTION";
            return new Result(status, response.statusCode(), elapsed(started), response.body().length, response.truncated(), assertion,
                    "检查完成", status.equals("HEALTHY") ? "无需处理" : "核对目标状态码、路径和服务日志", errorCategory);
        }
    }

    private static void validateAssertion(Request request) {
        if (request.assertionPath() == null) return;
        String type = request.assertionType() == null ? "exists" : request.assertionType();
        if (!type.equals("exists") && !type.equals("equals")) throw new BusinessException(400, "JSON 断言类型无效");
        if (type.equals("equals") && request.expectedValue() == null) throw new BusinessException(400, "相等断言需要期望值");
    }

    private String evaluate(DiagnosticTransport.HttpResult response, Request request) {
        if (request.assertionPath() == null) return "NOT_REQUESTED";
        if (response.truncated()) return "UNKNOWN";
        try {
            JsonNode node = json.readTree(response.body());
            for (String part : request.assertionPath().split("\\.")) node = node == null ? null : node.get(part);
            if (node == null) return "FAIL";
            return switch (request.assertionType() == null ? "exists" : request.assertionType()) {
                case "exists" -> "PASS";
                case "equals" -> node.equals(request.expectedValue()) ? "PASS" : "FAIL";
                default -> throw new BusinessException(400, "JSON 断言类型无效");
            };
        } catch (BusinessException ex) {
            throw ex;
        } catch (Exception ex) {
            return "UNKNOWN";
        }
    }

    private Result failed(String code, String message, long started) {
        String category = code.equals("TIMEOUT") ? "TIMEOUT" : "NETWORK";
        return new Result("UNHEALTHY", 0, elapsed(started), 0, false, code, message, "检查目标配置、网络和证书", category);
    }

    private static long elapsed(long started) { return Math.max(0, (System.nanoTime() - started) / 1_000_000); }

    public record Request(String targetId, String method, String assertionPath, String assertionType, JsonNode expectedValue) {}

    public record Result(String status, int statusCode, long durationMs, int responseBytes, boolean truncated,
            String assertion, String summary, String nextAction, String errorCategory) {
        public Result(String status, int statusCode, long durationMs, int responseBytes, boolean truncated,
                String assertion, String summary, String nextAction) {
            this(status, statusCode, durationMs, responseBytes, truncated, assertion, summary, nextAction, null);
        }
    }
}
