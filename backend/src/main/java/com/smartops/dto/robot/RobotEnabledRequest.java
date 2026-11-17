package com.smartops.dto.robot;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/** 设备启用/禁用请求。 */
@Data
public class RobotEnabledRequest {

    @NotNull
    private Boolean enabled;
}
