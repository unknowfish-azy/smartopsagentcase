package com.smartops.cloud;

import java.util.List;

/**
 * 一页只读清单结果。
 *
 * nextCursor 为空且 hasMore=false 才表示"全量已取完"；
 * 只有全量取完才允许把未出现的资源标记为 MISSING，避免把分页中断误判成资源消失。
 */
public record CloudPage(List<CloudResourceSnapshot> items, String nextCursor, boolean hasMore) {

    public CloudPage {
        items = items == null ? List.of() : List.copyOf(items);
    }
}
