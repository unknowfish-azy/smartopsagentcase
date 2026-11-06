package com.smartops.security;

import org.apache.hc.client5.http.DnsResolver;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.client5.http.impl.routing.SystemDefaultRoutePlanner;
import org.apache.hc.core5.util.Timeout;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SEC-06 残余：真实 DNS rebinding 注入实验（无管理员权限、不改系统 DNS）。
 *
 * <p>做法：在 {@code 127.0.0.1} 起一个真实的 UDP DNS 服务，对同一主机名先答公网 A
 * 记录（模拟"校验通过"），随后切答 {@code 127.0.0.1}（模拟攻击者在校验与连接之间
 * rebinding）。本地蜜罐 TCP 端口记录是否真的被连上。</p>
 *
 * <p>两组对照：</p>
 * <ol>
 *   <li>未 pin 的客户端（解析器直接向受控 DNS 发真实查询）→ 连到蜜罐，证明 rebinding
 *       应答确实生效、攻击真实可达；</li>
 *   <li>生产 cable 方式（{@link PinnedDns} 作为 DnsResolver）→ 只用 pin 的公网地址
 *       建连，蜜罐零连接；清除 pin 后直接 fail-closed（{@link UnknownHostException}）。</li>
 * </ol>
 *
 * <p>边界（如实）：受控 DNS 与蜜罐都在本机，未使用公网出口；DNS 应答切换走真实
 * UDP 协议，pin 之后的连接走真实 TCP。审计要求的"公网真实 rebinding"仍属部署环境项。</p>
 */
class PinnedDnsRebindingTest {

    private static final String HOST = "rebind.sec.test";
    private static final String PUBLIC_IP = "93.184.216.34";   // example.com，策略判定为公网
    private static final String PRIVATE_IP = "127.0.0.1";

    private ControlledDns dns;
    private Honeypot honeypot;

    @BeforeEach
    void setUp() throws Exception {
        PinnedDns.clear(HOST);
        dns = new ControlledDns(PUBLIC_IP);
        honeypot = new Honeypot();
    }

    @AfterEach
    void tearDown() throws Exception {
        PinnedDns.clear(HOST);
        if (dns != null) dns.close();
        if (honeypot != null) honeypot.close();
    }

    @Test
    void rebindingAnswerIsLiveButPinnedConnectionNeverReachesPrivateTarget() throws Exception {
        InetAddress validated = InetAddress.getByName(PUBLIC_IP);
        assertTrue(OutboundUrlPolicy.isPublicAddress(validated),
                "前置：校验阶段看到的地址必须是公网（否则实验无意义）");

        // 校验通过后 pin 住公网地址；随后攻击者把 DNS 应答切到内网（rebinding 时刻）。
        PinnedDns.pin(HOST, List.of(validated));
        dns.rebindTo(PRIVATE_IP);

        URI target = URI.create("http://" + HOST + ":" + honeypot.port() + "/probe?k=rebind");

        // 对照 1：未 pin，解析器向受控 DNS 发真实 UDP 查询 → 应连到内网蜜罐。
        try (CloseableHttpClient unpinned = client(resolver(host -> queryDns(host, dns.port())))) {
            var response = unpinned.execute(new org.apache.hc.client5.http.classic.methods.HttpGet(target));
            try {
                assertEquals(200, response.getCode(), "未 pin 客户端应命中蜜罐");
            } finally {
                response.close();
            }
        }
        assertEquals(1, honeypot.hits(), "未 pin 客户端必须被 rebinding 带进内网蜜罐（攻击真实可达）");

        // 对照 2：生产 pin 路径（PinnedDns 作为 DnsResolver）→ 只用已校验的公网地址建连。
        try (CloseableHttpClient pinned = client(resolver(PinnedDns::resolve))) {
            assertThrows(IOException.class,
                    () -> pinned.execute(new org.apache.hc.client5.http.classic.methods.HttpGet(target)).close());
        }
        assertEquals(1, honeypot.hits(), "已 pin 的客户端不得因 DNS 改答而连入内网（蜜罐计数不变）");

        // 对照 3：pin 缺失时 fail-closed，而不是回落到系统解析。
        PinnedDns.clear(HOST);
        try (CloseableHttpClient pinned = client(resolver(PinnedDns::resolve))) {
            assertThrows(IOException.class,
                    () -> pinned.execute(new org.apache.hc.client5.http.classic.methods.HttpGet(target)).close());
        }
        assertEquals(1, honeypot.hits(), "未登记 pin 的主机必须拒绝建连，不得回落 DNS");
    }

    // ------------------------------------------------------------------
    // 受控 DNS（真实 UDP）：同一主机名，应答可在 public ↔ 127.0.0.1 间切换
    // ------------------------------------------------------------------

    private static final class ControlledDns implements AutoCloseable {
        private final DatagramSocket socket;
        private final AtomicReference<String> answer;
        private final Thread loop;

        ControlledDns(String ip) throws Exception {
            this.socket = new DatagramSocket(0, InetAddress.getByName("127.0.0.1"));
            this.answer = new AtomicReference<>(ip);
            this.loop = new Thread(this::serve, "controlled-dns");
            this.loop.setDaemon(true);
            this.loop.start();
        }

        int port() {
            return socket.getLocalPort();
        }

        void rebindTo(String ip) {
            answer.set(ip);
        }

        private void serve() {
            byte[] buffer = new byte[512];
            while (!socket.isClosed()) {
                try {
                    DatagramPacket incoming = new DatagramPacket(buffer, buffer.length);
                    socket.receive(incoming);
                    respond(incoming);
                } catch (IOException closed) {
                    return;
                }
            }
        }

        private void respond(DatagramPacket incoming) throws IOException {
            byte[] query = incoming.getData();
            int length = incoming.getLength();
            if (length < 12) return;
            int questionEnd = questionEnd(query, length);
            if (questionEnd < 0) return;

            byte[] response = new byte[questionEnd + 16];
            System.arraycopy(query, 0, response, 0, 12);
            response[2] = (byte) 0x81;                      // QR=1, RD=1, RA=1
            response[3] = (byte) 0x80;
            response[4] = 0; response[5] = 1;               // QDCOUNT=1
            response[6] = 0; response[7] = 1;               // ANCOUNT=1
            response[8] = 0; response[9] = 0;               // NSCOUNT=0
            response[10] = 0; response[11] = 0;             // ARCOUNT=0
            System.arraycopy(query, 12, response, 12, questionEnd - 12);

            int at = questionEnd;
            response[at] = (byte) 0xC0; response[at + 1] = 0x0C;   // 指向 QNAME
            response[at + 2] = 0; response[at + 3] = 1;            // TYPE A
            response[at + 4] = 0; response[at + 5] = 1;            // CLASS IN
            // TTL(a+6..a+9)=0，RDLENGTH(a+10..a+11)=4
            response[at + 11] = 4;
            String[] octets = answer.get().split("\\.");
            for (int i = 0; i < 4; i++) {
                response[at + 12 + i] = (byte) Integer.parseInt(octets[i]);
            }
            socket.send(new DatagramPacket(response, response.length, incoming.getAddress(), incoming.getPort()));
        }

        private static int questionEnd(byte[] query, int length) {
            int at = 12;
            while (at < length && query[at] != 0) at += query[at] + 1;
            int end = at + 1 + 4;
            return end <= length ? end : -1;
        }

        @Override
        public void close() {
            socket.close();
        }
    }

    /** 真实 UDP DNS 查询（A 记录），供未 pin 的对照客户端使用。 */
    private static InetAddress[] queryDns(String host, int dnsPort) throws UnknownHostException {
        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setSoTimeout((int) Timeout.ofSeconds(2).toMilliseconds());
            byte[] query = new byte[12 + host.length() + 6];
            query[0] = 0x12; query[1] = 0x34;                 // 任意 ID
            query[2] = 0x01;                                  // RD
            query[5] = 1;                                     // QDCOUNT=1
            int at = 12;
            for (String label : host.split("\\.")) {
                query[at++] = (byte) label.length();
                for (char c : label.toCharArray()) query[at++] = (byte) c;
            }
            query[at++] = 0;                                   // QNAME 结束
            query[at++] = 0; query[at++] = 1;                  // QTYPE=A
            query[at++] = 0; query[at] = 1;                    // QCLASS=IN
            socket.send(new DatagramPacket(query, at + 1,
                    new InetSocketAddress("127.0.0.1", dnsPort)));

            byte[] reply = new byte[512];
            DatagramPacket packet = new DatagramPacket(reply, reply.length);
            socket.receive(packet);
            int end = 12;
            while (end < packet.getLength() && reply[end] != 0) end += reply[end] + 1;
            end += 1 + 4;                                      // 跳过 QNAME+QTYPE+QCLASS
            end += 2;                                          // 跳过应答 NAME（压缩指针）
            end += 8;                                          // TYPE+CLASS+TTL
            int rdLength = ((reply[end] & 0xFF) << 8) | (reply[end + 1] & 0xFF);
            end += 2;
            if (rdLength != 4) throw new UnknownHostException("非 A 记录: " + host);
            byte[] ip = new byte[4];
            System.arraycopy(reply, end, ip, 0, 4);
            return new InetAddress[]{InetAddress.getByAddress(host, ip)};
        } catch (IOException failed) {
            throw new UnknownHostException(host + ": " + failed.getMessage());
        }
    }

    // ------------------------------------------------------------------
    // 蜜罐 + 客户端构造（与 ModelProviderClient 的 pin 接线一致）
    // ------------------------------------------------------------------

    private static final class Honeypot implements AutoCloseable {
        private final ServerSocket server;
        private final AtomicInteger hits = new AtomicInteger();
        private final Thread loop;

        Honeypot() throws IOException {
            this.server = new ServerSocket(0, 8, InetAddress.getByName("127.0.0.1"));
            this.loop = new Thread(this::accept, "honeypot");
            this.loop.setDaemon(true);
            this.loop.start();
        }

        int port() {
            return server.getLocalPort();
        }

        int hits() {
            return hits.get();
        }

        private void accept() {
            while (!server.isClosed()) {
                try {
                    Socket socket = server.accept();
                    hits.incrementAndGet();
                    try {
                        // 先把请求读干净再回复，否则 Windows 关闭时会对未读数据发 RST，
                        // 让客户端在"已连入内网"的事实之外再抛一个误导性的读错误。
                        socket.setSoTimeout(1000);
                        java.io.InputStream in = socket.getInputStream();
                        byte[] buffer = new byte[1024];
                        StringBuilder received = new StringBuilder();
                        while (received.indexOf("\r\n\r\n") < 0) {
                            int read = in.read(buffer);
                            if (read < 0) break;
                            received.append(new String(buffer, 0, read, java.nio.charset.StandardCharsets.US_ASCII));
                        }
                        OutputStream out = socket.getOutputStream();
                        out.write("HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                                .getBytes(java.nio.charset.StandardCharsets.US_ASCII));
                        out.flush();
                    } finally {
                        socket.close();
                    }
                } catch (IOException closed) {
                    if (server.isClosed()) return;
                }
            }
        }

        @Override
        public void close() throws IOException {
            server.close();
        }
    }

    @FunctionalInterface
    private interface HostLookup {
        InetAddress[] lookup(String host) throws UnknownHostException;
    }

    /** DnsResolver 不是函数式接口（两个抽象方法），这里包一层便于注入解析策略。 */
    private static DnsResolver resolver(HostLookup strategy) {
        return new DnsResolver() {
            @Override
            public InetAddress[] resolve(String host) throws UnknownHostException {
                return strategy.lookup(host);
            }

            @Override
            public String resolveCanonicalHostname(String host) throws UnknownHostException {
                strategy.lookup(host);
                return host;
            }
        };
    }

    /** 与生产同构：DNS 交给给定解析器，禁代理/重定向/重试，短连接超时。 */
    private static CloseableHttpClient client(DnsResolver resolver) {
        ConnectionConfig connection = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(1))
                .build();
        PoolingHttpClientConnectionManager manager = PoolingHttpClientConnectionManagerBuilder.create()
                .setDnsResolver(resolver)
                .setDefaultConnectionConfig(connection)
                .build();
        ProxySelector direct = new ProxySelector() {
            @Override public List<Proxy> select(URI uri) { return List.of(Proxy.NO_PROXY); }
            @Override public void connectFailed(URI uri, SocketAddress address, IOException failure) { }
        };
        return HttpClients.custom()
                .setConnectionManager(manager)
                .setRoutePlanner(new SystemDefaultRoutePlanner(direct))
                .setDefaultRequestConfig(RequestConfig.custom()
                        .setConnectionRequestTimeout(Timeout.ofSeconds(1))
                        .setResponseTimeout(Timeout.ofSeconds(2))
                        .build())
                .disableRedirectHandling()
                .disableAutomaticRetries()
                .build();
    }
}
