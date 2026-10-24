package com.smartops.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class ServerCreateRequest {

    @NotBlank(message = "服务器名称不能为空")
    private String name;

    @NotBlank(message = "服务器地址不能为空")
    private String host;

    @Min(value = 1, message = "端口必须大于0")
    @Max(value = 65535, message = "端口不能超过65535")
    private Integer port = 22;

    private String os;

    private String description;
}