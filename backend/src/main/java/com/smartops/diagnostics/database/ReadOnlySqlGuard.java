package com.smartops.diagnostics.database;

import com.smartops.exception.BusinessException;

import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * 只读 SQL 守卫（OPS-07）。
 *
 * <p>这是"限制单语句"的落点：只允许以 SELECT / SHOW 开头的单条语句，并拒绝
 * 写文件、加锁读与多语句拼接。守卫只做保守判断，宁可拒绝合法但可疑的语句，
 * 也不让诊断入口变成任意 SQL 执行器。</p>
 */
public final class ReadOnlySqlGuard {

    private static final Set<String> ALLOWED_FIRST_KEYWORDS = Set.of("SELECT", "SHOW");

    private static final Set<String> DENIED_FIRST_KEYWORDS = Set.of(
            "INSERT", "UPDATE", "DELETE", "REPLACE", "ALTER", "DROP", "TRUNCATE",
            "CREATE", "GRANT", "REVOKE", "CALL", "SET", "LOAD", "MERGE", "EXEC", "EXECUTE");

    private static final Pattern BLOCK_COMMENT = Pattern.compile("/\\*.*?\\*/", Pattern.DOTALL);
    private static final Pattern LINE_COMMENT = Pattern.compile("--[^\n\r]*");
    private static final Pattern INTO_OUTFILE = Pattern.compile("\\bINTO\\s+(OUTFILE|DUMPFILE)\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern FOR_UPDATE = Pattern.compile("\\bFOR\\s+UPDATE\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern LOCK_IN_SHARE_MODE = Pattern.compile("\\bLOCK\\s+IN\\s+SHARE\\s+MODE\\b", Pattern.CASE_INSENSITIVE);

    private ReadOnlySqlGuard() {
    }

    /**
     * 校验并原样返回 SQL。
     *
     * @throws BusinessException 400 {@code DB_STATEMENT_NOT_READONLY}
     */
    public static String requireReadOnly(String sql) {
        if (sql == null || sql.isBlank()) {
            throw notReadOnly();
        }
        // 注释必须先剥离：/*x*/ DELETE ... 的首关键字不能被注释伪装掉。
        String stripped = LINE_COMMENT.matcher(BLOCK_COMMENT.matcher(sql).replaceAll(" ")).replaceAll(" ").trim();
        String body = stripped;
        while (body.endsWith(";")) {
            body = body.substring(0, body.length() - 1).trim();
        }
        if (body.indexOf(';') >= 0) {
            // 除结尾外的分号一律视为多语句：驱动允许 allowMultiQueries=false，但这里更早拒绝。
            throw notReadOnly();
        }

        String upper = body.toUpperCase(Locale.ROOT);
        String firstKeyword = firstKeyword(upper);
        if (firstKeyword == null) {
            throw notReadOnly();
        }
        if (DENIED_FIRST_KEYWORDS.contains(firstKeyword) || !ALLOWED_FIRST_KEYWORDS.contains(firstKeyword)) {
            throw notReadOnly();
        }
        if (INTO_OUTFILE.matcher(upper).find()
                || FOR_UPDATE.matcher(upper).find()
                || LOCK_IN_SHARE_MODE.matcher(upper).find()) {
            throw notReadOnly();
        }
        return sql;
    }

    private static String firstKeyword(String upperSql) {
        int index = 0;
        while (index < upperSql.length() && !Character.isLetter(upperSql.charAt(index))) {
            index++;
        }
        int end = index;
        while (end < upperSql.length() && Character.isLetter(upperSql.charAt(end))) {
            end++;
        }
        return end > index ? upperSql.substring(index, end) : null;
    }

    private static BusinessException notReadOnly() {
        return new BusinessException(400, "DB_STATEMENT_NOT_READONLY");
    }
}
