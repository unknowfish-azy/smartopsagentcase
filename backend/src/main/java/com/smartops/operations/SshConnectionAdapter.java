package com.smartops.operations;

import com.smartops.entity.OperationSession;
import org.apache.sshd.client.SshClient;
import org.apache.sshd.client.channel.ChannelShell;
import org.apache.sshd.client.channel.ChannelExec;
import org.apache.sshd.client.channel.ClientChannelEvent;
import org.apache.sshd.client.session.ClientSession;
import org.apache.sshd.client.config.hosts.HostConfigEntry;
import org.apache.sshd.common.config.keys.KeyUtils;
import org.apache.sshd.common.util.io.resource.PathResource;
import org.apache.sshd.common.util.security.SecurityUtils;
import org.apache.sshd.sftp.client.SftpClient;
import org.apache.sshd.sftp.client.SftpClientFactory;
import org.apache.sshd.common.util.net.SshdSocketAddress;
import org.apache.sshd.client.session.forward.ExplicitPortForwardingTracker;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.OutputStream;
import java.io.ByteArrayOutputStream;
import java.io.ByteArrayInputStream;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.PublicKey;
import java.util.Base64;
import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

@Component
public class SshConnectionAdapter implements ConnectionAdapter {
    private static final long CONNECT_TIMEOUT_MS = 10_000;
    private final OperationRuntimeRegistry registry;
    private final HostKeyTrustPolicy hostKeyTrustPolicy;
    private final long commandOutputLimitBytes;

    public SshConnectionAdapter(OperationRuntimeRegistry registry, KnownHostStore knownHostStore,
                                @Value("${smartops.operations.ssh.output-limit-bytes:1048576}") long commandOutputLimitBytes) {
        this.registry = registry;
        this.hostKeyTrustPolicy = new HostKeyTrustPolicy(knownHostStore);
        this.commandOutputLimitBytes = commandOutputLimitBytes;
    }

    @Override
    public ConnectionResult connect(Long userId, OperationSession session, String secret, HostKeyDecision decision) {
        return connect(userId, session, secret, decision, null);
    }

    public ConnectionResult connect(Long userId, OperationSession session, String secret, HostKeyDecision decision, OperationSession jumpSession) {
        if (!"SSH".equalsIgnoreCase(session.getProtocol()) && !"SFTP".equalsIgnoreCase(session.getProtocol())) {
            return ConnectionResult.failed("CAPABILITY", "REQUIRES_NATIVE_BRIDGE");
        }
        SshClient client = SshClient.setUpDefaultClient();
        CapturedKey captured = new CapturedKey();
        client.setServerKeyVerifier((clientSession, address, key) -> {
            captured.key = key;
            captured.fingerprint = KeyUtils.getFingerPrint(key);
            captured.algorithm = key.getAlgorithm();
            captured.publicKey = Base64.getEncoder().encodeToString(key.getEncoded());
            return hostKeyTrustPolicy.allows(session, captured.toPresentedHostKey(session), decision);
        });
        try {
            client.start();
            ClientSession ssh;
            if (jumpSession == null) {
                ssh = client.connect(session.getUsername(), session.getHost(), session.getPort()).verify(CONNECT_TIMEOUT_MS).getSession();
            } else {
                HostConfigEntry entry = new HostConfigEntry(session.getHost(), session.getHost(), session.getPort(), session.getUsername());
                entry.setProxyJump(jumpSession.getUsername() + "@" + jumpSession.getHost() + ":" + jumpSession.getPort());
                ssh = client.connect(entry, null, null).verify(CONNECT_TIMEOUT_MS).getSession();
            }
            if (secret != null && !secret.isBlank()) ssh.addPasswordIdentity(secret);
            if (session.getIdentityPath() != null && !session.getIdentityPath().isBlank()) {
                Path identity = Path.of(session.getIdentityPath()).toAbsolutePath().normalize();
                if (!Files.isRegularFile(identity) || !Files.isReadable(identity)) {
                    throw new IOException("IDENTITY_FILE_UNREADABLE");
                }
                Iterable<KeyPair> pairs = SecurityUtils.loadKeyPairIdentities(null, new PathResource(identity), Files.newInputStream(identity), null);
                for (KeyPair pair : pairs) ssh.addPublicKeyIdentity(pair);
            }
            ssh.auth().verify(CONNECT_TIMEOUT_MS);
            if (decision == HostKeyDecision.TRUST_AND_SAVE) hostKeyTrustPolicy.save(session, captured.toPresentedHostKey(session));
            String runtimeId = registry.register(new SshRuntime(userId, session.getId(), client, ssh, commandOutputLimitBytes));
            return ConnectionResult.online(runtimeId, captured.fingerprint, captured.algorithm);
        } catch (Exception ex) {
            closeQuietly(client);
            if (captured.key != null && decision == HostKeyDecision.NONE) {
                return ConnectionResult.hostKeyRequired(captured.fingerprint, captured.algorithm);
            }
            return ConnectionResult.failed(stageFor(ex), safeMessage(ex));
        }
    }

    private static String stageFor(Exception ex) {
        String name = ex.getClass().getSimpleName().toLowerCase();
        if (name.contains("auth")) return "AUTH";
        if (name.contains("connect") || name.contains("timeout")) return "TCP";
        return "CHANNEL";
    }

    private static String safeMessage(Exception ex) {
        String message = ex.getMessage();
        return message == null || message.isBlank() ? "Connection failed" : OperationRedactor.redact(message);
    }

    private static void closeQuietly(SshClient client) {
        try { client.stop(); } catch (Exception ignored) { }
    }

    private static final class CapturedKey {
        private PublicKey key;
        private String fingerprint;
        private String algorithm;
        private String publicKey;

        private PresentedHostKey toPresentedHostKey(OperationSession session) {
            return new PresentedHostKey(session.getHost(), session.getPort(), algorithm, fingerprint, publicKey);
        }
    }

    private static final class SshRuntime implements OperationRuntime, SftpAccess, TunnelAccess {
        private final String id = UUID.randomUUID().toString();
        private final Long userId;
        private final Long sessionId;
        private final SshClient client;
        private final ClientSession session;
        private final long outputLimitBytes;
        private final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
            Thread thread = new Thread(r, "smartops-ssh-output");
            thread.setDaemon(true);
            return thread;
        });
        private volatile ChannelShell shell;
        private PipedOutputStream input;
        private volatile OutputListener listener;
        private volatile boolean open = true;
        private final java.util.Map<String, ExplicitPortForwardingTracker> tunnels = new java.util.concurrent.ConcurrentHashMap<>();

        private SshRuntime(Long userId, Long sessionId, SshClient client, ClientSession session, long outputLimitBytes) {
            this.userId = userId; this.sessionId = sessionId; this.client = client; this.session = session;
            this.outputLimitBytes = outputLimitBytes;
        }

        @Override public String id() { return id; }
        @Override public Long userId() { return userId; }
        @Override public Long sessionId() { return sessionId; }

        @Override
        public synchronized void onOutput(OutputListener listener) {
            this.listener = listener;
            if (shell == null) {
                try {
                    shell = session.createShellChannel();
                    PipedInputStream remoteInput = new PipedInputStream();
                    input = new PipedOutputStream(remoteInput);
                    shell.setIn(remoteInput);
                    shell.setOut(new OutputStream() {
                        @Override public void write(int b) { emit(new String(new byte[]{(byte) b}, StandardCharsets.UTF_8)); }
                        @Override public void write(byte[] b, int off, int len) { emit(new String(b, off, len, StandardCharsets.UTF_8)); }
                    });
                    shell.setErr(shell.getOut());
                    shell.open();
                } catch (IOException ex) {
                    emit("\r\n[CHANNEL ERROR] " + OperationRedactor.redact(ex.getMessage()) + "\r\n");
                }
            }
        }

        private void emit(String output) { if (listener != null) listener.onOutput(OperationRedactor.redact(output)); }

        @Override public void write(String input) throws IOException {
            if (!open) throw new IOException("RUNTIME_CLOSED");
            if (shell == null) onOutput(listener);
            this.input.write(input.getBytes(StandardCharsets.UTF_8));
            this.input.flush();
        }

        @Override public void resize(int columns, int rows) throws IOException {
            if (shell != null) shell.sendWindowChange(columns, rows, 0, 0);
        }

        @Override public boolean isOpen() { return open && session.isOpen(); }

        @Override
        public CommandResult execute(String command, long timeoutMillis) throws IOException {
            if (!isOpen()) throw new IOException("RUNTIME_CLOSED");
            BoundedOutput stdout = new BoundedOutput(outputLimitBytes);
            BoundedOutput stderr = new BoundedOutput(outputLimitBytes);
            try (ChannelExec channel = session.createExecChannel(command)) {
                channel.setOut(stdout.stream());
                channel.setErr(stderr.stream());
                channel.open().verify(timeoutMillis);
                Set<ClientChannelEvent> events = channel.waitFor(
                        EnumSet.of(ClientChannelEvent.CLOSED, ClientChannelEvent.EXIT_STATUS), timeoutMillis);
                if (!events.contains(ClientChannelEvent.CLOSED) && !events.contains(ClientChannelEvent.EXIT_STATUS)) {
                    channel.close(true);
                    throw new IOException("COMMAND_TIMEOUT");
                }
                Integer exitStatus = channel.getExitStatus();
                return new CommandResult(
                        exitStatus == null ? -1 : exitStatus,
                        OperationRedactor.redact(stdout.text()),
                        OperationRedactor.redact(stderr.text()),
                        stdout.truncated() || stderr.truncated()
                );
            }
        }

        @Override public java.util.List<RemoteFile> list(String path) throws IOException {
            try (SftpClient sftp = SftpClientFactory.instance().createSftpClient(session)) {
                java.util.List<RemoteFile> result = new java.util.ArrayList<>();
                for (SftpClient.DirEntry entry : sftp.readDir(path)) {
                    if (".".equals(entry.getFilename()) || "..".equals(entry.getFilename())) continue;
                    String child = path.endsWith("/") ? path + entry.getFilename() : path + "/" + entry.getFilename();
                    result.add(new RemoteFile(entry.getFilename(), child, entry.getAttributes().getSize(), entry.getAttributes().isDirectory(),
                            entry.getAttributes().getModifyTime() == null ? null : entry.getAttributes().getModifyTime().toString()));
                }
                return result;
            }
        }

        @Override public java.io.InputStream read(String path) throws IOException {
            try (SftpClient sftp = SftpClientFactory.instance().createSftpClient(session);
                 java.io.InputStream input = sftp.read(path);
                 ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                input.transferTo(output);
                return new ByteArrayInputStream(output.toByteArray());
            }
        }

        @Override public OutputStream openWrite(String path) throws IOException {
            SftpClient sftp = SftpClientFactory.instance().createSftpClient(session);
            OutputStream output = sftp.write(path, SftpClient.OpenMode.Create, SftpClient.OpenMode.Write, SftpClient.OpenMode.Truncate);
            return new OutputStream() {
                @Override public void write(int b) throws IOException { output.write(b); }
                @Override public void write(byte[] b, int off, int len) throws IOException { output.write(b, off, len); }
                @Override public void flush() throws IOException { output.flush(); }
                @Override public void close() throws IOException { try { output.close(); } finally { sftp.close(); } }
            };
        }

        @Override public void mkdir(String path) throws IOException { try (SftpClient sftp = SftpClientFactory.instance().createSftpClient(session)) { sftp.mkdir(path); } }
        @Override public void rename(String source, String target) throws IOException { try (SftpClient sftp = SftpClientFactory.instance().createSftpClient(session)) { sftp.rename(source, target); } }
        @Override public void delete(String path) throws IOException { try (SftpClient sftp = SftpClientFactory.instance().createSftpClient(session)) { sftp.remove(path); } }

        @Override public String startLocalForward(String name, String listenAddress, int listenPort, String targetHost, int targetPort) throws IOException {
            String tunnelId = java.util.UUID.randomUUID().toString();
            ExplicitPortForwardingTracker tracker = session.createLocalPortForwardingTracker(
                    new SshdSocketAddress(listenAddress, listenPort), new SshdSocketAddress(targetHost, targetPort));
            tunnels.put(tunnelId, tracker);
            return tunnelId;
        }

        @Override public void stopLocalForward(String tunnelId) throws IOException {
            ExplicitPortForwardingTracker tracker = tunnels.remove(tunnelId);
            if (tracker == null) throw new IOException("TUNNEL_NOT_FOUND");
            tracker.close();
        }

        @Override public synchronized void close() {
            if (!open) return;
            open = false;
            try { if (shell != null) shell.close(false); } catch (Exception ignored) { }
            try { session.close(false); } catch (Exception ignored) { }
            try { client.stop(); } catch (Exception ignored) { }
            tunnels.values().forEach(tracker -> { try { tracker.close(); } catch (Exception ignored) { } });
            tunnels.clear();
            executor.shutdownNow();
            if (listener != null) listener.onClosed(null);
        }
    }
}
