package com.smartops.service;

import com.smartops.exception.BusinessException;
import com.smartops.operations.OperationRuntime;
import com.smartops.operations.OperationRuntimeRegistry;
import com.smartops.operations.SftpAccess;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.List;

@Service
@RequiredArgsConstructor
public class OperationFileService {
    private final OperationRuntimeRegistry registry;

    private SftpAccess access(Long userId, String runtimeId) {
        OperationRuntime runtime = registry.requireOwned(runtimeId, userId);
        if (!(runtime instanceof SftpAccess sftp)) throw new BusinessException(409, "SFTP_NOT_AVAILABLE");
        return sftp;
    }

    public List<SftpAccess.RemoteFile> list(Long userId, String runtimeId, String path) {
        try { return access(userId, runtimeId).list(path == null || path.isBlank() ? "." : path); }
        catch (IOException ex) { throw new BusinessException(502, "SFTP_LIST_FAILED: " + ex.getMessage()); }
    }

    public InputStream read(Long userId, String runtimeId, String path) {
        try { return access(userId, runtimeId).read(path); }
        catch (IOException ex) { throw new BusinessException(502, "SFTP_READ_FAILED: " + ex.getMessage()); }
    }

    public OutputStream write(Long userId, String runtimeId, String path) {
        try { return access(userId, runtimeId).openWrite(path); }
        catch (IOException ex) { throw new BusinessException(502, "SFTP_WRITE_FAILED: " + ex.getMessage()); }
    }

    public void mkdir(Long userId, String runtimeId, String path) {
        try { access(userId, runtimeId).mkdir(path); }
        catch (IOException ex) { throw new BusinessException(502, "SFTP_MKDIR_FAILED: " + ex.getMessage()); }
    }

    public void delete(Long userId, String runtimeId, String path, String confirmation) {
        if (!"DELETE".equals(confirmation)) throw new BusinessException(409, "CONFIRMATION_REQUIRED");
        try { access(userId, runtimeId).delete(path); }
        catch (IOException ex) { throw new BusinessException(502, "SFTP_DELETE_FAILED: " + ex.getMessage()); }
    }
}
