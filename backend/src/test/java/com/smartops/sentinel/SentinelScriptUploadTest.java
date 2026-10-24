package com.smartops.sentinel;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * 脚本上传的语言推断。
 *
 * <p>重点：推断不出来就返回 null 让调用方拒绝，**不猜**。
 * 猜错语言会导致预检用错规则、执行时用错解释器。</p>
 */
class SentinelScriptUploadTest {

    @Test
    @DisplayName("常见脚本扩展名映射到受支持的语言")
    void mapsKnownExtensions() {
        assertEquals("shell", SentinelService.languageFromFileName("cleanup.sh"));
        assertEquals("shell", SentinelService.languageFromFileName("cleanup.bash"));
        assertEquals("python", SentinelService.languageFromFileName("check.py"));
        assertEquals("bat", SentinelService.languageFromFileName("restart.bat"));
        assertEquals("bat", SentinelService.languageFromFileName("restart.cmd"));
        assertEquals("powershell", SentinelService.languageFromFileName("probe.ps1"));
        assertEquals("powershell", SentinelService.languageFromFileName("probe.psm1"));
    }

    @Test
    @DisplayName("大小写不敏感：.SH 与 .sh 等价")
    void extensionIsCaseInsensitive() {
        assertEquals("shell", SentinelService.languageFromFileName("CLEANUP.SH"));
        assertEquals("python", SentinelService.languageFromFileName("Check.PY"));
    }

    @Test
    @DisplayName("未知或缺失扩展名返回 null，交给调用方拒绝")
    void unknownExtensionReturnsNull() {
        assertNull(SentinelService.languageFromFileName("notes.txt"));
        assertNull(SentinelService.languageFromFileName("Makefile"));
        assertNull(SentinelService.languageFromFileName("weird."));
        assertNull(SentinelService.languageFromFileName(null));
    }
}
