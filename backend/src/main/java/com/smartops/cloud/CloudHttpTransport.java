package com.smartops.cloud;

import java.io.IOException;
import java.util.List;
import java.util.Map;

/**
 * 云 API HTTP 传输层的最小抽象。
 *
 * 单独抽出来是为了让签名、分页、退避、错误映射可以在没有真实云账号的环境里
 * 用替身响应验证，而不是靠"文件存在"判断适配器可用。
 */
public interface CloudHttpTransport {

    Response post(String uri, Map<String, String> headers, String body) throws IOException, InterruptedException;

    /**
     * 只读 GET（华为云 ECS 清单使用）。默认实现显式失败，
     * 避免测试替身未实现时静默返回空页而被误判为"同步成功"。
     */
    default Response get(String uri, Map<String, String> headers) throws IOException, InterruptedException {
        throw new UnsupportedOperationException("GET 传输未实现");
    }

    record Response(int status, Map<String, List<String>> headers, String body) {

        public String header(String name) {
            if (headers == null || name == null) {
                return null;
            }
            for (Map.Entry<String, List<String>> entry : headers.entrySet()) {
                if (entry.getKey() != null && entry.getKey().equalsIgnoreCase(name) && !entry.getValue().isEmpty()) {
                    return entry.getValue().get(0);
                }
            }
            return null;
        }
    }
}
