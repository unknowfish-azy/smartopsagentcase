// Curated from the DNS/BIND material supplied by the user in this conversation.
// The original Markdown attachment was not supplied; lab examples are not live assets.
export const dnsBindProvenance = Object.freeze({
  source: '用户提供的 DNS/BIND 教程整理文本',
  attachmentVerified: false,
  references: ['BIND 9 Administrator Reference Manual', 'RFC 7766', 'RHEL NetworkManager DNS documentation']
})

const makeEntry = (id, title, section, summary, content, tags, risk = 'READ_ONLY') => ({
  id: 'dns.bind.' + id,
  domain: 'linux', platform: 'CentOS / BIND', service: 'dns-bind',
  type: 'DNS / BIND KNOWLEDGE', title, section, summary, content,
  tags: ['DNS', 'BIND', ...tags], source: dnsBindProvenance.source,
  version: 'CentOS/BIND 教学场景 · 通用诊断原则', risk, executionAllowed: false
})

export const dnsBindEntries = [
  makeEntry('resolution-path', 'DNS 解析与 Web 访问链路', '01 / 基础与边界',
    '区分 hosts、resolver、DNS 和后续 TCP/HTTP；域名打不开不等于 DNS 故障。',
    '[SRC] 用户/程序 → /etc/hosts → resolver（/etc/resolv.conf）→ 权威区/缓存/上游 → IP → TCP/IP → HTTP/HTTPS → Web 服务。FQDN 为完整域名，例如 www.example.test.。正向解析为域名到 IP，反向解析为 IP 到 PTR 名称。Windows hosts 路径为 C:\\Windows\\System32\\drivers\\etc\\hosts，Linux 为 /etc/hosts。\n[OPS] 区分客户端未发 DNS 请求、请求超时、NXDOMAIN、错误 IP，以及 DNS 正确但 TCP/HTTP 失败。getent hosts <fqdn> 更接近系统名称服务路径；nslookup/dig 直接测试 DNS，不证明 hosts 生效。ping 通不证明 HTTP 可用。',
    ['hosts', 'FQDN', 'getent', 'nslookup', 'NXDOMAIN', 'HTTP']),
  makeEntry('resolver', 'Resolver 与 NetworkManager 持久配置', '02 / Resolver',
    '排查 DNS 改完重启失效，追溯 /etc/resolv.conf 的生成者与连接配置。',
    '[SRC] 教程用 echo nameserver 192.168.126.172 > /etc/resolv.conf 作临时实验，并在 /etc/NetworkManager/system-connections/ens33.nmconnection 配置 DNS。\n[VERIFY] /etc/resolv.conf 常由 NetworkManager 等组件生成，不能假定手工修改永久有效。\n[OPS] 只读检查：cat /etc/resolv.conf；ls -l /etc/resolv.conf；nmcli connection show --active；nmcli connection show <connection-name>。对照活动连接 DNS、自动获取 DNS、文件生成者和客户端实际查询的服务器。修改连接或覆盖配置须审批。',
    ['/etc/resolv.conf', 'NetworkManager', 'nmcli', 'DNS 改完重启失效']),
  makeEntry('transport-records', 'DNS 记录、SOA 与 UDP/TCP 53', '03 / 协议与记录',
    '理解常见记录与 TTL、serial；DNS 查询和区域传送都需考虑 TCP。',
    '[SRC] $TTL 是缓存生存时间；A/AAAA 为 IPv4/IPv6；CNAME 为别名；MX 为邮件交换；NS 为权威名称服务器；PTR 为反向记录；SOA 包含 serial、refresh、retry、expire、minimum。\n[VERIFY] 普通查询大量使用 UDP/53，但 DNS 实现也必须支持 TCP；AXFR 使用 TCP/53，BIND 支持 IXFR。大响应或截断要检查 TCP 路径。\n[OPS] dig @<dns-ip> <fqdn> A；dig +tcp @<dns-ip> <fqdn> A；dig @<dns-ip> <zone> SOA。不要把“只开 UDP/53”当作通用修复。',
    ['UDP/53', 'TCP/53', 'AXFR', 'IXFR', 'SOA', 'serial', 'TTL', 'A', 'AAAA', 'CNAME', 'MX', 'NS', 'PTR']),
  makeEntry('bind-files', 'BIND 文件职责与四层验证', '04 / BIND 配置',
    '分别验证配置语法、zone 数据、named 服务和客户端实际查询。',
    '[SRC] /etc/named.conf 为主配置；/etc/named.rfc1912.zones 常存 zone 定义；/var/named/*.zone 为区数据；/var/named/slaves/ 可存 secondary 数据。教程以 named.localhost、named.loopback 为模板。\n[OPS] 第一层 named-checkconf /etc/named.conf（可加 -z 检查区域加载）；第二层 named-checkzone <zone-name> <zone-file>；第三层 systemctl status named 及日志；第四层 dig/nslookup 定向查询，再测客户端默认 DNS。配置检查通过不代表服务可达；进程运行不代表 zone 已正确加载。reload/restart 有副作用，需审批和复验。',
    ['/etc/named.conf', '/etc/named.rfc1912.zones', '/var/named', 'named-checkconf', 'named-checkzone']),
  makeEntry('forward-zone', 'BIND 正向解析实验', '05 / 正向解析',
    '以 lhp.cluster 实验区说明 master、A 记录和 DNS+Web 验证链。',
    '[SRC] 教程示例：client.lhp.cn=192.168.126.171，dns.lhp.cn=192.168.126.172，web.lhp.cn=192.168.126.173；目标 www.lhp.cluster → 192.168.126.173。zone "lhp.cluster" IN { type master; file "lhp.cluster.zone"; allow-update { none; }; };\n[OPS] named-checkconf /etc/named.conf；named-checkzone lhp.cluster /var/named/lhp.cluster.zone；dig @192.168.126.172 www.lhp.cluster A；客户端默认 resolver 查询；最后 curl -v http://www.lhp.cluster。示例 IP/域名不可作为生产配置。',
    ['lhp.cluster', 'type master', 'zone file', '192.168.126.173']),
  makeEntry('reverse-multizone', '反向 PTR 与多域解析', '06 / 反向与多域',
    '用 in-addr.arpa 检查反向解析，单域故障优先检查对应 zone。',
    '[SRC] 192.168.126.0/24 示例反向区为 126.168.192.in-addr.arpa；173 PTR www.lhp.cluster.。教程还让 www.test.net 与 bbs.haha.cc 分别通过不同 zone 解析到同一 Web IP。\n[OPS] dig -x 192.168.126.173 @<dns-ip>。若仅 haha.cc 失败，查其 zone 定义、named-checkzone haha.cc /var/named/haha.cc.zone、记录和加载日志；若所有 zone 失败，再查 named 全局配置、监听、ACL、resolver 和 53 端口。PTR 目标使用绝对名称并检查末尾点号。',
    ['PTR', 'in-addr.arpa', '126.168.192.in-addr.arpa', 'test.net', 'haha.cc']),
  makeEntry('secondary', 'BIND 主从同步与区域传送', '07 / Master-Slave',
    '比较主从 SOA serial，再查传送 ACL、主服务器地址、TCP/53 与日志。',
    '[SRC] master 示例为 allow-transfer { 192.168.126.174; };；slave 示例含 type slave; file "slaves/test.net"; masters { 192.168.126.172; };。\n[VERIFY] primary/master 与 secondary/slave 为兼容术语；secondary 通过 AXFR/IXFR 获取区数据，SOA serial 用于判断更新，NOTIFY 可加快发现更新。\n[OPS] 分别 dig @<master> <zone> SOA 与 dig @<slave> <zone> SOA；再查 TCP/53、allow-transfer、masters、区名、slaves/ 权限及 named 日志。版本完全一致不是绝对前提。',
    ['Master', 'Slave', 'Primary', 'Secondary', 'allow-transfer', 'masters', 'SOA serial']),
  makeEntry('web-boundary', 'DNS 正常但网站打不开', '08 / DNS + Web',
    '解析正确后转向 TCP、Web 监听、虚拟主机与应用层。',
    '[SRC] 原教程用 httpd 和 curl 串联 DNS 与 Web 测试。\n[OPS] nslookup 失败：查 resolver/53/zone；有 IP 而 ping 不通：查路由与 ICMP 策略；ping 通而 curl 不通：查 TCP/80/443、监听和服务；curl 返回 4xx/5xx：查 HTTP 与应用；域名和 IP 结果不同：查 Host header/VirtualHost。只读命令：dig <fqdn>；curl -v http://<fqdn>；ss -lntp；systemctl status httpd。不要在 DNS 已被证据排除后继续修改 zone。',
    ['curl', 'httpd', 'VirtualHost', 'Host header', 'TCP', 'HTTP']),
  makeEntry('diagnostic-rules', 'DNS-001 至 DNS-005：故障证据链', '09 / 故障诊断',
    '覆盖解析失败、超时、旧记录、主从未同步以及 DNS 正常但 Web 失败。',
    '[OPS] DNS-001 Could not resolve host：检查 hosts、resolv.conf、getent hosts、定向 dig；区分 NXDOMAIN、timeout、错误 IP。DNS-002 查询超时：检查 UDP/TCP 53、监听、ACL、防火墙、路由和 named 日志。DNS-003 zone 改后旧 IP：对照权威直查与默认 resolver，查 TTL/缓存、SOA serial、zone 加载和客户端 DNS。DNS-004 slave 旧记录：先比两端 serial，再查 allow-transfer、masters、TCP/53、权限与日志。DNS-005 DNS 正常但网站打不开：转入 TCP → Web Server → VirtualHost → Application。\n证据优先级：实际命令输出 > 服务日志 > 配置内容 > 网络监听 > 用户描述 > 经验推断。回答先分类和列现象，再给 2~5 条最小验证、判定逻辑、证据支持的修复、复验与风险。',
    ['DNS-001', 'DNS-002', 'DNS-003', 'DNS-004', 'DNS-005', 'NXDOMAIN', 'timeout']),
  makeEntry('safety-cases', 'DNS 安全边界与四类训练案例', '10 / 风险与案例',
    '实验室关闭防火墙/SELinux 的做法不能自动转为生产修复。',
    '[SRC] 原教程停止 firewalld/SELinux 是教学简化。\n[OPS] 生产仅开放必要的 UDP/TCP 53 与来源；allow-query、allow-transfer 收紧到可信范围；改前备份；先 checkconf/checkzone，再经审批 reload/restart 并复验。禁止凭猜测修改 SOA serial、TTL、ACL。\n案例 A：curl 报 Could not resolve host，先查 hosts/resolver，再区分 NXDOMAIN 与 timeout。案例 B：nslookup www.lhp.cluster 返回 192.168.126.173，但 curl 失败，转查 TCP/HTTP/VirtualHost。案例 C：www.test.net 正常而 bbs.haha.cc 失败，先查 haha.cc zone。案例 D：master 已更新而 slave 数据旧，先比两端 SOA serial，再查传送链。',
    ['firewalld', 'SELinux', 'allow-query', 'allow-transfer', '安全', '案例'], 'APPROVAL_REQUIRED')
]

export const dnsBindRules = Object.freeze([
  { id: 'DNS-001', symptom: 'Could not resolve host', evidence: ['hosts', 'resolv.conf', 'getent hosts', 'dig/nslookup'], decision: '区分解析路径、NXDOMAIN、超时和错误地址' },
  { id: 'DNS-002', symptom: 'DNS query timeout', evidence: ['resolver', 'UDP/TCP 53', 'named listen/ACL/log'], decision: '区分网络、策略和服务故障' },
  { id: 'DNS-003', symptom: 'zone 修改后旧 IP', evidence: ['权威直查', 'SOA serial', 'TTL/cache', 'zone load'], decision: '查清改动未传播的层级' },
  { id: 'DNS-004', symptom: 'secondary 数据旧', evidence: ['两端 SOA serial', 'allow-transfer', 'masters', 'TCP/53'], decision: '确认区域传送路径' },
  { id: 'DNS-005', symptom: 'DNS 正常但网站失败', evidence: ['DNS answer', 'TCP connect', 'HTTP response', 'VirtualHost'], decision: '转入 Web 与应用层' }
])
