package com.smartops.dto.inspector;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 视觉巡检请求体：imageBase64 必填（纯 base64 或 data URI），
 * target / filename 可选，用于纠察事件的目标与证据溯源标注。
 */
public record VisionAnalysisRequest(

        @NotBlank(message = "图片数据不能为空")
        String imageBase64,

        @Size(max = 120, message = "巡检目标不能超过 120 字符")
        String target,

        @Size(max = 200, message = "文件名不能超过 200 字符")
        String filename
) {}
