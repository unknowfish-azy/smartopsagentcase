// Reference-only network fundamentals. This pack deliberately contains no
// executor, runtime client, or infrastructure lookup.
const provenance = {
  id: 'network-foundation-reference-2026-09-24',
  kind: 'curated_reference_pack',
  attachmentVerified: false,
  sourceFile: null,
  note: 'Reference material for diagnosis and learning; not an attached authoritative source.'
}

const definitions = [
  ['network.model.osi', 'OSI model and evidence boundaries', 'OSI', 'OSI layers organize evidence, but incidents should use the smallest relevant path rather than mechanically testing every layer.', ['OSI', 'layer', 'evidence']],
  ['network.model.tcpip', 'TCP/IP model', 'TCP/IP', 'Link, internet, transport, and application concerns map to different observations and failure modes.', ['TCP/IP', 'model', 'layer']],
  ['network.ipv4.address', 'IPv4 address and prefix', 'IPv4', 'An IPv4 address identifies an interface in a prefix; address, prefix length, gateway, and route must be evaluated together.', ['IPv4', 'address', 'prefix']],
  ['network.ipv4.classful', 'Classful IPv4 addressing (historical)', 'IPv4', 'Class A, B, and C boundaries are historical fundamentals. Modern routing uses CIDR rather than classful assumptions.', ['IPv4', 'classful', 'historical'], { knowledge_type: 'historical_fundamentals' }],
  ['network.ipv4.subnet', 'CIDR subnetting and ranges', 'IPv4', 'CIDR expresses the network prefix length. Calculate network, usable range, broadcast, and boundary before changing an address.', ['CIDR', 'subnet', 'broadcast'], {
    examples: [
      { address: '192.168.10.64/26', network: '192.168.10.64', firstHost: '192.168.10.65', lastHost: '192.168.10.126', broadcast: '192.168.10.127' },
      { address: '10.0.0.0/31', note: 'Point-to-point semantics depend on the platform and RFC 3021 support.' },
      { address: '192.0.2.10/32', note: 'A host route identifies one address.' }
    ]
  }],
  ['network.ipv4.private', 'Private IPv4 ranges', 'IPv4', 'RFC 1918 private ranges are 10/8, 172.16/12, and 192.168/16; private does not mean reachable or safe.', ['RFC1918', 'private', 'NAT']],
  ['network.ipv4.special', 'Special-use IPv4 addresses', 'IPv4', 'Loopback, link-local, documentation, multicast, and unspecified ranges have distinct routing and diagnostic meanings.', ['loopback', 'link-local', 'multicast']],
  ['network.ipv6.address', 'IPv6 address and prefix', 'IPv6', 'IPv6 uses 128-bit addresses and prefixes; link-local addresses and global addresses have different reachability scopes.', ['IPv6', 'prefix', 'scope']],
  ['network.ipv6.ndp', 'IPv6 Neighbor Discovery', 'IPv6', 'NDP replaces ARP functions with ICMPv6 messages and depends on link-local reachability and router advertisements.', ['IPv6', 'NDP', 'ICMPv6']],
  ['network.arp.next_hop', 'ARP and next-hop resolution', 'Ethernet', 'ARP resolves a local IPv4 next hop to a MAC address. A remote destination normally resolves the gateway, not the remote host.', ['ARP', 'next hop', 'MAC']],
  ['network.icmp.diagnostic', 'ICMP diagnostics and limits', 'ICMP', 'Ping tests an ICMP path only; blocked ICMP does not prove TCP failure, and successful ICMP does not prove application health.', ['ICMP', 'ping', 'diagnosis']],
  ['network.tcp.state', 'TCP states including TIME-WAIT', 'TCP', 'TIME-WAIT protects delayed segments after close. It is evidence about connection churn, not by itself a service failure.', ['TCP', 'TIME-WAIT', 'socket']],
  ['network.tcp.handshake', 'TCP three-way handshake', 'TCP', 'SYN, SYN-ACK, and ACK establish a connection. SYN retries, RST, and timeout point to different layers and policies.', ['TCP', 'SYN', 'handshake']],
  ['network.tcp.retransmission', 'TCP retransmission and loss', 'TCP', 'Retransmission indicates missing acknowledgements and should be correlated with packet loss, congestion, MTU, and peer behavior.', ['TCP', 'retransmission', 'loss']],
  ['network.udp.behavior', 'UDP characteristics', 'UDP', 'UDP has no handshake or delivery guarantee; application protocols must provide ordering, retry, or integrity where needed.', ['UDP', 'datagram', 'transport']],
  ['network.dns.record', 'DNS record types', 'DNS', 'A, AAAA, CNAME, MX, TXT, NS, and PTR records serve different purposes; a record existing does not prove the application path works.', ['DNS', 'A', 'AAAA', 'CNAME']],
  ['network.dns.resolution', 'DNS resolution path', 'DNS', 'Check stub resolver, configured nameservers, recursion, authoritative answers, search domains, and split-horizon behavior separately.', ['DNS', 'resolver', 'authoritative']],
  ['network.dns.ttl', 'DNS TTL and cache behavior', 'DNS', 'TTL controls cache freshness, not an instant global update. Record changes require checking authoritative and recursive views.', ['DNS', 'TTL', 'cache']],
  ['network.dhcp.lease', 'DHCP lease lifecycle', 'DHCP', 'Discover, offer, request, and acknowledgement establish a lease; address presence alone does not prove correct gateway or DNS options.', ['DHCP', 'lease', 'IPv4']],
  ['network.nat.snat', 'Source NAT and masquerading', 'NAT', 'SNAT changes source identity for egress traffic and can affect return paths, logging, and policy matching.', ['NAT', 'SNAT', 'egress']],
  ['network.nat.dnat', 'Destination NAT and port forwarding', 'NAT', 'DNAT changes the destination before forwarding; validate listener, route, firewall, and return path independently.', ['NAT', 'DNAT', 'port forwarding']],
  ['network.routing.longest_prefix', 'Longest-prefix route selection', 'Routing', 'Routers prefer the most specific matching prefix before administrative distance or metric.', ['route', 'longest prefix', 'FIB']],
  ['network.routing.default', 'Default route and gateway', 'Routing', 'A default route handles destinations without a more specific match; its presence does not prove the gateway forwards traffic.', ['route', 'default gateway', 'next hop']],
  ['network.routing.asymmetric', 'Asymmetric routing', 'Routing', 'Forward and return paths can differ, causing stateful firewall drops, misleading captures, and uneven latency.', ['route', 'asymmetric', 'firewall']],
  ['network.switch.mac_table', 'Switch MAC address table', 'Ethernet switching', 'Switches learn source MAC locations and forward frames by VLAN. A stale or flapping entry can resemble host failure.', ['switch', 'MAC table', 'VLAN']],
  ['network.switch.vlan', 'VLAN segmentation', 'Ethernet switching', 'Access and trunk semantics determine which VLAN tags cross a link; matching IP ranges alone cannot prove VLAN connectivity.', ['VLAN', 'trunk', 'access']],
  ['network.router.forwarding', 'Router forwarding boundary', 'Routing', 'A router forwards between networks according to route, policy, and next-hop resolution; local ARP is not required for every destination.', ['router', 'forwarding', 'next hop']],
  ['network.firewall.stateful', 'Stateful firewall flow', 'Firewall', 'Stateful policy evaluates direction, interface, zone, source, destination, port, and connection state.', ['firewall', 'stateful', 'policy']],
  ['network.firewall.nat_order', 'Firewall and NAT ordering', 'Firewall', 'Platform-specific processing order matters; inspect the effective policy and counters rather than inferring from a rule label.', ['firewall', 'NAT', 'packet path']],
  ['network.loadbalancer.l4', 'Layer 4 load balancing', 'Load balancing', 'L4 balancing selects a backend for a connection without understanding HTTP content; health checks can pass while requests still fail.', ['load balancer', 'L4', 'health check']],
  ['network.loadbalancer.l7', 'Layer 7 reverse proxying', 'Load balancing', 'L7 proxies can route by host and path and may terminate TLS, so backend and proxy observations must be separated.', ['reverse proxy', 'L7', 'HTTP']],
  ['network.http.status', 'HTTP status and transport layers', 'HTTP', 'HTTP status proves an application response was generated, not that every upstream dependency is healthy.', ['HTTP', 'status', 'application']],
  ['network.tls.handshake', 'TLS handshake and certificate scope', 'TLS', 'Certificate name, SNI, trust chain, protocol, and time are separate checks; TCP reachability is necessary but insufficient.', ['TLS', 'certificate', 'SNI']],
  ['network.proxy.forward', 'Forward and reverse proxy headers', 'HTTP', 'Forwarded and X-Forwarded-* headers are trust-boundary data and should not be accepted as identity without a controlled proxy.', ['proxy', 'Forwarded', 'trust boundary']],
  ['network.mtu.fragmentation', 'MTU, MSS, and fragmentation', 'Packet delivery', 'Path MTU issues can break large packets while small pings pass; compare interface MTU, MSS behavior, and tunnel overhead.', ['MTU', 'MSS', 'fragmentation']],
  ['network.vpn.tunnel', 'VPN tunnel and underlay', 'VPN', 'A tunnel can be established while overlay routes, selectors, or application ports remain wrong; validate underlay and overlay separately.', ['VPN', 'tunnel', 'overlay']],
  ['network.wifi.layers', 'Wi-Fi association versus IP reachability', 'Wi-Fi', 'Association and authentication are link-layer states; DHCP, route, DNS, and application checks remain separate.', ['Wi-Fi', 'association', 'DHCP']],
  ['network.observability.flow', 'Network evidence sources', 'Observability', 'Use interface counters, socket state, route, resolver output, flow logs, packet capture, and application logs according to the hypothesis.', ['observability', 'flow logs', 'packet capture']],
  ['network.reasoning.next_evidence', 'Next Best Evidence decision rule', 'Diagnosis', 'Choose the least risky observation that can distinguish the current hypotheses; do not jump from a symptom to a mutation.', ['Next Best Evidence', 'evidence', 'hypothesis']],
  ['network.reasoning.layer_boundary', 'Layer boundary reasoning', 'Diagnosis', 'Record what each observation proves and what it cannot prove, then stop collecting evidence when the hypothesis is resolved.', ['evidence', 'layer boundary', 'diagnosis']],
  ['INC-NET-SUBNET', 'Subnet overlap or incorrect prefix', 'Incident', 'Overlapping or incorrect prefixes can send traffic to the wrong next hop. Compare intended CIDR, address, route table, and ARP evidence before any change.', ['INC-NET-SUBNET', 'CIDR', 'subnet overlap']],
  ['INC-NET-DNS', 'DNS resolves to the wrong address', 'Incident', 'Compare client, recursive, and authoritative answers, TTL, split-horizon policy, and application SNI before changing records.', ['INC-NET-DNS', 'DNS', 'split horizon']],
  ['INC-NET-TIMEOUT', 'Connection timeout investigation', 'Incident', 'A timeout can arise from route, ACL, firewall, packet loss, listener, or asymmetric return path; distinguish it from an explicit refusal.', ['INC-NET-TIMEOUT', 'timeout', 'firewall']],
  ['INC-NET-REFUSED', 'Connection refused investigation', 'Incident', 'An immediate refusal usually means a reachable host rejected the connection or no process is listening; validate address, namespace, and policy.', ['INC-NET-REFUSED', 'refused', 'LISTEN']],
  ['INC-NET-TLS', 'TLS name or trust failure', 'Incident', 'Separate TCP reachability, TLS negotiation, SNI, certificate validity, trust chain, and system clock evidence.', ['INC-NET-TLS', 'TLS', 'certificate']]
]

const relatedByIndex = definitions.map(item => item[0])

export const networkFoundationEntries = definitions.map(([id, title, section, summary, tags, extra = {}], index) => ({
  id,
  packId: 'network-foundation',
  domain: 'network',
  platform: 'Network',
  service: 'network-foundation',
  type: extra.knowledge_type === 'historical_fundamentals' ? 'HISTORICAL FUNDAMENTALS' : 'ENGINEERING KNOWLEDGE',
  title,
  summary,
  content: `${title}\n\n${summary}${extra.examples ? `\n\nExamples:\n${extra.examples.map(example => JSON.stringify(example)).join('\n')}` : ''}\n\nEvidence boundary: this reference supports observation and diagnosis only. It does not authorize network changes or claim live infrastructure state.`,
  source: 'Network Foundations Reference Pack',
  section,
  version: '1.0',
  risk: 'READ_ONLY',
  tags,
  provenance,
  executionAllowed: false,
  relatedIds: extra.relatedIds || [relatedByIndex[(index + 1) % relatedByIndex.length]],
  ...extra
}))
