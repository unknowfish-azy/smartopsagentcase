package com.smartops.radar;

import java.util.List;

/**
 * 采集器扩展点。
 *
 * <p>实现只负责把外部来源解析成 {@link CollectedResource}；去重、评分、入库、
 * 运行日志与来源状态流转统一由 {@link RadarCollectionService} 负责，
 * 这样每种采集方式的行为边界保持一致。</p>
 */
public interface RadarCollector {

    /** 与 {@link RadarSource#collectorType()} 对应，例如 RSS / JSON_API / GITHUB / HTTP_PAGE。 */
    String type();

    List<CollectedResource> collect(RadarSource source);
}
