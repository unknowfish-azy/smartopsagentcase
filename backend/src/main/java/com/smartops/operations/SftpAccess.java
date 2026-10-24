package com.smartops.operations;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.List;

public interface SftpAccess {
    List<RemoteFile> list(String path) throws IOException;
    InputStream read(String path) throws IOException;
    OutputStream openWrite(String path) throws IOException;
    void mkdir(String path) throws IOException;
    void rename(String source, String target) throws IOException;
    void delete(String path) throws IOException;

    record RemoteFile(String name, String path, long size, boolean directory, String modifiedAt) {}
}
