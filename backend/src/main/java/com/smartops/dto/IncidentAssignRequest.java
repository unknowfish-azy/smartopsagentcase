package com.smartops.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/** 指派 / 转派事件负责人请求。 */
@Data
public class IncidentAssignRequest {

    @NotNull(message = "负责人不能为空")
    private Long assigneeId;

    private Long actorId;
}
