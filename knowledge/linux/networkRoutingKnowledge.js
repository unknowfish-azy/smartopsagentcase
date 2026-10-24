// Reference-only L3 routing knowledge and deterministic route explanation.
// No network client, executor, or live device state is imported here.
const provenance = {
  id: 'network-routing-reference-2026-09-24',
  kind: 'curated_course_and_engineering_pack',
  attachmentVerified: false,
  sourceFile: null,
  note: 'Packet Tracer topology and CLI examples are lab/demo context; production route state must be observed.'
}

const read = (command, purpose, parameters = 'Read-only observation; record source, destination, device, timestamp, and scope.') => ({
  command, purpose, parameters, read_only: true, risk: 'READ_ONLY', risk_level: 'LOW', executionAllowed: false,
  verification: 'Correlate the result with route state, next-hop reachability, return path, and end-to-end behavior.'
})

const change = (command, purpose, parameters, riskLevel = 'MEDIUM', blastRadius = ['target route', 'affected destination networks']) => ({
  command, purpose, parameters, read_only: false, risk: riskLevel, risk_level: riskLevel,
  executionAllowed: false, requires_preview: true, approval_required: true, blastRadius,
  verification: 'Snapshot routes before change, apply only after approval, verify forward and return paths, and retain rollback.'
})

const node = (id, title, category, summary, tags, commands = [], relatedIds = [], extra = {}) => ({
  id, title, category, summary, tags, commands, relatedIds, type: 'ENGINEERING KNOWLEDGE',
  executionAllowed: false, risk: 'READ_ONLY', ...extra,
  content: `${title}\n\n${summary}\n\nEvidence boundary: this node explains route reasoning and does not claim live infrastructure state.`
})

export const networkRoutingNodes = [
  node('network.routing.router_l3_device', 'Router and L3 forwarding device', 'L3 Routing', 'A router or Layer-3 switch forwards packets between IP networks using a routing table; a router is not the only device capable of L3 forwarding.', ['Router', 'L3 Switch', 'forwarding'], [read('show ip interface brief', 'Inspect L3 interfaces and operational state')], ['network.routing.routing_table', 'network.vlan.concept']),
  node('network.routing.routing_table', 'Routing table and route entry', 'L3 Routing', 'A routing table describes available paths to destination networks. Route entries carry destination/prefix, next hop, exit interface, source, metric, administrative distance, and state.', ['Routing Table', 'Route Entry', 'destination', 'next hop'], [read('show ip route', 'Inspect connected, static and dynamic routes')], ['network.routing.connected', 'network.routing.static', 'network.routing.default']),
  node('network.routing.connected', 'Connected route', 'L3 Routing', 'An operational interface with an IP prefix can create a directly connected route, such as 192.168.1.0/24 via Fa0/0; configured does not necessarily mean operational.', ['Connected Route', 'directly connected', 'interface'], [read('show ip interface brief', 'Verify address, administrative state and line protocol'), read('show ip route connected', 'Inspect connected routes')], ['network.routing.interface_state', 'network.routing.routing_table']),
  node('network.routing.static', 'Static route as destination plus forwarding choice', 'L3 Routing', 'A static route maps a destination network to a next hop and/or exit interface. CLI syntax varies by platform; the internal model must not be interface-only.', ['Static Route', 'destination', 'next hop', 'exit interface'], [read('show ip route static', 'Inspect active static routes'), change('ip route <destination> <mask> <next-hop-or-interface>', 'Preview a platform-specific static route', 'Replace placeholders only after topology, next hop, interface and blast radius are verified.', 'MEDIUM')], ['network.routing.route_entry', 'network.routing.next_hop']),
  node('network.routing.route_entry', 'Static route three-part model', 'L3 Routing', 'A route entry separates Destination Network, Next Hop, and Exit Interface, with source, metric, preference and state captured independently.', ['route entry', 'destination network', 'Next Hop', 'Exit Interface'], [read('show ip route', 'Compare route fields with the expected path')], ['network.routing.static', 'network.routing.route_lookup']),
  node('network.routing.next_hop', 'Next hop and exit interface', 'L3 Routing', 'After route lookup selects a path, the device resolves the next hop and sends through the selected exit interface; both must be reachable and operational.', ['Next Hop', 'Exit Interface', 'forwarding'], [read('ping <next-hop>', 'Test next-hop reachability from the routing device'), read('show ip interface brief', 'Check outgoing interface state')], ['network.routing.route_lookup', 'network.routing.interface_state']),
  node('network.routing.default_route_selection', 'Default route and gateway of last resort', 'L3 Routing', '0.0.0.0/0 is used only when no more specific route matches. A missing default route matters only when no other matching route exists.', ['Default Route', '0.0.0.0/0', 'Gateway of last resort'], [read('show ip route', 'Check whether a default route is installed')], ['network.routing.longest_prefix_match', 'network.routing.return_path']),
  node('network.routing.dynamic', 'Dynamic route source', 'L3 Routing', 'Dynamic sources such as OSPF, RIP, IS-IS, EIGRP or BGP can populate routes; route source codes and preference are platform/version sensitive.', ['Dynamic Route', 'OSPF', 'BGP', 'route source'], [read('show ip route', 'Inspect route source and preference'), read('show running-config', 'Read platform configuration context')], ['network.routing.routing_table', 'network.routing.route_preference']),
  node('network.routing.longest_prefix_match', 'Longest Prefix Match', 'L3 Routing', 'When multiple routes match a destination, the most specific prefix is selected before route preference and metric tie-breaking.', ['Longest Prefix Match', 'LPM', 'specific prefix'], [read('show ip route <destination>', 'Inspect matching route candidates')], ['network.routing.route_lookup', 'network.routing.default']),
  node('network.routing.route_preference', 'Route preference, administrative distance and metric', 'L3 Routing', 'For equal prefix length, devices apply platform route preference and metric rules; values and symbols are version/platform sensitive.', ['administrative distance', 'metric', 'route preference'], [read('show ip route <destination>', 'Inspect selected route and preference')], ['network.routing.longest_prefix_match', 'network.routing.dynamic']),
  node('network.routing.route_lookup', 'Route lookup pipeline', 'L3 Routing', 'Destination IP is matched against route prefixes, the best route is selected, next hop is resolved, and the packet is forwarded through the exit interface.', ['Route Lookup', 'forwarding', 'best match'], [read('show ip route <destination>', 'Explain route selection for one destination'), read('show ip cef <destination>', 'Inspect platform forwarding decision when supported')], ['network.routing.longest_prefix_match', 'network.routing.next_hop']),
  node('network.routing.route_explain', 'Route Explain', 'L3 Routing', 'A useful explanation lists destination, all matching routes, selected route, selection reason, next hop and exit interface instead of saying only that the routing table contains an entry.', ['Route Explain', 'explain route', 'selected route'], [read('show ip route <destination>', 'Collect route candidates and selected forwarding path')], ['network.routing.route_lookup', 'network.routing.return_path']),
  node('network.routing.interface_state', 'L3 interface state matrix', 'L3 Routing', 'Validate interface existence, IP/prefix, administrative state, operational state and line protocol. IP configuration alone does not prove forwarding.', ['interface state', 'administratively down', 'line protocol'], [read('show ip interface brief', 'Check IP, admin state and protocol state'), read('show interfaces <interface>', 'Inspect link and protocol detail')], ['network.routing.connected', 'network.routing.next_hop']),
  node('network.routing.same_subnet', 'Same subnet versus routed path', 'L3 Routing', 'Hosts in the same subnet normally use L2/ARP; hosts in different subnets send to a default gateway and enter L3 route lookup.', ['same subnet', 'gateway', 'ARP', 'routed path'], [read('ip route get <destination>', 'Observe host-selected path'), read('show ip route', 'Inspect gateway device routing')], ['network.routing.return_path', 'network.l2.switch_forwarding']),
  node('network.routing.gateway', 'Default gateway selection', 'L3 Routing', 'A source host uses its gateway when the destination is outside the local prefix; wrong gateway or mask can prevent route lookup from reaching the intended router.', ['Default Gateway', 'gateway', 'subnet'], [read('ip addr', 'Verify source prefix'), read('ip route', 'Verify host default route')], ['network.routing.same_subnet', 'network.routing.interface_state']),
  node('network.routing.return_path', 'Forward path and return path', 'L3 Routing', 'Forward connectivity does not guarantee reverse connectivity. Bidirectional communication requires a usable return route, default route, summary route or dynamic route.', ['Return Path', 'bidirectional', 'reverse route'], [read('show ip route', 'Inspect destination-side route to the source'), read('traceroute <source>', 'Observe reverse path when authorized')], ['network.routing.asymmetric', 'network.routing.blackhole']),
  node('network.routing.asymmetric_path', 'Asymmetric routing', 'L3 Routing', 'Forward and return paths may differ; stateful firewalls, captures and latency can expose the asymmetry even when one direction works.', ['Asymmetric Routing', 'return path', 'stateful firewall'], [read('traceroute <destination>', 'Observe forward hops'), read('traceroute <source>', 'Observe reverse hops')], ['network.routing.return_path', 'network.routing.policy']),
  node('network.routing.traceroute', 'Traceroute and hop-by-hop evidence', 'L3 Routing', 'traceroute, tracepath and tracert reveal observed L3 hops and a repeated/stopped hop; an incomplete trace is an investigation hint, not root-cause proof.', ['traceroute', 'tracepath', 'tracert', 'hop'], [read('traceroute <destination>', 'Observe path hops and latency'), read('tracepath <destination>', 'Observe path and MTU hints')], ['network.routing.trace_evidence', 'network.routing.multi_hop']),
  node('network.routing.trace_evidence', 'Trace evidence model', 'L3 Routing', 'Store source, destination, hop number, address and latency so Jellyfish can correlate path evidence with Whale topology and route state.', ['trace evidence', 'hop', 'latency'], [read('traceroute <destination>', 'Collect hop-by-hop evidence')], ['network.routing.traceroute', 'network.routing.multi_hop']),
  node('network.routing.multi_hop', 'Multi-router route graph', 'L3 Routing', 'A path can traverse R1, R2 and R3 between source and destination networks; each device needs a usable onward path and the destination-side return path.', ['multi-hop', 'Route Graph', 'topology'], [read('show ip route', 'Inspect each router in the path'), read('traceroute <destination>', 'Correlate observed hops')], ['network.routing.return_path', 'network.routing.static']),
  node('network.routing.blackhole', 'Routing blackhole', 'L3 Troubleshooting', 'A route can exist while traffic is discarded due to wrong route, null route, ACL/firewall, broken next hop or missing return path.', ['blackhole', 'null route', 'discard'], [read('show ip route <destination>', 'Check selected route and discard behavior'), read('traceroute <destination>', 'Locate the last observed hop')], ['network.routing.return_path', 'network.routing.policy']),
  node('network.routing.loop', 'Routing loop and TTL expiration', 'L3 Troubleshooting', 'A wrong path can repeat R1→R2→R3→R1 until TTL expires; inspect repeated hops and route tables before proposing any change.', ['Routing Loop', 'TTL', 'repeating hop'], [read('traceroute <destination>', 'Identify repeating hop pattern'), read('show ip route', 'Compare route selection on repeated devices')], ['network.routing.traceroute', 'network.routing.route_lookup']),
  node('network.routing.first_ping', 'First ping may be slower', 'L3 Troubleshooting', 'A first ping can be slower because of ARP/neighbor resolution, MAC learning or other path setup; treat this as an observation, not a fixed root cause.', ['first ping', 'ARP', 'neighbor resolution'], [read('ping <destination>', 'Compare first and subsequent probes'), read('show arp', 'Check neighbor resolution')], ['network.routing.same_subnet', 'network.arp.next_hop']),
  node('network.routing.policy', 'Routing policy and ACL boundary', 'L3 Troubleshooting', 'A selected route and reachable next hop do not bypass ACL, firewall, null route or policy decisions; policy evidence remains a separate layer.', ['ACL', 'Firewall', 'policy', 'null route'], [read('show running-config', 'Inspect policy context'), read('show ip route <destination>', 'Check selected and discard routes')], ['network.routing.blackhole', 'network.routing.return_path']),
  node('network.command.show_ip_route', 'Command Card: show ip route', 'Command Card', 'Cisco IOS/Packet Tracer style query for connected, static and dynamic route entries; symbols and fields are platform/version sensitive.', ['show ip route', 'C', 'S', 'O', 'B'], [read('show ip route', 'Inspect routing table')], ['network.routing.routing_table', 'network.routing.route_lookup'], { source_scope: 'Cisco IOS/Packet Tracer style', version_sensitive: true }),
  node('network.command.show_ip_interface_brief', 'Command Card: show ip interface brief', 'Command Card', 'Query IP address, administrative state and line protocol for L3 interfaces.', ['show ip interface brief', 'interface state'], [read('show ip interface brief', 'Inspect interface/IP readiness')], ['network.routing.interface_state']),
  node('network.command.show_interfaces', 'Command Card: show interfaces', 'Command Card', 'Query link, protocol, errors, counters and interface detail before blaming route state.', ['show interfaces', 'link', 'errors'], [read('show interfaces <interface>', 'Inspect interface detail')], ['network.routing.interface_state']),
  node('network.command.ping', 'Command Card: ping', 'Command Card', 'Use a bounded ping as one probe for next hop, destination and return behavior; success is not full application health.', ['ping', 'next hop', 'verification'], [read('ping <next-hop>', 'Check next-hop reachability'), read('ping <destination>', 'Check destination reachability')], ['network.routing.next_hop', 'network.routing.return_path']),
  node('network.command.traceroute', 'Command Card: traceroute/tracepath/tracert', 'Command Card', 'Observe L3 path hops and latency; trace failure is not proof that the stopped device is the root cause.', ['traceroute', 'tracepath', 'tracert'], [read('traceroute <destination>', 'Observe L3 path')], ['network.routing.traceroute', 'network.routing.trace_evidence']),
  node('network.ops.route_drift', 'Route configuration drift and baseline', 'Baseline', 'Compare expected route destinations, next hops, interfaces and default routes with the current table to detect new, missing or changed paths.', ['Route Drift', 'baseline', 'configuration drift'], [read('show ip route', 'Capture current route table'), read('show running-config', 'Capture configured route context')], ['network.routing.route_baseline', 'network.routing.route_explain']),
  node('network.ops.route_change', 'Route change preview and blast radius', 'Change Safety', 'Route changes require topology, current route snapshot, impact analysis, preview, approval, apply, forward/return verification and record.', ['change preview', 'blast radius', 'approval'], [read('show ip route', 'Snapshot current routes'), change('ip route <destination> <mask> <next-hop-or-interface>', 'Preview a static route change', 'Use only validated destination, next hop and platform syntax.', 'HIGH', ['affected networks', 'downstream routers', 'forward and return paths'])], ['network.routing.static', 'network.ops.route_drift']),
  node('network.ops.visual_l3', 'VisualOps L3 investigation mapping', 'VisualOps', 'Spider may observe NO_ROUTE, DESTINATION_UNREACHABLE or TIMEOUT; Jellyfish classifies L3/L4 investigation and requests route/next-hop/path evidence; Whale holds topology state.', ['VisualOps', 'Spider', 'Jellyfish', 'Whale', 'investigation_hint'], [], ['network.routing.route_lookup', 'network.routing.traceroute'])
]

const incident = (id, title, symptoms, diagnosis, relatedIds, risk = 'READ_ONLY') => ({
  id, title, category: 'L3 Incident', type: 'INCIDENT', origin: 'expert_enhancement', status: 'REFERENCE_SCENARIO', symptoms, observed: symptoms,
  hypothesis: 'Evidence from interfaces, route tables, path and policy is required; a symptom is not a root cause.', diagnosis,
  verification: 'Verify source to next hop, source to destination, destination to source and service behavior; command exit code is not recovery.', rollback: 'Only approved changes may use a route snapshot and independent recovery path.', risk, executionAllowed: false, relatedIds, tags: [id, 'L3', title]
})

export const networkRoutingIncidents = [
  incident('INC-L3-001', 'No Route to Destination', 'Destination has no matching route', ['Confirm source/destination subnets, gateway, route table, default route and policy'], ['network.routing.route_lookup', 'network.routing.default']),
  incident('INC-L3-002', 'Missing Connected Route', 'Interface appears configured but a connected route is absent', ['Check IP/prefix, interface admin/operational state and line protocol'], ['network.routing.connected', 'network.routing.interface_state']),
  incident('INC-L3-003', 'Missing Static Route', 'Remote network lacks an expected static path', ['Distinguish dynamic/default paths, then validate destination, mask and next hop'], ['network.routing.static', 'network.routing.return_path']),
  incident('INC-L3-004', 'Wrong Static Route', 'A route exists but points to the wrong network or device', ['Explain matching entries and compare prefix, next hop, interface and baseline'], ['network.routing.static', 'network.routing.route_explain']),
  incident('INC-L3-005', 'Wrong Next Hop', 'Next hop is unreachable or not the intended adjacent device', ['Verify exit interface and next-hop reachability, then inspect neighbor and peer routes'], ['network.routing.next_hop', 'network.routing.interface_state']),
  incident('INC-L3-006', 'Interface Down', 'Router interface is administratively down or line protocol down', ['Check shutdown, link, peer, IP/prefix and connected route'], ['network.routing.interface_state', 'network.routing.connected']),
  incident('INC-L3-007', 'Missing Default Route', 'No specific match exists and no 0.0.0.0/0 is installed', ['Confirm whether the destination actually depends on a default route'], ['network.routing.default', 'network.routing.longest_prefix_match']),
  incident('INC-L3-008', 'Missing Return Route', 'Forward path reaches the destination but replies cannot return', ['Check source prefix route on the destination side, default/summary route, ACL and firewall'], ['network.routing.return_path', 'network.routing.asymmetric']),
  incident('INC-L3-009', 'Asymmetric Routing', 'Forward and reverse paths differ and trigger stateful policy or observation issues', ['Collect forward and reverse traces and route tables'], ['network.routing.asymmetric', 'network.routing.return_path']),
  incident('INC-L3-010', 'Routing Blackhole', 'A route exists but traffic is discarded', ['Check wrong route, null route, ACL/firewall, broken next hop and return path'], ['network.routing.blackhole', 'network.routing.policy'], 'HIGH'),
  incident('INC-L3-011', 'Routing Loop', 'Traceroute repeats hops or TTL expires', ['Identify repeating devices, compare route lookup and do not randomly edit routes'], ['network.routing.loop', 'network.routing.traceroute'], 'HIGH'),
  incident('INC-L3-012', 'Unexpected Route Selection', 'Multiple matching routes select an unexpected path', ['Apply longest prefix, preference, metric and platform rules'], ['network.routing.longest_prefix_match', 'network.routing.route_preference']),
  incident('INC-L3-013', 'Route Configuration Drift', 'Current destination/next-hop/interface/default differs from baseline', ['Capture current table, correlate change event, assess impact and do not auto-overwrite'], ['network.ops.route_drift', 'network.ops.route_change'], 'MEDIUM'),
  incident('INC-L3-014', 'Multi-hop Path Failure', 'The path breaks after an intermediate router or next hop', ['Ping next hop first, trace hop by hop, then inspect intermediate and destination return route'], ['network.routing.multi_hop', 'network.routing.trace_evidence']),
  incident('INC-L3-015', 'First Probe Resolution Delay', 'First ping is slower while later probes improve', ['Compare ARP/neighbor, MAC learning and repeat probes; do not directly blame routing'], ['network.routing.first_ping', 'network.arp.next_hop'])
]

export const networkRoutingRunbooks = [
  { id: 'RB-L3-ROUTING-001', title: 'Cross-subnet communication failure', type: 'RUNBOOK', category: 'L3 Routing Troubleshooting', origin: 'expert_enhancement', symptom: 'Source and destination are not in the same subnet and end-to-end communication fails', risk: 'LOW', executionAllowed: false, precheck: ['identify source IP', 'identify destination IP', 'calculate source and destination subnet', 'confirm business requires routed path'], steps: ['check source default gateway', 'check source interface', 'inspect routing table', 'identify selected route', 'verify next hop reachability', 'inspect downstream route', 'verify destination route', 'verify return route', 'check ACL/firewall', 'test with bounded ping/traceroute', 'verify end-to-end'], evidence: ['show ip interface brief', 'show ip route', 'ping <next-hop>', 'ping <destination>', 'traceroute <destination>'], verification: 'Verify source to next hop, source to destination, destination to source and application path.', rollback: 'No automatic mutation; route changes require a separate approved change plan.', relatedIds: ['network.routing.gateway', 'network.routing.route_lookup', 'network.routing.return_path'] },
  { id: 'RB-L3-STATIC-001', title: 'Static route troubleshooting', type: 'RUNBOOK', category: 'Static Route Troubleshooting', origin: 'expert_enhancement', risk: 'MEDIUM', executionAllowed: false, precheck: ['topology', 'source network', 'target network', 'router interfaces'], steps: ['verify destination network and mask', 'verify next hop reachability', 'verify exit interface', 'verify route active', 'verify downstream route', 'verify return route', 'compare route baseline', 'preview any proposed change', 'obtain approval before apply'], evidence: ['show ip interface brief', 'show ip route', 'ping <next-hop>', 'ping <destination>', 'traceroute <destination>'], verification: 'Forward and return path plus end-to-end service validation must agree.', rollback: 'Restore the route snapshot through the approved recovery path.', relatedIds: ['network.routing.static', 'network.routing.next_hop', 'network.ops.route_change'] },
  { id: 'RB-L3-ROUTE-002', title: 'Route Table Investigation', type: 'RUNBOOK', category: 'Route Explanation', origin: 'expert_enhancement', risk: 'LOW', executionAllowed: false, objective: 'Identify why destination traffic selects a given path.', steps: ['collect destination IP', 'collect source IP', 'determine source subnet', 'inspect routing table', 'identify all matching routes', 'select best match', 'identify next hop', 'verify next hop reachability', 'inspect outgoing interface', 'verify downstream route', 'verify return path', 'test end-to-end'], evidence: ['show ip route', 'show ip interface brief', 'ping <next-hop>', 'traceroute <destination>'], verification: 'Route explanation must state matching candidates, selected reason, next hop, exit interface and return-path status.', rollback: 'No mutation in this runbook.', relatedIds: ['network.routing.route_explain', 'network.routing.longest_prefix_match'] }
]

export const networkRoutingQuestions = [
  ['ROUTE_TABLE_ANALYSIS', 'What does a routing table describe?', 'Available paths to destination networks, including prefix, next hop, exit interface, source, metric, preference and state.', 'network.routing.routing_table'],
  ['STATIC_ROUTE_ANALYSIS', 'How should a static route be modeled?', 'Destination Network plus Next Hop and/or Exit Interface plus platform syntax, not only one CLI string.', 'network.routing.static'],
  ['DEFAULT_ROUTE', 'Does no specific static route always mean no connectivity?', 'No; a more specific route or 0.0.0.0/0 may still provide a path.', 'network.routing.default'],
  ['NEXT_HOP_ANALYSIS', 'Why ping the next hop before the destination?', 'It narrows the fault domain to the current router and adjacent path before testing the remote network.', 'network.routing.next_hop'],
  ['SUBNET_TO_ROUTE', 'What happens when source and destination are in different subnets?', 'The source uses its default gateway and enters L3 route lookup rather than relying on L2 switching alone.', 'network.routing.gateway'],
  ['LONGEST_PREFIX', 'How are multiple matching routes selected?', 'Usually longest-prefix match first, then device preference/administrative distance/metric rules.', 'network.routing.longest_prefix_match'],
  ['RETURN_PATH', 'Does A to B success prove B to A success?', 'No; verify the destination-to-source return route and policy.', 'network.routing.return_path'],
  ['ASYMMETRIC_ROUTING', 'What is asymmetric routing?', 'Forward and return paths differ, which may affect stateful firewalls, captures and latency.', 'network.routing.asymmetric'],
  ['ROUTING_LOOP', 'What does a repeating traceroute hop suggest?', 'A possible routing loop or policy issue; compare route tables and TTL evidence.', 'network.routing.loop'],
  ['BLACKHOLE', 'What can cause a route to exist while traffic is discarded?', 'Wrong route, null route, ACL/firewall, broken next hop or missing return path.', 'network.routing.blackhole'],
  ['TRACEROUTE_ANALYSIS', 'Does an incomplete traceroute prove a hop is the root cause?', 'No; it is path evidence that needs route, policy and end-to-end correlation.', 'network.routing.traceroute'],
  ['MULTI_ROUTER_TOPOLOGY', 'What does a multi-router path require?', 'Every hop needs an onward path, and the destination side needs a usable return path.', 'network.routing.multi_hop']
].map(([category, question, answer, relatedId], index) => ({ id: `Q-NET-L3-${String(index + 1).padStart(3, '0')}`, title: question, question, answer, category, type: 'QUESTION', origin: 'expert_enhancement', relatedIds: [relatedId], tags: [category, 'L3', 'routing'], risk: 'REFERENCE', executionAllowed: false }))

export const networkRoutingWrongAnswers = [
  ['L2_L3_CONFUSION', 'Connecting two switches automatically routes different IP subnets', 'Layer-2 connectivity is not Layer-3 routing; different subnets normally need L3 forwarding and a gateway.', 'network.routing.router_l3_device'],
  ['RETURN_PATH_ERROR', 'Only the route toward B is needed', 'A reverse route can come from a reverse route, default, summary or dynamic route, but it must exist and be verified.', 'network.routing.return_path'],
  ['DEFAULT_ROUTE_CONFUSION', 'No specific static route always means no communication', 'A more specific route or a default route may still match.', 'network.routing.default'],
  ['ROUTE_LOOKUP_ERROR', 'Matching routes are selected randomly', 'Devices normally apply longest-prefix match first and then route preference rules.', 'network.routing.longest_prefix_match'],
  ['INTERFACE_STATE_ERROR', 'An IP address proves the router interface can forward', 'Check existence, prefix, administrative state, operational state and line protocol.', 'network.routing.interface_state'],
  ['DEFAULT_ROUTE_OVERCLAIM', 'A default route guarantees access to every network', 'It is only a fallback candidate; next hop, policy, return path and application still need verification.', 'network.routing.default'],
  ['TRACE_ROOT_CAUSE_OVERCLAIM', 'An incomplete traceroute means the destination server is broken', 'The trace can be filtered or affected by policy, rate limiting or return path.', 'network.routing.traceroute'],
  ['FIRST_PING_OVERCLAIM', 'A slow first ping proves router failure', 'ARP/neighbor resolution, MAC learning or path setup can explain it; collect evidence.', 'network.routing.first_ping'],
  ['STATIC_ROUTE_RISK_UNDERSTATEMENT', 'Changing a static route is always low risk', 'Core or large networks can affect many networks and return paths; assess blast radius and approval.', 'network.ops.route_change']
].map(([wrong_reason_type, wrong_answer, correct_answer, relatedId], index) => ({ id: `WRONG-NET-L3-${String(index + 1).padStart(3, '0')}`, title: wrong_answer, type: 'WRONG_ANSWER', category: 'Wrong Answer Bank', origin: 'expert_enhancement', wrong_reason_type, misconception: wrong_answer, correction: correct_answer, relatedIds: [relatedId], tags: [wrong_reason_type, 'L3'], risk: 'REFERENCE', executionAllowed: false }))

export const networkRoutingRules = [
  { id: 'RULE-NET-ROUTE-DECISION', title: 'L3 Routing Decision Loop', kind: 'Agent Decision Rule', sequence: ['identify source', 'identify destination', 'calculate subnets', 'identify gateway', 'check interface', 'inspect route table', 'select best match', 'resolve next hop', 'check downstream router', 'verify destination route', 'verify return path', 'check policy', 'test end-to-end', 'record'], rule: 'Destination to Route Lookup to Next Hop/Exit Interface to Forwarding to Return Path to Verification.', relatedIds: ['network.routing.route_lookup', 'network.routing.return_path'], tags: ['L3', 'decision', 'evidence'], risk: 'REFERENCE', executionAllowed: false },
  { id: 'RULE-NET-ROUTE-PROBE', title: 'Next Best Evidence for Routing', kind: 'Troubleshooting Rule', sequence: ['source to gateway', 'gateway to next hop', 'next hop to destination', 'destination to source', 'application path'], rule: 'Use the smallest probe that can distinguish current hypotheses; do not repeatedly ping only from the original host.', relatedIds: ['network.routing.next_hop', 'network.routing.traceroute'], tags: ['Next Best Evidence', 'probe'], risk: 'REFERENCE', executionAllowed: false },
  { id: 'RULE-NET-ROUTE-SAFETY', title: 'Routing Change Safety', kind: 'Change Safety Rule', sequence: ['Discover', 'Current Route Snapshot', 'Impact Analysis', 'Preview', 'Approval', 'Apply', 'Route Verification', 'End-to-End Verification', 'Return Path Verification', 'Record'], rule: 'AI recommends and previews; it must not directly add or alter production routes.', relatedIds: ['network.ops.route_change', 'network.ops.route_drift'], tags: ['approval', 'blast radius', 'rollback'], risk: 'HIGH', executionAllowed: false },
  { id: 'RULE-NET-ROUTE-CORRELATION', title: 'Visual, topology and route correlation', kind: 'Correlation Rule', sequence: ['visual observation', 'layer hint', 'topology state', 'route evidence', 'path evidence', 'independent verification'], rule: 'NO_ROUTE, TIMEOUT and DESTINATION_UNREACHABLE are investigation hints, not confirmed root causes.', relatedIds: ['network.ops.visual_l3', 'network.routing.route_explain'], tags: ['VisualOps', 'Whale', 'Jellyfish'], risk: 'REFERENCE', executionAllowed: false }
]

const artifacts = [...networkRoutingNodes, ...networkRoutingIncidents, ...networkRoutingRunbooks, ...networkRoutingQuestions, ...networkRoutingWrongAnswers, ...networkRoutingRules]

export const networkRoutingEntries = artifacts.map(item => ({
  ...item, packId: 'network-routing', domain: 'network', platform: 'IP Routing', service: 'network-routing',
  source: 'Network L3 Routing Knowledge Pack', section: item.category || item.kind || 'L3 Routing', version: '1.0', provenance,
  content: item.content || [item.id, item.title, item.summary, item.symptoms, item.answer, item.correction, item.rule, ...(item.steps || []), ...(item.evidence || []), JSON.stringify(item, null, 2)].filter(Boolean).join('\n\n'),
  tags: item.tags || [item.category || item.kind || 'routing'], risk: item.risk || 'REFERENCE', executionAllowed: false
}))

export const networkRoutingSchemas = {
  RouteEntry: { fields: ['destination', 'prefix', 'netmask', 'next_hop', 'exit_interface', 'source', 'metric', 'administrative_distance', 'state'] },
  RoutePath: { fields: ['sourceNetwork', 'destinationNetwork', 'hops', 'verified'] },
  RouteBaseline: { fields: ['destinations', 'nextHops', 'interfaces', 'defaultRoute', 'source', 'capturedAt'] },
  TraceEvidence: { fields: ['source', 'destination', 'hops', 'observedStop', 'capturedAt'] }
}

function ipv4ToInteger(value) {
  const octets = String(value).trim().split('.')
  if (octets.length !== 4 || octets.some(octet => !/^\d+$/.test(octet) || Number(octet) > 255)) return null
  return octets.reduce((result, octet) => ((result * 256) + Number(octet)) >>> 0, 0) >>> 0
}

function parseCidr(route) {
  const rawDestination = route?.destination ?? route?.network
  if (typeof rawDestination !== 'string') return null
  const [address, rawPrefix] = rawDestination.split('/')
  const prefix = rawPrefix === undefined ? Number(route.prefix) : Number(rawPrefix)
  const integer = ipv4ToInteger(address)
  if (integer === null || !Number.isInteger(prefix) || prefix < 0 || prefix > 32) return null
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0
  return { integer, prefix, mask }
}

function routeMatches(destinationIp, route) {
  const target = ipv4ToInteger(destinationIp)
  const cidr = parseCidr(route)
  return target === null || !cidr ? null : { route, ...cidr, matches: (target & cidr.mask) === (cidr.integer & cidr.mask) }
}

function compareMatches(left, right) {
  return right.prefix - left.prefix || Number(left.route.administrativeDistance ?? left.route.distance ?? 0) - Number(right.route.administrativeDistance ?? right.route.distance ?? 0) || Number(left.route.metric ?? 0) - Number(right.route.metric ?? 0)
}

export function resolveRoute(destinationIp, routes = []) {
  const matches = routes.map(route => routeMatches(destinationIp, route)).filter(item => item?.matches).sort(compareMatches)
  return matches[0]?.route || null
}

export function explainRoute(destinationIp, routes = []) {
  const matchingRoutes = routes.map(route => routeMatches(destinationIp, route)).filter(item => item?.matches).sort(compareMatches).map(item => item.route)
  const selected = matchingRoutes[0] || null
  return { destinationIp, matchingRoutes, selected, reason: selected ? 'longest_prefix_match' : 'no_matching_route', nextHop: selected?.nextHop ?? selected?.next_hop ?? null, exitInterface: selected?.exitInterface ?? selected?.exit_interface ?? null }
}
