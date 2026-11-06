package com.smartops.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/** 事件评论请求。 */
@Data
public class IncidentCommentRequest {

    @NotBlank(message = "评论内容不能为空")
    private String content;

    private Long actorId;
}
