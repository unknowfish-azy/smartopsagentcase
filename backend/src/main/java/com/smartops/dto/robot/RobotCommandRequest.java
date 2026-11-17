package com.smartops.dto.robot;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 机器人命令下发请求（REST 通道，与 WebSocket 通道共用同一套白名单校验）。
 *
 * <p>{@code source} 仅内部大脑调用时传 {@code BRAIN}，前端一律不传（默认 CONSOLE）。</p>
 */
@Data
public class RobotCommandRequest {

    @NotBlank
    private String op;

    private Map<String, Object> params = new LinkedHashMap<>();

    /** CONSOLE（人工态）/ BRAIN（自主态大脑）；缺省视为 CONSOLE。 */
    private String source;
}
