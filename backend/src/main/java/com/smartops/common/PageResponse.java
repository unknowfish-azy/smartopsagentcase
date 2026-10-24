package com.smartops.common;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class PageResponse<T> {

    /**
     * 当前页数据
     */
    private List<T> records;

    /**
     * 当前页码
     */
    private long current;

    /**
     * 每页大小
     */
    private long size;

    /**
     * 总记录数
     */
    private long total;

    /**
     * 总页数
     */
    private long pages;

    public static <T> PageResponse<T> of(
            List<T> records,
            long current,
            long size,
            long total) {

        long pages = size <= 0
                ? 0
                : (total + size - 1) / size;

        return new PageResponse<>(
                records,
                current,
                size,
                total,
                pages
        );
    }
}