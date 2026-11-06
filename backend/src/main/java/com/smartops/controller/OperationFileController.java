package com.smartops.controller;
import com.smartops.security.CurrentUser;
import com.smartops.common.ApiResponse;
import com.smartops.operations.SftpAccess;
import com.smartops.service.OperationFileService;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.InputStream;
import java.util.List;

@RestController
@RequestMapping("/api/operations/runtimes/{runtimeId}/files")
@RequiredArgsConstructor
public class OperationFileController {
    private final OperationFileService service;

    @GetMapping
    public ApiResponse<List<SftpAccess.RemoteFile>> list(@CurrentUser Long userId,
                                                         @PathVariable String runtimeId,
                                                         @RequestParam(defaultValue = ".") String path) {
        return ApiResponse.success(service.list(userId, runtimeId, path));
    }

    @GetMapping("/content")
    public ResponseEntity<InputStreamResource> download(@CurrentUser Long userId,
                                                        @PathVariable String runtimeId,
                                                        @RequestParam String path) {
        InputStream input = service.read(userId, runtimeId, path);
        return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).body(new InputStreamResource(input));
    }

    @PostMapping("/directory")
    public ApiResponse<Void> mkdir(@CurrentUser Long userId,
                                   @PathVariable String runtimeId,
                                   @RequestParam String path) {
        service.mkdir(userId, runtimeId, path);
        return ApiResponse.success();
    }

    @PostMapping(value = "/content", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<Long> upload(@CurrentUser Long userId,
                                    @PathVariable String runtimeId,
                                    @RequestParam String path,
                                    @RequestPart MultipartFile file) {
        try (InputStream input = file.getInputStream(); java.io.OutputStream output = service.write(userId, runtimeId, path)) {
            long bytes = input.transferTo(output);
            return ApiResponse.success(bytes);
        } catch (java.io.IOException ex) {
            throw new com.smartops.exception.BusinessException(502, "SFTP_UPLOAD_FAILED: " + ex.getMessage());
        }
    }

    @DeleteMapping("/content")
    public ApiResponse<Void> delete(@CurrentUser Long userId,
                                    @PathVariable String runtimeId,
                                    @RequestParam String path,
                                    @RequestParam(required = false) String confirmation) {
        service.delete(userId, runtimeId, path, confirmation);
        return ApiResponse.success();
    }
}
