package com.smartops.diagnostics;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import org.springframework.stereotype.Component;

@Component
public final class DiagnosticTransport implements AutoCloseable {
    public static final int MAX_BODY_BYTES = 256 * 1024;
    public static final int CONNECT_TIMEOUT_MS = 3_000;
    public static final int READ_TIMEOUT_MS = 10_000;

    public HttpResult http(DiagnosticTargetPolicy.ApprovedTarget target, String method) throws IOException {
        URI uri = target.uri();
        InetAddress address = target.addresses().get(0);
        try (Socket raw = new Socket()) {
            raw.connect(new java.net.InetSocketAddress(address, uri.getPort()), CONNECT_TIMEOUT_MS);
            raw.setSoTimeout(READ_TIMEOUT_MS);
            Socket socket = raw;
            if ("https".equalsIgnoreCase(uri.getScheme())) socket = tls(raw, uri.getHost(), uri.getPort());
            try {
                OutputStream output = socket.getOutputStream();
                String host = uri.getHost() + (("https".equals(uri.getScheme()) && uri.getPort() == 443) || ("http".equals(uri.getScheme()) && uri.getPort() == 80) ? "" : ":" + uri.getPort());
                output.write((method + " " + uri.getRawPath() + " HTTP/1.1\r\nHost: " + host
                        + "\r\nAccept: application/json,text/plain;q=0.8\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
                output.flush();
                return readResponse(socket, method);
            } finally { if (socket != raw) socket.close(); }
        }
    }

    public CertificateResult certificate(DiagnosticTargetPolicy.ApprovedTarget target) throws IOException {
        if (!"https".equalsIgnoreCase(target.uri().getScheme())) throw new IOException("TLS 仅支持 HTTPS");
        InetAddress address = target.addresses().get(0);
        try (Socket raw = new Socket()) {
            raw.connect(new java.net.InetSocketAddress(address, target.uri().getPort()), CONNECT_TIMEOUT_MS);
            raw.setSoTimeout(READ_TIMEOUT_MS);
            try (SSLSocket socket = tls(raw, target.uri().getHost(), target.uri().getPort())) {
                socket.startHandshake();
                var session = socket.getSession();
                Certificate[] chain = session.getPeerCertificates();
                if (chain.length == 0 || !(chain[0] instanceof X509Certificate leaf)) throw new IOException("未取得服务器证书");
                List<String> names = new ArrayList<>();
                try {
                    for (List<?> item : leaf.getSubjectAlternativeNames() == null ? List.<List<?>>of() : leaf.getSubjectAlternativeNames()) {
                        if (item.size() > 1 && item.get(1) instanceof String name && (item.get(0).equals(2) || item.get(0).equals(7))) names.add(name);
                    }
                } catch (java.security.cert.CertificateParsingException ignored) { }
                return new CertificateResult(leaf.getIssuerX500Principal().getName(), List.copyOf(names),
                        leaf.getNotBefore().toInstant(), leaf.getNotAfter().toInstant());
            }
        }
    }

    private static SSLSocket tls(Socket raw, String hostname, int port) throws IOException {
        SSLSocket socket = (SSLSocket) ((SSLSocketFactory) SSLSocketFactory.getDefault()).createSocket(raw, hostname, port, true);
        SSLParameters parameters = socket.getSSLParameters();
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        parameters.setServerNames(List.of(new javax.net.ssl.SNIHostName(hostname)));
        socket.setSSLParameters(parameters);
        return socket;
    }

    private static HttpResult readResponse(Socket socket, String method) throws IOException {
        BufferedInputStream input = new BufferedInputStream(socket.getInputStream());
        ByteArrayOutputStream headerBytes = new ByteArrayOutputStream();
        int current;
        while ((current = input.read()) != -1) {
            headerBytes.write(current);
            if (headerBytes.size() > 32 * 1024) throw new IOException("响应头超过限制");
            byte[] header = headerBytes.toByteArray();
            int size = header.length;
            if ((size >= 4 && header[size - 4] == '\r' && header[size - 3] == '\n' && header[size - 2] == '\r' && header[size - 1] == '\n')
                    || (size >= 2 && header[size - 2] == '\n' && header[size - 1] == '\n')) break;
        }
        String headers = headerBytes.toString(StandardCharsets.ISO_8859_1);
        String[] lines = headers.split("\\r?\\n");
        if (lines.length == 0 || !lines[0].startsWith("HTTP/")) throw new IOException("无效 HTTP 响应");
        int status = Integer.parseInt(lines[0].split(" ", 3)[1]);
        long contentLength = -1;
        for (String line : lines) if (line.regionMatches(true, 0, "Content-Length:", 0, 15)) {
            try { contentLength = Long.parseLong(line.substring(15).trim()); } catch (NumberFormatException ignored) { }
        }
        if ("HEAD".equals(method) || status == 204 || status == 304) return new HttpResult(status, new byte[0], false);
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        while (body.size() <= MAX_BODY_BYTES) {
            int read = input.read(buffer);
            if (read < 0) break;
            body.write(buffer, 0, Math.min(read, MAX_BODY_BYTES + 1 - body.size()));
            if (contentLength >= 0 && body.size() >= contentLength) break;
        }
        boolean truncated = body.size() > MAX_BODY_BYTES || contentLength > MAX_BODY_BYTES;
        byte[] bytes = body.toByteArray();
        return new HttpResult(status, truncated ? java.util.Arrays.copyOf(bytes, Math.min(bytes.length, MAX_BODY_BYTES)) : bytes, truncated);
    }

    @Override public void close() {}
    public record HttpResult(int statusCode, byte[] body, boolean truncated) {}
    public record CertificateResult(String issuer, List<String> names, Instant notBefore, Instant notAfter) {}
}
