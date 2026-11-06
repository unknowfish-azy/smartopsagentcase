package com.smartops.backup;

import com.smartops.backup.BackupService.ArtifactView;
import com.smartops.backup.BackupService.DrillRequest;
import com.smartops.backup.BackupService.DrillView;
import com.smartops.backup.BackupService.SetView;
import com.smartops.backup.BackupService.StatusView;
import com.smartops.common.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;

/**
 * OPS-13：备份恢复集合、清单校验与隔离恢复演练接口。
 */
@RestController
@RequestMapping("/api/backups")
public class BackupController {

    private final BackupService backups;

    public BackupController(BackupService backups) {
        this.backups = backups;
    }

    @GetMapping("/sets")
    public ApiResponse<List<SetView>> sets(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId) {
        return ApiResponse.success(backups.listSets(userId));
    }

    @PostMapping("/sets")
    public ApiResponse<SetView> createSet(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @Valid @RequestBody CreateSetRequest request) {
        return ApiResponse.success(backups.createSet(userId, request.name(), request.environment(),
                request.components(), request.retentionDays(), request.offsiteRequired()));
    }

    @GetMapping("/sets/{setId}/status")
    public ApiResponse<StatusView> status(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable long setId) {
        return ApiResponse.success(backups.status(userId, setId));
    }

    /** 导入备份脚本生成的清单（sha256 / 字节数 / 条目数）。 */
    @PostMapping("/sets/{setId}/manifests")
    public ApiResponse<List<ArtifactView>> manifest(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable long setId,
            @Valid @RequestBody ManifestRequest request) {
        return ApiResponse.success(backups.ingestManifest(userId, setId, request.manifestJson()));
    }

    @PostMapping("/sets/{setId}/artifacts/verify")
    public ApiResponse<ArtifactView> verify(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable long setId,
            @Valid @RequestBody VerifyRequest request) {
        return ApiResponse.success(backups.verifyArtifact(userId, setId,
                request.artifactId(), request.actualSha256(), request.actualItemCount()));
    }

    @PostMapping("/sets/{setId}/artifacts/offsite")
    public ApiResponse<ArtifactView> offsite(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable long setId,
            @Valid @RequestBody OffsiteRequest request) {
        return ApiResponse.success(backups.recordOffsite(userId, setId,
                request.artifactId(), request.location(), request.verified()));
    }

    @PostMapping("/sets/{setId}/drills")
    public ApiResponse<DrillView> drill(
            @RequestHeader(value = "X-User-Id", defaultValue = "1") Long userId,
            @PathVariable long setId,
            @Valid @RequestBody DrillRunRequest request) {
        return ApiResponse.success(backups.recordDrill(userId, setId, new DrillRequest(
                request.mode(), request.startedAt(), request.finishedAt(), request.expectedCount(),
                request.restoredCount(), request.hashVerified(), request.referenceCheck(),
                request.keyQueryCheck())));
    }

    public record CreateSetRequest(@NotBlank String name, @NotBlank String environment,
                                   List<String> components, Integer retentionDays, Boolean offsiteRequired) {}

    public record ManifestRequest(@NotBlank String manifestJson) {}

    public record VerifyRequest(@NotBlank String artifactId, @NotBlank String actualSha256, Long actualItemCount) {}

    public record OffsiteRequest(@NotBlank String artifactId, @NotBlank String location, boolean verified) {}

    public record DrillRunRequest(String mode, Instant startedAt, Instant finishedAt, long expectedCount,
                                  long restoredCount, boolean hashVerified, String referenceCheck,
                                  String keyQueryCheck) {}
}
