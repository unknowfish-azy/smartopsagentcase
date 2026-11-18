package com.smartops.config;

import static org.assertj.core.api.Assertions.assertThatCode;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockServletContext;

/**
 * 桥 WS 帧上限配置回归测试。
 *
 * <p>背景：servlet 容器默认文本帧上限 8192 字节，而桥把关键帧以 base64 塞进 JSON，
 * 一张真实帧就有数十 KB，曾经因此第一帧就断链、帧永远进不了归档。
 * 同时这个配置必须能在没有真实 WS 容器的环境（集成测试 MOCK servlet）里安全降级，
 * 否则会把整个 ApplicationContext 带崩。</p>
 */
class RobotWebSocketBufferConfigTest {

    @Test
    void 没有WS容器时应安全跳过而不是抛异常() {
        RobotWebSocketBufferConfig config = new RobotWebSocketBufferConfig(12_582_912);

        assertThatCode(() -> config.setServletContext(new MockServletContext()))
                .doesNotThrowAnyException();
    }
}
