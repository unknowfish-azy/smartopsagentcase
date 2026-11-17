package com.smartops.vo;

import lombok.Builder;
import lombok.Data;

import java.util.List;
import java.util.Map;

/**
 * 恢复契约草案视图对象。
 *
 * <p>草案 ≠ 契约：platform 不计算 canonical digest（信任边界在 Agent 侧），
 * 草案必须经 Agent 运行手册校验谓词绑定、计算 digest 并经内部端点登记后才成为可执行契约。</p>
 */
@Data
@Builder
public class IncidentContractDraftVO {

    private Long incidentId;

    private String incidentTitle;

    /** 一句话摘要（草案针对什么目标、什么义务）。 */
    private String summary;

    /** 与 Agent 契约 schema 同形（recovery-contract/v1）的草案体，digest 字段恒为空串。 */
    private Map<String, Object> draft;

    /** 人工复核提示：predicate 绑定、source_groups、签发流程等。 */
    private List<String> notes;
}
