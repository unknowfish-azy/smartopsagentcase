package com.smartops.admin;

import com.smartops.exception.BusinessException;
import org.springframework.jdbc.support.KeyHolder;

import java.util.Map;

/**
 * 生成主键读取。
 *
 * <p>某些驱动在 RETURN_GENERATED_KEYS 时会返回多列（id 之外还有 created_at 等），
 * 此时 {@link KeyHolder#getKey()} 会抛异常。这里从 getKeyList 里读 "id"。</p>
 */
public final class SysKeys {

    private SysKeys() {}

    public static long id(KeyHolder keys) {
        if (keys.getKeyList().isEmpty()) throw new BusinessException(500, "创建记录后未返回主键");
        Map<String, Object> row = keys.getKeyList().get(0);
        Object value = row.get("id");
        if (value == null && !row.isEmpty()) value = row.values().iterator().next();
        if (value instanceof Number number) return number.longValue();
        throw new BusinessException(500, "创建记录后未返回主键");
    }
}
