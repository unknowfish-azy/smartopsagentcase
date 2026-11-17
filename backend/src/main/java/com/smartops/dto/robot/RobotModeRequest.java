package com.smartops.dto.robot;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/** 双态切换请求：AUTONOMOUS / HUMAN_CONTROL / IDLE。 */
@Data
public class RobotModeRequest {

    @NotBlank
    private String mode;
}
