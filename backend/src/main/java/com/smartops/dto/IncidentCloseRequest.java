package com.smartops.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/** 关闭事件请求（RESOLVED -> CLOSED），必须填写根因与复盘。 */
@Data
public class IncidentCloseRequest {

    @NotBlank(message = "关闭事件必须填写根因")
    private String rootCause;

    @NotBlank(message = "关闭事件必须填写处置过程")
    private String resolution;

    @NotBlank(message = "关闭事件必须填写复盘结论")
    private String postmortem;
}
