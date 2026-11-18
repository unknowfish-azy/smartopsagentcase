package com.smartops.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.JdbcTemplate;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

/**
 * 关键帧归档：落盘路径、幂等、体积上限、降级不抛。
 *
 * <p>这些断言保护的是「视觉数据资产不会悄悄丢样本、也不会冒充成功」——
 * 归档失败必须给出真实 reason，不能记成 stored=true。</p>
 */
class RobotFrameArchiveServiceTest {

    private static final String DEVICE = "robot-car-01";
    /** 12 字节真实内容（不是合法 PNG，但归档只关心字节与哈希）。 */
    private static final byte[] CONTENT = "fake-jpeg-payload".getBytes(StandardCharsets.UTF_8);

    @TempDir
    Path tempDir;

    private JdbcTemplate jdbc;

    @BeforeEach
    void setUp() {
        jdbc = mock(JdbcTemplate.class);
    }

    private RobotFrameArchiveService service(boolean enabled, long maxBytes) {
        return new RobotFrameArchiveService(jdbc, enabled, tempDir.toString(), maxBytes);
    }

    @Test
    void storesFileAndRegistersRowWithStableHashPath() throws Exception {
        RobotFrameArchiveService archive = service(true, 1024 * 1024);
        String base64 = Base64.getEncoder().encodeToString(CONTENT);

        RobotFrameArchiveService.ArchiveResult result =
                archive.archiveNow(DEVICE, "配电柜 A", base64, Map.of("quality", "low", "mime", "image/png"));

        assertThat(result.stored()).isTrue();
        assertThat(result.reason()).isEqualTo("STORED");
        // 路径按 sha256 命名，且带设备目录；扩展名跟随 mime
        assertThat(result.filePath()).endsWith(result.sha256() + ".png");
        assertThat(result.filePath()).contains(DEVICE);
        assertThat(Files.readAllBytes(tempDir.resolve(result.filePath()))).isEqualTo(CONTENT);
        // 登记 1 行，字段口径与 robot_frame 一致
        verify(jdbc).update(anyString(), eq(DEVICE), eq("配电柜 A"), eq(result.filePath()),
                eq(result.sha256()), eq(CONTENT.length), any(), any(), eq("low"), any(), any());
    }

    @Test
    void sha256MatchesContentSoReuploadIsIdempotent() {
        RobotFrameArchiveService archive = service(true, 1024 * 1024);
        String base64 = Base64.getEncoder().encodeToString(CONTENT);

        RobotFrameArchiveService.ArchiveResult first = archive.archiveNow(DEVICE, null, base64, Map.of());
        RobotFrameArchiveService.ArchiveResult second = archive.archiveNow(DEVICE, null, base64, Map.of());

        assertThat(first.sha256()).isEqualTo(second.sha256());
        assertThat(first.filePath()).isEqualTo(second.filePath());
        assertThat(first.sha256()).isEqualTo(sha256Of(CONTENT));
        // 同一张图重复回传：两次都登记（唯一键兜底），但只写一次文件
        verify(jdbc, times(2)).update(anyString(), any(), any(), anyString(), anyString(), anyInt(),
                any(), any(), any(), any(), any());
    }

    @Test
    void dataUriPrefixIsStrippedBeforeDecode() {
        RobotFrameArchiveService archive = service(true, 1024 * 1024);
        String dataUri = "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(CONTENT);

        RobotFrameArchiveService.ArchiveResult result = archive.archiveNow(DEVICE, null, dataUri, Map.of());

        assertThat(result.stored()).isTrue();
        assertThat(result.sha256()).isEqualTo(sha256Of(CONTENT));
    }

    @Test
    void oversizeFrameIsSkippedWithoutTruncation() throws Exception {
        RobotFrameArchiveService archive = service(true, 4);
        String base64 = Base64.getEncoder().encodeToString(CONTENT);

        RobotFrameArchiveService.ArchiveResult result = archive.archiveNow(DEVICE, null, base64, Map.of());

        assertThat(result.stored()).isFalse();
        assertThat(result.reason()).startsWith("TOO_LARGE:");
        verify(jdbc, never()).update(anyString(), any(), any(), anyString(), anyString(), anyInt(),
                any(), any(), any(), any(), any());
        try (var files = Files.walk(tempDir)) {
            assertThat(files.filter(Files::isRegularFile).count()).isZero();
        }
    }

    @Test
    void invalidBase64IsReportedAsEmptyInsteadOfThrowing() {
        RobotFrameArchiveService archive = service(true, 1024 * 1024);

        RobotFrameArchiveService.ArchiveResult result =
                archive.archiveNow(DEVICE, null, "!!!not-base64!!!", Map.of());

        assertThat(result.stored()).isFalse();
        assertThat(result.reason()).isEqualTo("EMPTY_IMAGE");
    }

    @Test
    void disabledArchiveDoesNothingAtAll() throws Exception {
        RobotFrameArchiveService archive = service(false, 1024 * 1024);
        String base64 = Base64.getEncoder().encodeToString(CONTENT);

        RobotFrameArchiveService.ArchiveResult result = archive.archiveNow(DEVICE, null, base64, Map.of());

        assertThat(result.stored()).isFalse();
        assertThat(result.reason()).isEqualTo("ARCHIVE_DISABLED");
        verify(jdbc, never()).update(anyString(), any(), any(), anyString(), anyString(), anyInt(),
                any(), any(), any(), any(), any());
        try (var files = Files.walk(tempDir)) {
            assertThat(files.filter(Files::isRegularFile).count()).isZero();
        }
    }

    @Test
    void dbFailureKeepsFileButReportsNotStored() {
        doThrow(new org.springframework.dao.DataAccessResourceFailureException("db down"))
                .when(jdbc).update(anyString(), any(), any(), anyString(), anyString(), anyInt(),
                        any(), any(), any(), any(), any());
        RobotFrameArchiveService archive = service(true, 1024 * 1024);
        String base64 = Base64.getEncoder().encodeToString(CONTENT);

        RobotFrameArchiveService.ArchiveResult result = archive.archiveNow(DEVICE, null, base64, Map.of());

        assertThat(result.stored()).isFalse();
        assertThat(result.reason()).startsWith("DB_FAILED:");
        // 文件保留：下次同图回传会走「已存在」分支并重试登记
        assertThat(Files.exists(tempDir.resolve(result.filePath()))).isTrue();
    }

    @Test
    void blankImageIsIgnoredByAsyncEntryPoint() {
        RobotFrameArchiveService archive = service(true, 1024 * 1024);
        archive.archive(DEVICE, null, "   ", Map.of());
        verify(jdbc, never()).update(anyString(), any(), any(), anyString(), anyString(), anyInt(),
                any(), any(), any(), any(), any());
    }

    private static String sha256Of(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
