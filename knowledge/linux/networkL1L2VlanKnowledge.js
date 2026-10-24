// Reference-only L1/L2, switching, VLAN and trunk knowledge.
// No runtime, device API, command executor, or live telemetry is imported.
const provenance = {
  id: 'network-l1l2-vlan-reference-2026-09-24',
  kind: 'curated_course_and_engineering_pack',
  attachmentVerified: false,
  sourceFile: null,
  note: 'Packet Tracer material is lab/demo context; production values must be read from the target device.'
}

const read = (command, purpose, parameters = 'Read-only observation; record target, timestamp, scope, and device context.') => ({
  command, purpose, parameters, read_only: true, risk: 'READ_ONLY', risk_level: 'LOW',
  executionAllowed: false,
  verification: 'Correlate the output with the requested layer and an independent observation; command success is not recovery.'
})

const change = (command, purpose, parameters, riskLevel = 'MEDIUM', blastRadius = ['target interface', 'endpoint connectivity']) => ({
  command, purpose, parameters, read_only: false, risk: riskLevel, risk_level: riskLevel,
  executionAllowed: false, requires_preview: true, approval_required: true, blastRadius,
  verification: 'Snapshot before change, apply only after approval, verify affected VLANs and endpoints, and keep a rollback path.'
})

const node = (id, title, category, summary, tags, commands = [], relatedIds = [], extra = {}) => ({
  id, title, category, summary, tags, commands, relatedIds, type: 'ENGINEERING KNOWLEDGE',
  executionAllowed: false, risk: 'READ_ONLY', ...extra,
  content: `${title}\n\n${summary}\n\nLayer boundary: this node selects evidence and explains possible causes. It does not claim live device state or authorize a mutation.`
})

export const networkL1L2VlanNodes = [
  node('network.physical.signal', '信号、介质与链路边界', 'L1 Physical', '模拟/数字信号通过铜缆、光纤、收发器和连接器形成物理链路；链路存在不等于 IP、路由或应用正常。', ['signal', 'medium', 'link', 'L1'], [read('show interfaces status', '观察端口 link/status、速度和双工')], ['network.physical.link_state', 'network.physical.copper', 'network.physical.fiber']),
  node('network.physical.copper', '双绞线、UTP/STP 与 RJ45', 'L1 Physical', 'CAT5/CAT5e/CAT6、UTP/STP、RJ45、T568A/T568B 描述介质和端接；线材类别不保证每个环境都能协商目标速率。', ['twisted pair', 'UTP', 'STP', 'RJ45', 'T568A', 'T568B', 'CAT6'], [read('show interfaces <interface>', '观察协商速率、双工和物理错误')], ['network.physical.signal', 'network.physical.speed_duplex']),
  node('network.physical.fiber', '单模、多模与光模块', 'L1 Physical', '单模/多模、FC/ST/LC、波长、距离、Tx/Rx power 和收发器匹配共同影响光链路。', ['fiber', 'single mode', 'multi mode', 'FC', 'ST', 'LC', 'transceiver'], [read('show interfaces <interface>', '观察光口 link、错误和模块诊断')], ['network.physical.signal', 'network.physical.link_state']),
  node('network.physical.link_state', 'Link UP 不等于 Network UP', 'L1 Physical', 'Ethernet link UP 只说明物理/链路协商有结果；仍需分别验证 IP、Route、TCP/UDP、Port/Socket 和应用。', ['Link UP', 'Network UP', 'layer boundary'], [read('show interfaces status', '确认端口是否 up、速度和双工'), read('show interfaces <interface>', '确认错误计数、flap 和协商细节')], ['network.physical.speed_duplex', 'network.l2.mac_learning', 'network.ipv4.address']),
  node('network.physical.speed_duplex', '速率、双工与链路抖动', 'L1 Physical', '速度/双工不匹配、端口 flap 或协商异常可能表现为丢包、重传和高延迟，不能直接归因于应用。', ['speed', 'duplex', 'link flap', 'negotiation'], [read('show interfaces <interface>', '检查 speed/duplex、input/output errors 和 link transitions')], ['network.physical.link_state', 'network.physical.crc_errors']),
  node('network.physical.crc_errors', 'CRC/FCS 错误', 'L1 Physical', 'CRC/FCS 用于检测帧完整性；错误增长需要结合线缆、收发器、端口、双工和邻端统计定位。', ['CRC', 'FCS', 'errors', 'frame integrity'], [read('show interfaces <interface>', '读取 CRC、FCS、input errors 和时间变化')], ['network.physical.fiber', 'network.physical.copper', 'network.l2.ethernet_frame']),
  node('network.l2.ethernet_frame', 'Ethernet Frame 结构', 'L2 Data Link', '帧由 Destination MAC、Source MAC、EtherType、Payload 和 FCS 组成；EtherType 0800 表示 IPv4，0806 表示 ARP。', ['Ethernet', 'frame', 'EtherType', '0800', '0806'], [read('show interfaces <interface>', '关联帧错误计数与端口观察')], ['network.l2.fcs_crc', 'network.arp.next_hop']),
  node('network.l2.fcs_crc', 'FCS/CRC 完整性检查', 'L2 Data Link', 'FCS/CRC 能提示帧在传输中损坏，但不能独立证明具体线缆、端口或设备是根因。', ['FCS', 'CRC', 'frame'], [read('show interfaces <interface>', '检查错误计数和增长趋势')], ['network.physical.crc_errors', 'network.l2.ethernet_frame']),
  node('network.l2.switch_forwarding', '交换机学习、查表与转发', 'L2 Switching', '交换机先学习源 MAC，再查找目标 MAC；已知单播定向转发，未知单播或广播通常只在相关 VLAN 内泛洪。', ['switch', 'forwarding', 'learning', 'flooding'], [read('show mac address-table', '验证 MAC 到 VLAN/端口的学习结果')], ['network.l2.mac_learning', 'network.l2.unknown_unicast', 'network.vlan.broadcast_domain']),
  node('network.l2.mac_learning', 'MAC 地址学习', 'L2 Switching', '交换机把收到帧的源 MAC 关联到观察到的接口和 VLAN；MAC 不是永远固定在某个物理端口的不可变身份。', ['MAC', 'learning', 'interface', 'VLAN'], [read('show mac address-table', '读取当前 MAC、VLAN、接口、类型和 aging')], ['network.l2.mac_table', 'network.l2.mac_flapping']),
  node('network.l2.mac_table', 'MAC Address Table 数据模型', 'L2 Switching', 'MAC 表应至少保留 mac、vlan、interface、firstSeen、lastSeen、age 和 source，便于关联端口、VLAN 与端点。', ['MAC table', 'vlan', 'interface', 'firstSeen', 'lastSeen'], [read('show mac address-table', '采集 MAC/VLAN/接口快照')], ['network.l2.mac_learning', 'network.vlan.id_membership']),
  node('network.l2.mac_aging', 'MAC 表 Aging 参数化', 'L2 Switching', '课程中的 5 分钟是 source-course 示例，不是固定事实；设备的 aging timer 必须从实际配置读取。', ['MAC aging', 'configurable', 'source_course_example'], [read('show running-config', '读取真实 MAC aging 配置'), read('show mac address-table', '观察条目 age 和刷新情况')], ['network.l2.mac_table']),
  node('network.l2.mac_flapping', 'MAC Flapping 与端口移动', 'L2 Switching', '同一 MAC 在短时间内出现在多个端口，可能表示环路、双归属、拓扑变化、虚拟化迁移或配置错误；不能随机 shutdown 端口。', ['MAC Flapping', 'MAC_MOVED', 'loop', 'topology'], [read('show mac address-table', '比较同一 MAC 的接口、VLAN 和时间'), read('show interfaces trunk', '确认是否沿 trunk 移动')], ['network.stp.loop_risk', 'network.l2.mac_learning']),
  node('network.l2.broadcast_domain', 'VLAN 与广播域', 'L2 Data Link', 'VLAN 是逻辑二层分段和广播域；同一 VLAN 内泛洪，跨 VLAN 默认需要三层转发。', ['VLAN', 'broadcast domain', 'segmentation'], [read('show vlan brief', '检查 VLAN 存在、状态和端口归属')], ['network.vlan.concept', 'network.l3.inter_vlan_routing']),
  node('network.l2.unknown_unicast', 'Unknown Unicast 与 Flooding', 'L2 Switching', 'MAC 表没有目标地址时，交换机可能在相关 VLAN 内向除源端口外泛洪；这不是“交换机收到数据一定广播”。', ['unknown unicast', 'flooding', 'broadcast'], [read('show mac address-table', '确认目标 MAC 是否已学习')], ['network.l2.switch_forwarding', 'network.l2.mac_aging']),
  node('network.l2.broadcast_storm', '广播风暴与未知单播泛洪', 'L2 Incident', '广播量或未知单播异常升高可能源于环路、错误拓扑、MAC 学习缺失或设备故障，需先收集端口和 STP 证据。', ['broadcast storm', 'unknown unicast', 'loop'], [read('show interfaces <interface>', '观察广播、丢包和错误计数'), read('show mac address-table', '观察学习规模和移动')], ['network.stp.loop_risk', 'network.l2.mac_flapping']),
  node('network.vlan.concept', 'VLAN 是二层逻辑分段', 'VLAN', 'VLAN ID 将交换端口划入逻辑广播域；VLAN 隔离不等于完整安全边界，路由器、L3 Switch 或防火墙仍可提供跨 VLAN 通信。', ['VLAN', 'broadcast domain', 'segmentation', 'security boundary'], [read('show vlan brief', '核对 VLAN ID、名称、状态和端口')], ['network.vlan.id_membership', 'network.l3.inter_vlan_routing']),
  node('network.vlan.id_membership', 'VLAN ID 与端口成员关系', 'VLAN', 'VLAN 需要在目标交换机存在并有正确的端口成员；端口、VLAN、MAC 三者应一起观察。', ['VLAN ID', 'membership', 'port'], [read('show vlan brief', '查看 VLAN 与 access 端口成员')], ['network.vlan.access_port', 'network.l2.mac_table']),
  node('network.vlan.access_port', 'Access Port 与单 VLAN 端点', 'VLAN', 'Access 端口通常承载一个用户或数据 VLAN；实际角色必须以配置为准，不能从线缆外观推断。', ['Access', 'access port', 'endpoint', 'VLAN membership'], [read('show interfaces status', '检查端口状态、模式和 VLAN'), read('show vlan brief', '核对 access VLAN'), change('switchport mode access\nswitchport access vlan <id>', '变更端点二层归属', '替换为经批准的接口和 VLAN；先记录当前配置和影响范围。', 'MEDIUM', ['target endpoint', 'access port', 'VLAN connectivity'])], ['network.vlan.id_membership', 'network.trunk.allowed_vlans']),
  node('network.vlan.trunk_port', 'Trunk 作为多 VLAN 逻辑承载', 'VLAN', 'Trunk 是一条物理链路上的多 VLAN 逻辑传输，不是把多根线合成一根线；需结合 tagging、allowed VLAN 和 native VLAN。', ['Trunk', 'multi-VLAN', 'logical link'], [read('show interfaces trunk', '查看 trunk operational state 与传输 VLAN'), change('switchport mode trunk', '把接口切换为 trunk', '两端配置必须成对核对；变更前确认下游设备和受影响 VLAN。', 'HIGH', ['all VLANs on link', 'downstream switches', 'multiple hosts'])], ['network.vlan.8021q', 'network.trunk.allowed_vlans', 'network.vlan.native_vlan']),
  node('network.vlan.8021q', '802.1Q VLAN Tagging', 'VLAN', '802.1Q 在 Ethernet Frame 中携带 VLAN tag，使一条 trunk 能承载多个 VLAN；Tagging 与端口模式、封装和两端配置共同决定结果。', ['802.1Q', 'tagging', 'VLAN tag', 'Ethernet frame'], [read('show interfaces trunk', '验证封装、native VLAN 和 allowed VLAN')], ['network.vlan.trunk_port', 'network.trunk.allowed_vlans']),
  node('network.trunk.allowed_vlans', 'Allowed VLANs 传输范围', 'Trunk', 'Trunk UP 不代表所有 VLAN 正常；allowed VLAN 列表缺少目标 VLAN 时，跨交换机同 VLAN 仍会中断。', ['Allowed VLAN', 'allowed VLANs', 'trunk'], [read('show interfaces trunk', '核对 allowed、active、forwarding VLAN'), change('switchport trunk allowed vlan <list>', '调整 trunk 允许的 VLAN', '只使用明确的目标 VLAN 列表；评估下游交换机与业务影响。', 'HIGH', ['all listed VLANs', 'downstream switches', 'multiple endpoints'])], ['network.vlan.trunk_port', 'network.vlan.mismatch']),
  node('network.vlan.native_vlan', 'Native VLAN 与双端一致性', 'Trunk', 'Native VLAN 处理未打标签的 trunk 流量；两端不一致会造成告警、错误转发或安全边界误判，必须读取真实配置。', ['native VLAN', '802.1Q', 'mismatch'], [read('show interfaces trunk', '比较两端 native VLAN'), read('show running-config', '核对实际接口配置')], ['network.vlan.mismatch', 'network.trunk.allowed_vlans']),
  node('network.vlan.mismatch', 'VLAN、Trunk 与端口模式不一致', 'VLAN Incident', 'VLAN 不通可能来自端口模式、VLAN 缺失、allowed VLAN、native VLAN、两端配置或 STP 状态，而不是单一“网络故障”。', ['VLAN mismatch', 'trunk failure', 'configuration drift'], [read('show vlan brief', '核对本地 VLAN 与 access assignment'), read('show interfaces trunk', '核对 trunk 与 VLAN transport'), read('show mac address-table', '核对 MAC learning')], ['network.vlan.access_port', 'network.trunk.allowed_vlans', 'network.vlan.native_vlan']),
  node('network.switch.show_vlan', 'Command Card: show vlan brief', 'Command Card', '用于检查 VLAN 是否存在、状态以及 access 端口成员。', ['show vlan brief', 'VLAN membership'], [read('show vlan brief', 'VLAN / access assignment')], ['network.vlan.id_membership']),
  node('network.switch.show_mac', 'Command Card: show mac address-table', 'Command Card', '用于检查 MAC 学习、VLAN、接口、移动和缺失条目。', ['show mac address-table', 'MAC learning'], [read('show mac address-table', 'MAC learning')], ['network.l2.mac_table', 'network.l2.mac_flapping']),
  node('network.switch.show_trunk', 'Command Card: show interfaces trunk', 'Command Card', '用于检查 trunk 状态、802.1Q、native VLAN、allowed VLAN 和 forwarding VLAN。', ['show interfaces trunk', 'trunk'], [read('show interfaces trunk', 'trunk state / VLAN transport')], ['network.vlan.8021q', 'network.trunk.allowed_vlans']),
  node('network.switch.show_status', 'Command Card: show interfaces status', 'Command Card', '用于检查物理/逻辑端口状态、速度、双工、模式和 VLAN。', ['show interfaces status', 'port state'], [read('show interfaces status', 'physical/logical port state')], ['network.physical.link_state', 'network.vlan.access_port']),
  node('network.l3.inter_vlan_routing', 'Inter-VLAN Routing', 'L3 Network', '不同 VLAN 默认不能直接二层互通；若业务要求通信，需要 Default Gateway、Router/L3 Switch、SVI、Route 和 ACL/Firewall。', ['Inter-VLAN Routing', 'gateway', 'L3', 'SVI'], [read('show ip route', '检查三层路由'), read('show interfaces <interface>', '检查 SVI/网关状态')], ['network.l3.svi_gateway', 'network.vlan.concept', 'network.ipv4.subnet']),
  node('network.l3.svi_gateway', 'SVI 与 Default Gateway', 'L3 Network', 'SVI 或路由器子接口为 VLAN 提供三层网关；网关可达不等于 ACL、应用和返回路径正确。', ['SVI', 'default gateway', 'router-on-a-stick'], [read('show ip route', '检查 VLAN 网段路由'), read('show interfaces <interface>', '检查 SVI 状态和地址')], ['network.l3.inter_vlan_routing', 'network.firewall.stateful']),
  node('network.stp.loop_risk', 'STP 与二层环路风险', 'STP', '多交换机和冗余链路可能产生 L2 loop；STP、拓扑变化、广播风暴和 MAC flapping 应关联分析。', ['STP', 'loop', 'broadcast storm', 'topology change'], [read('show interfaces <interface>', '观察拓扑变化和端口计数')], ['network.l2.mac_flapping', 'network.l2.broadcast_storm']),
  node('network.ops.layer_probe', '从现象选择最小证据路径', 'Agent Decision', 'Link Down 查 L1/L2；MAC 学习或 VLAN mismatch 查 L2；No Route 查 L3；Connection Refused 查 L4；HTTP 502 查 L7/Gateway。层级映射不是根因确认。', ['layer probe', 'Next Best Evidence', 'Evidence First'], [read('show interfaces status', '从物理状态开始'), read('show vlan brief', '随后检查 VLAN'), read('show mac address-table', '再检查 MAC learning')], ['network.physical.link_state', 'network.l2.mac_learning', 'network.l3.inter_vlan_routing']),
  node('network.ops.change_preview', 'Network Change Preview 与 Blast Radius', 'Change Safety', 'Access VLAN、Trunk、Allowed VLAN、Native VLAN 修改必须先 Discover、Snapshot、Preview、评估影响、审批、Apply、Verify、Record。', ['change preview', 'blast radius', 'approval'], [read('show running-config', '获取当前有效配置快照'), change('switchport trunk allowed vlan <list>', '示例：预览 trunk 允许 VLAN 变更', '仅作为已批准变更的占位命令，不接受未验证目标。', 'HIGH', ['multiple VLANs', 'downstream switches', 'multiple hosts'])], ['network.trunk.allowed_vlans', 'network.ops.config_drift']),
  node('network.ops.config_drift', 'VLAN/Trunk 配置漂移', 'Baseline', '将接口、VLAN assignment、trunk、allowed VLAN、native VLAN、MAC entries 和 expected links 与基线比较，检测意外变更。', ['configuration drift', 'baseline', 'VLAN Drift', 'Trunk Drift'], [read('show running-config', '读取有效配置'), read('show vlan brief', '比较 VLAN assignment'), read('show interfaces trunk', '比较 trunk baseline')], ['network.ops.change_preview', 'network.vlan.mismatch']),
  node('network.ops.topology_state', 'Network Digital Twin 拓扑状态', 'Digital Twin', 'Whale 可用设备、接口、链路、VLAN、MAC、IP、Route、Neighbor、Port、Service 和 Flow 描述环境状态；观察不等于实时遥测。', ['Network Digital Twin', 'topology', 'device', 'link'], [], ['network.ops.config_drift', 'network.l2.mac_table']),
  node('network.visual.l1l2_mapping', 'VisualOps 的 L1/L2 映射', 'VisualOps', 'Spider 识别 PORT DOWN、TRUNK DOWN、VLAN ERROR、MAC FLAPPING、BROADCAST STORM 时只提交观察；Jellyfish 分类层级并请求证据，Whale 保持拓扑状态。', ['VisualOps', 'Spider', 'Jellyfish', 'Whale'], [], ['network.ops.layer_probe', 'network.ops.topology_state'])
]

const incident = (id, title, category, symptoms, diagnosis, relatedIds, risk = 'READ_ONLY', tags = []) => ({
  id, title, category, type: 'INCIDENT', origin: 'expert_enhancement', status: 'REFERENCE_SCENARIO', symptoms, observed: symptoms,
  hypothesis: '待设备证据确认；症状不是根因。', diagnosis, verification: '从独立设备/端点观察验证恢复，不以命令退出码代替业务验证。', rollback: '仅对已审批变更使用预先记录的配置和独立恢复入口。',
  risk, executionAllowed: false, relatedIds, tags: [id, ...tags]
})

export const networkL1L2VlanIncidents = [
  incident('INC-L1-001', 'Physical Link Down', 'L1 Physical', '端口 down、无 carrier 或端点无法建立链路', ['检查接口状态、线缆/收发器、邻端端口、速率双工和错误计数'], ['network.physical.link_state', 'network.physical.copper']),
  incident('INC-L1-002', 'Link Flapping', 'L1 Physical', '端口反复 UP/DOWN', ['比较 link transition 时间、CRC、收发器、NIC、驱动和邻端日志'], ['network.physical.speed_duplex', 'network.physical.crc_errors']),
  incident('INC-L1-003', 'CRC/FCS Errors', 'L1 Physical', 'CRC/FCS 或 input errors 持续增长', ['先确认计数增长趋势，再隔离线缆、模块、端口和双工假设'], ['network.physical.crc_errors', 'network.l2.fcs_crc']),
  incident('INC-L2-001', 'MAC Learning Failure', 'L2 Switching', '端点发送流量但 MAC 表没有预期条目', ['核对端口 up、VLAN membership、MAC aging、源流量和是否经过 trunk'], ['network.l2.mac_learning', 'network.l2.mac_table']),
  incident('INC-L2-002', 'MAC Flapping', 'L2 Switching', '同一 MAC 在短时间内出现在多个端口', ['比较 MAC、VLAN、接口和时间；检查双归属、环路、虚拟化迁移和 STP'], ['network.l2.mac_flapping', 'network.stp.loop_risk'], 'MEDIUM', ['MAC_FLAPPING']),
  incident('INC-L2-003', 'Unknown Unicast Flood', 'L2 Switching', '未知单播泛洪、MAC 表缺失或广播量异常', ['核对 MAC learning、aging、VLAN 边界和拓扑变化'], ['network.l2.unknown_unicast', 'network.l2.mac_aging']),
  incident('INC-L2-004', 'Broadcast Storm', 'L2 Switching', '广播/未知单播流量异常升高', ['检查端口计数、MAC flapping、STP 状态和最近拓扑变更'], ['network.l2.broadcast_storm', 'network.stp.loop_risk'], 'HIGH'),
  incident('INC-VLAN-001', 'Wrong Access VLAN', 'VLAN', '同交换机端点处于错误 VLAN', ['核对 show vlan brief、show interfaces status、端点 IP/掩码和基线'], ['network.vlan.access_port', 'network.vlan.id_membership'], 'MEDIUM'),
  incident('INC-VLAN-002', 'VLAN Missing', 'VLAN', '目标 VLAN 在交换机不存在或 inactive', ['检查 VLAN 数据库、端口成员和变更记录'], ['network.vlan.concept', 'network.vlan.id_membership'], 'MEDIUM'),
  incident('INC-VLAN-003', 'VLAN Connectivity Failure', 'VLAN', '同 VLAN 主机或跨交换机同 VLAN 不通', ['按 L1→Access→VLAN→Trunk→Allowed VLAN→MAC→Host IP 最小路径排查'], ['network.ops.layer_probe', 'network.vlan.mismatch']),
  incident('INC-TRUNK-001', 'Trunk Down', 'Trunk', '两交换机物理链路存在但 trunk 未 operational', ['检查物理状态、端口模式、封装、两端配置与 STP'], ['network.vlan.trunk_port', 'network.switch.show_trunk'], 'HIGH'),
  incident('INC-TRUNK-002', 'Allowed VLAN Missing', 'Trunk', 'trunk UP 但目标 VLAN 无法跨链路传输', ['比较 allowed、active、forwarding VLAN 和两端 VLAN existence'], ['network.trunk.allowed_vlans', 'network.vlan.8021q'], 'HIGH'),
  incident('INC-TRUNK-003', 'Native VLAN Mismatch', 'Trunk', '两端 native VLAN 不一致或出现告警', ['比较两端 native VLAN、未打标签流量和配置漂移'], ['network.vlan.native_vlan', 'network.vlan.mismatch'], 'HIGH'),
  incident('INC-TRUNK-004', 'Trunk Configuration Drift', 'Trunk', '当前 trunk、allowed VLAN 或 mode 偏离基线', ['读取 effective config、比较 baseline、关联最近变更和受影响端点'], ['network.ops.config_drift', 'network.ops.change_preview'], 'HIGH'),
  incident('INC-VLAN-004', 'Inter-VLAN Routing Failure', 'L3 Network', '业务要求跨 VLAN 通信但 gateway/SVI/route/ACL 不满足', ['确认业务确实要求跨 VLAN，再查 gateway、SVI、route、ACL/firewall 和返回路径'], ['network.l3.inter_vlan_routing', 'network.l3.svi_gateway']),
  incident('INC-STP-001', 'Potential Layer-2 Loop', 'STP', 'MAC flapping、广播风暴或拓扑频繁变化提示潜在二层环路', ['保留证据，检查 STP、链路冗余和变更，不随机 shutdown 接口'], ['network.stp.loop_risk', 'network.l2.mac_flapping'], 'HIGH')
]

export const networkL1L2VlanRunbooks = [
  { id: 'RB-L2-VLAN-001', title: 'VLAN 主机连通性故障', type: 'RUNBOOK', category: 'VLAN Troubleshooting', origin: 'expert_enhancement', symptom: '同 VLAN 或跨交换机同 VLAN 端点不通', scope: ['endpoint', 'access port', 'VLAN', 'MAC', 'trunk', 'gateway'], precheck: ['确认目标、同 VLAN/跨 VLAN 需求、影响范围和时间线'], steps: ['verify endpoint link', 'verify endpoint IP and subnet', 'verify switch port', 'verify VLAN membership', 'verify MAC learning', 'verify trunk when cross-switch', 'verify allowed VLANs when cross-switch', 'verify gateway and ACL when cross-VLAN'], evidence: ['show interfaces status', 'show vlan brief', 'show mac address-table', 'show interfaces trunk', 'show ip route'], risk: 'MEDIUM', remediation: '只推荐经过审批的最小变更，不自动改端口或 trunk。', verification: '同 VLAN、跨交换机和必要的跨 VLAN 业务分别验证。', rollback: '使用变更前快照和独立管理入口恢复。', executionAllowed: false, relatedIds: ['network.vlan.access_port', 'network.trunk.allowed_vlans', 'network.l3.inter_vlan_routing'] },
  { id: 'RB-L2-TRUNK-001', title: '交换机 Trunk 连接异常', type: 'RUNBOOK', category: 'Trunk Troubleshooting', origin: 'expert_enhancement', symptom: 'trunk down 或目标 VLAN 无法跨交换机', scope: ['physical link', 'mode', 'encapsulation', 'VLAN', 'allowed VLAN', 'native VLAN', 'STP'], precheck: ['确认两端设备、接口、业务 VLAN 和是否存在下游设备'], steps: ['verify physical link', 'verify port mode', 'verify trunk operational state', 'verify VLAN exists', 'verify allowed VLANs', 'verify native VLAN', 'verify both sides', 'verify MAC learning', 'test same VLAN endpoint', 'compare configuration drift'], evidence: ['show interfaces status', 'show interfaces trunk', 'show vlan brief', 'show mac address-table'], risk: 'HIGH', remediation: '只提出双端一致性变更预览，禁止未经审批重新配置两端。', verification: '目标 VLAN forwarding、MAC learning、跨交换机端点和业务路径均恢复。', rollback: '恢复已保存的两端配置并重新验证。', executionAllowed: false, relatedIds: ['network.vlan.trunk_port', 'network.trunk.allowed_vlans', 'network.vlan.native_vlan'] },
  { id: 'RB-L2-MAC-001', title: 'MAC Learning Investigation', type: 'RUNBOOK', category: 'MAC Troubleshooting', origin: 'expert_enhancement', symptom: 'MAC 缺失、未知单播泛洪或端点未被学习', scope: ['source traffic', 'VLAN', 'interface', 'aging', 'trunk'], precheck: ['确认 MAC、VLAN、端口、时间和观察来源'], steps: ['verify interface state', 'verify VLAN membership', 'verify source traffic', 'verify MAC table entry', 'verify aging configuration', 'verify trunk path when remote', 'compare firstSeen and lastSeen'], evidence: ['show interfaces status', 'show vlan brief', 'show mac address-table', 'show running-config'], risk: 'LOW', remediation: '先区分无流量、VLAN 错误、aging、trunk 丢失和设备故障。', verification: '重新产生受控流量后 MAC 在正确 VLAN/接口稳定学习。', rollback: '无自动修复；保留观察快照。', executionAllowed: false, relatedIds: ['network.l2.mac_learning', 'network.l2.mac_aging'] },
  { id: 'RB-L2-FLAPPING-001', title: 'MAC Flapping Investigation', type: 'RUNBOOK', category: 'L2 Anomaly', origin: 'expert_enhancement', symptom: '同一 MAC 在多个端口之间移动', scope: ['MAC', 'VLAN', 'ports', 'trunk', 'STP', 'topology'], precheck: ['确认移动时间窗口、端口列表、VLAN 和最近变更'], steps: ['capture MAC movement timeline', 'verify VLAN and interfaces', 'check dual connection and virtualization movement', 'check trunk path', 'check STP and topology changes', 'correlate broadcast and CRC counters', 'recommend least-risk isolation only after approval'], evidence: ['show mac address-table', 'show interfaces trunk', 'show interfaces <interface>', 'show running-config'], risk: 'HIGH', remediation: '不随机 shutdown 接口；先形成拓扑假设和影响评估。', verification: 'MAC 在预期端口稳定，广播/错误计数回归基线且业务验证通过。', rollback: '任何隔离变更必须有人工批准和独立恢复入口。', executionAllowed: false, relatedIds: ['network.l2.mac_flapping', 'network.stp.loop_risk'] }
]

export const networkL1L2VlanQuestions = [
  ['OSI_LAYER_IDENTIFICATION', 'Link UP 能证明 IP 网络和应用正常吗？', '不能；还需验证 IP、Route、TCP/UDP、Port/Socket 和应用。', 'L1/L2', 'network.physical.link_state'],
  ['MAC_TABLE_ANALYSIS', '交换机收到数据一定广播吗？', '不是；已知单播按 MAC 表定向转发，未知单播/广播可能在相关 VLAN 内泛洪。', 'L2', 'network.l2.switch_forwarding'],
  ['VLAN_ANALYSIS', 'VLAN 是否等于完整安全隔离？', '不是；VLAN 是二层分段，Router/L3 Switch/Firewall 可以提供跨 VLAN 通信。', 'VLAN', 'network.vlan.concept'],
  ['TRUNK_ANALYSIS', 'Trunk 为什么能承载多个 VLAN？', '通过 VLAN tagging（典型为 802.1Q）和两端 trunk 配置承载多个逻辑 VLAN。', 'Trunk', 'network.vlan.8021q'],
  ['TRUNK_ANALYSIS', 'Trunk UP 是否代表所有 VLAN 正常？', '不是；必须检查 VLAN existence、allowed VLAN、native VLAN、STP 和 MAC learning。', 'Trunk', 'network.trunk.allowed_vlans'],
  ['INCIDENT_ANALYSIS', 'MAC 在多个端口之间变化说明什么？', '可能是环路、双归属、拓扑变化、虚拟化迁移或配置错误，需要继续收集证据。', 'L2 anomaly', 'network.l2.mac_flapping'],
  ['NETWORK_TOPOLOGY', '不同 VLAN 的机器为什么不能通信？', '如果业务要求跨 VLAN，需要检查 Default Gateway、SVI/L3 routing、Route、ACL/Firewall；不是永远不能通信。', 'L3', 'network.l3.inter_vlan_routing']
].map(([category, question, answer, layer, relatedId], index) => ({ id: `Q-NET-L1L2-${String(index + 1).padStart(3, '0')}`, title: question, question, answer, category, layer, type: 'QUESTION', origin: 'expert_enhancement', relatedIds: [relatedId], tags: [category, layer], risk: 'REFERENCE', executionAllowed: false }))

export const networkL1L2VlanWrongAnswers = [
  ['SWITCH_FORWARDING_MISUNDERSTANDING', '交换机收到数据一定广播', '已知单播通常按 MAC table 定向转发；未知单播和广播才可能在相关 VLAN 内泛洪。', 'network.l2.switch_forwarding'],
  ['MAC_IDENTITY_CONFUSION', 'MAC 永远固定在某个交换机端口', 'MAC learning 映射的是某时刻观察到的 VLAN/接口，拓扑或端点变化时可能移动。', 'network.l2.mac_learning'],
  ['LAYER_CONFUSION', 'Link UP 就等于网络正常', 'Link UP 只覆盖物理/链路边界，不证明 IP、Route、TCP 或应用。', 'network.physical.link_state'],
  ['VLAN_SECURITY_OVERSIMPLIFICATION', '不同 VLAN 永远不能通信', '不同 VLAN 默认二层隔离，但可以通过 L3 Gateway、ACL 和 Firewall 通信。', 'network.l3.inter_vlan_routing'],
  ['TRUNK_MISUNDERSTANDING', 'Trunk 是把多根网线合成一根线', 'Trunk 是承载多个 VLAN 的逻辑链路，通常依赖 802.1Q tagging。', 'network.vlan.trunk_port'],
  ['TRUNK_STATE_OVERCLAIM', 'Trunk UP 就代表所有 VLAN 都正常', '仍需检查 allowed VLAN、native VLAN、VLAN existence、STP 和 MAC learning。', 'network.trunk.allowed_vlans'],
  ['MAC_FLAPPING_NORMALIZATION', 'MAC flapping 只是正常 MAC 更新', '短时间多端口移动是异常线索，需检查 loop、dual connection、STP 和虚拟化移动。', 'network.l2.mac_flapping'],
  ['LAYER_CONFUSION', 'ping 不通就是 IP 配错', 'ping failure 可能来自 L1/L2/L3/L4、ACL/Firewall 或应用路径，先按最小证据路径分层。', 'network.ops.layer_probe']
].map(([wrong_reason_type, wrong_answer, correct_answer, relatedId], index) => ({ id: `WRONG-NET-L1L2-${String(index + 1).padStart(3, '0')}`, title: wrong_answer, type: 'WRONG_ANSWER', category: 'Wrong Answer Bank', origin: 'expert_enhancement', wrong_reason_type, misconception: wrong_answer, correction: correct_answer, relatedIds: [relatedId], tags: [wrong_reason_type], risk: 'REFERENCE', executionAllowed: false }))

export const networkL1L2VlanRules = [
  { id: 'RULE-NET-LAYER-PROBE', title: '从现象选择最小证据层级', kind: 'Agent Decision Rule', sequence: ['identify symptom layer', 'select least-risk evidence', 'record what evidence proves', 'form hypotheses', 'recommend next probe', 'verify independently'], rule: 'Layer mapping is investigation guidance, not root cause confirmation.', relatedIds: ['network.ops.layer_probe'], tags: ['layer', 'evidence', 'Next Best Evidence'], risk: 'REFERENCE', executionAllowed: false },
  { id: 'RULE-NET-VLAN-PATH', title: 'VLAN 连通性证据路径', kind: 'Troubleshooting Rule', sequence: ['endpoint link', 'access port', 'VLAN membership', 'MAC learning', 'trunk when cross-switch', 'allowed VLAN', 'gateway when cross-VLAN', 'ACL/firewall'], rule: 'Do not diagnose a later layer before a required earlier path is evidenced.', relatedIds: ['network.vlan.access_port', 'network.trunk.allowed_vlans', 'network.l3.inter_vlan_routing'], tags: ['VLAN', 'troubleshooting'], risk: 'REFERENCE', executionAllowed: false },
  { id: 'RULE-NET-CHANGE-SAFETY', title: '交换网络变更安全流程', kind: 'Change Safety Rule', sequence: ['Discover', 'Snapshot', 'Preview', 'Blast Radius', 'Approval', 'Apply', 'Verify', 'Record', 'Baseline Update'], rule: 'AI may recommend and preview; it must not directly mutate a switch or randomly isolate a port.', relatedIds: ['network.ops.change_preview', 'network.ops.config_drift'], tags: ['approval', 'blast radius', 'baseline'], risk: 'HIGH', executionAllowed: false },
  { id: 'RULE-NET-CORRELATION', title: '网络变更与应用影响关联', kind: 'Correlation Rule', sequence: ['change event', 'network event', 'transport symptom', 'application impact', 'recovery event', 'independent verification'], rule: 'Temporal correlation is not confirmed root cause; retain competing hypotheses until verified.', relatedIds: ['network.ops.change_preview', 'network.l3.inter_vlan_routing'], tags: ['correlation', 'timeline', 'verification'], risk: 'REFERENCE', executionAllowed: false }
]

const artifacts = [...networkL1L2VlanNodes, ...networkL1L2VlanIncidents, ...networkL1L2VlanRunbooks, ...networkL1L2VlanQuestions, ...networkL1L2VlanWrongAnswers, ...networkL1L2VlanRules]

export const networkL1L2VlanEntries = artifacts.map(item => ({
  ...item,
  packId: 'network-l1l2-vlan',
  domain: 'network',
  platform: 'Switching / VLAN',
  service: 'network-l1l2-vlan',
  source: 'Network L1/L2 + Switching + VLAN/Trunk Knowledge Pack',
  section: item.category || item.kind || 'Network',
  version: '1.0',
  provenance,
  content: item.content || [item.id, item.title, item.summary, item.symptoms, item.answer, item.correction, item.rule, ...(item.steps || []), ...(item.evidence || []), JSON.stringify(item, null, 2)].filter(Boolean).join('\n\n'),
  tags: item.tags || [item.category || item.kind || 'network'],
  risk: item.risk || 'REFERENCE',
  executionAllowed: false
}))

export const networkDigitalTwinSchema = {
  NetworkNode: { fields: ['id', 'type', 'name'] },
  NetworkLink: { fields: ['id', 'source', 'target', 'sourcePort', 'targetPort', 'status', 'vlans', 'mode', 'allowedVlans'] },
  MacObservation: { fields: ['mac', 'vlan', 'port', 'first_seen', 'last_seen', 'movement_count', 'stable'] },
  SwitchBaseline: { fields: ['interfaces', 'vlanAssignments', 'trunks', 'allowedVlans', 'nativeVlans', 'macEntries', 'expectedLinks'] }
}
