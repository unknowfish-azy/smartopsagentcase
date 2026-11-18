package com.smartops.config;

import jakarta.servlet.ServletContext;
import jakarta.websocket.server.ServerContainer;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.context.ServletContextAware;

/**
 * 放大 WS 容器的默认帧上限。
 *
 * <p>桥把关键帧以 base64 塞进 JSON 文本帧，servlet 容器的默认上限是 8KB；
 * 一张真实关键帧有数十 KB，超限会被直接断链，帧根本进不了归档。
 * 上限取 {@code smartops.robot.bridge-max-text-bytes}，与 frame-archive.max-bytes 匹配。</p>
 *
 * <p>为什么不用 {@code ServletServerContainerFactoryBean}：该 bean 在
 * MOCK servlet 环境（集成测试）里拿不到 {@code ServerContainer} 属性，
 * 会让整个 ApplicationContext 启动失败。这里改为"有容器就设置、没有就跳过"，
 * 生产运行行为一致，测试环境安全降级。</p>
 */
@Slf4j
@Component
public class RobotWebSocketBufferConfig implements ServletContextAware {

    /** Jakarta WebSocket 规范约定的 ServletContext 属性名。 */
    private static final String SERVER_CONTAINER_ATTRIBUTE = "jakarta.websocket.server.ServerContainer";

    private final int maxTextBytes;

    public RobotWebSocketBufferConfig(
            @Value("${smartops.robot.bridge-max-text-bytes:12582912}") int maxTextBytes) {
        this.maxTextBytes = maxTextBytes;
    }

    @Override
    public void setServletContext(ServletContext servletContext) {
        Object container = servletContext.getAttribute(SERVER_CONTAINER_ATTRIBUTE);
        if (container instanceof ServerContainer serverContainer) {
            serverContainer.setDefaultMaxTextMessageBufferSize(maxTextBytes);
            serverContainer.setDefaultMaxBinaryMessageBufferSize(maxTextBytes);
            log.info("机器人桥 WS 帧上限已设为 {} 字节", maxTextBytes);
        } else {
            log.debug("WS ServerContainer 未就绪，跳过桥帧上限设置（非真实 servlet 容器环境）");
        }
    }
}
