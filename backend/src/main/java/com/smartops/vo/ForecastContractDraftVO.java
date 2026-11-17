package com.smartops.vo;

import java.util.List;
import java.util.Map;

import lombok.Builder;
import lombok.Getter;

/**
 * 预测面预防性恢复契约草案（P1-4）。
 *
 * <p>由越界预测上下文组装，digest 恒为空串——不是可执行契约，
 * 签发必须由 Agent 侧完成。预测面无工单实体，草案不落库不留痕，
 * 交付形态是即时 JSON，由用户复核后交给 Agent 运行手册。</p>
 */
@Getter
@Builder
public class ForecastContractDraftVO {

    /** 越界传感器标识（如 ect / rpm），也用作草案目标服务标识 */
    private String sensor;

    /** 越界等级：warn 预警 / crit 越界 */
    private String kind;

    /** 预测越界发生在多少秒后 */
    private Integer horizonSec;

    /** 预测置信度（0~1） */
    private Double confidence;

    /** 一句话摘要 */
    private String summary;

    /** recovery-contract/v1 同形草案，digest 为空串 */
    private Map<String, Object> draft;

    /** 复核提示 */
    private List<String> notes;
}
