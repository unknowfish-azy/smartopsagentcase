/**
 * virtualOpsScene — 虚拟运维场景 / 操作失误后果预测（纯函数，node:test 可测）
 *
 * 定位：借鉴「AI Web 传智杯 · 创造虚拟环境」的思路，在前端构建一个可交互的 3D
 * 机房沙盒。用户选择一个「可能失误的运维操作」，系统在虚拟环境里确定性地推演
 * 未来若干 tick 的级联后果（断电宕机 / 温度爬升热保护 / 网络分区 / 服务熔断），
 * 并给出影响面、SLA 风险、级联步骤与规避建议。
 *
 * 数据红线：
 *  - 全部为演示虚拟数据，拓扑与推演均由确定性公式生成，不伪造任何真实机房数据；
 *  - 同一 (拓扑, 操作, 时间窗) 反复推演结果一致，可重放、可单测；
 *  - 预测结果明确标注「预测态」，仅用于演练与风险教育，不作为真实变更决策依据。
 */

/** 资产运行状态，严重度从低到高。 */
export const STATUS_RANK = Object.freeze({ ok: 0, degraded: 1, warn: 2, critical: 3, down: 4 })
export const STATUS_LABELS = Object.freeze({
  ok: '正常',
  degraded: '降级',
  warn: '预警',
  critical: '严重',
  down: '中断'
})

/**
 * 状态色板（与 STATUS_RANK 同序）：更分明的暖色阶梯——
 * 正常绿 / 降级黄 / 预警琥珀 / 严重橙红 / 中断红，逐级拉开色相，
 * 保证在暗底上的辨识度与对比度。3D 网格、徽章、侧栏 KPI 统一引用此常量，避免色值漂移。
 */
export const STATUS_COLORS = Object.freeze({
  ok: '#22c55e',
  degraded: '#facc15',
  warn: '#f59e0b',
  critical: '#f97316',
  down: '#ef4444'
})

/** 温度阈值（摄氏度）：与机房孪生口径一致，便于对照。 */
export const TEMP_THRESHOLDS = Object.freeze({ warn: 28, critical: 32, shutdown: 38 })

/** 默认推演时间窗：tick 数（每 tick ≈ 1 个演示步长）。 */
export const DEFAULT_HORIZON = 24

/**
 * 确定性散列：把文本映射到 [0,1)，用于在没有真实数据时给指标加稳定的「个性」，
 * 保证同一输入输出恒定，测试稳定。
 */
export function hashUnit(text) {
  let h = 2166136261
  const str = String(text ?? '')
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 10000) / 10000
}

/** 单资产温度分级。 */
export function tempLevel(temp) {
  const v = Number(temp)
  if (!Number.isFinite(v)) return 'unknown'
  if (v >= TEMP_THRESHOLDS.shutdown) return 'down'
  if (v >= TEMP_THRESHOLDS.critical) return 'critical'
  if (v >= TEMP_THRESHOLDS.warn) return 'warn'
  return 'ok'
}

/** 取多个状态中最严重者。 */
export function worstStatus(statuses) {
  let worst = 'ok'
  for (const s of statuses || []) {
    if ((STATUS_RANK[s] ?? -1) > (STATUS_RANK[worst] ?? -1)) worst = s
  }
  return worst
}

/* -------------------------------------------------------------------------- */
/*  虚拟拓扑                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * 构建虚拟机房拓扑：2 排 × 6 列机柜，分 A/B 两个制冷区；
 * 每排一台 TOR 交换机，两台核心交换机互为冗余；两台精密空调各负责一个区；
 * 8 个业务服务分布在各机柜，带依赖关系，用于演示级联影响。
 * 坐标单位「米」，与机房孪生页同一尺度，便于复用相机与观感。
 */
export function buildVirtualTopology() {
  const cols = 6
  const rows = 2
  const gapX = 1.6
  const racks = []
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const zone = r === 0 ? 'A' : 'B'
      racks.push({
        id: `R${r + 1}-${String(c + 1).padStart(2, '0')}`,
        label: `R${r + 1}-${String(c + 1).padStart(2, '0')}`,
        row: r,
        col: c,
        zone,
        tor: zone === 'A' ? 'SW-TOR-A' : 'SW-TOR-B',
        x: Number(((c - (cols - 1) / 2) * gapX).toFixed(2)),
        z: Number(((r === 0 ? -1 : 1) * 1.6).toFixed(2))
      })
    }
  }

  const switches = [
    { id: 'SW-CORE-1', label: 'SW-CORE-1', kind: 'core', x: -6.6, z: 0 },
    { id: 'SW-CORE-2', label: 'SW-CORE-2', kind: 'core', x: 6.6, z: 0 },
    { id: 'SW-TOR-A', label: 'SW-TOR-A', kind: 'tor', x: 0, z: -3.1 },
    { id: 'SW-TOR-B', label: 'SW-TOR-B', kind: 'tor', x: 0, z: 3.1 }
  ]

  const coolers = [
    { id: 'CRAC-A', label: 'CRAC-A', zone: 'A', setpoint: 22, x: -5, z: -4.7 },
    { id: 'CRAC-B', label: 'CRAC-B', zone: 'B', setpoint: 22, x: 5, z: 4.7 }
  ]

  /* 网络实验拓扑：核心路由器 → 边缘网关 → 外部，核心交换机 → 路由器全互联冗余。 */
  const routers = [
    { id: 'RTR-CORE-1', label: 'RTR-CORE-1', role: 'core', x: -6.6, z: -2.8 },
    { id: 'RTR-CORE-2', label: 'RTR-CORE-2', role: 'core', x: 6.6, z: -2.8 }
  ]
  const gateways = [
    { id: 'GW-EDGE', label: 'GW-EDGE', role: 'edge', x: 0, z: -5.8 }
  ]

  const services = [
    { id: 'svc-auth', label: '认证服务', rackId: 'R1-02', criticality: 'important' },
    { id: 'svc-order', label: '订单服务', rackId: 'R1-03', criticality: 'core' },
    { id: 'svc-payment', label: '支付服务', rackId: 'R1-04', criticality: 'core' },
    { id: 'svc-notify', label: '通知服务', rackId: 'R1-05', criticality: 'normal' },
    { id: 'svc-inventory', label: '库存服务', rackId: 'R2-02', criticality: 'important' },
    { id: 'svc-cache', label: '缓存集群', rackId: 'R2-03', criticality: 'important' },
    { id: 'svc-db', label: '核心数据库', rackId: 'R2-04', criticality: 'core' },
    { id: 'svc-queue', label: '消息队列', rackId: 'R2-05', criticality: 'important' }
  ]

  const serviceDeps = {
    'svc-order': ['svc-payment', 'svc-inventory'],
    'svc-payment': ['svc-db'],
    'svc-notify': ['svc-queue'],
    'svc-inventory': ['svc-db'],
    'svc-auth': ['svc-db'],
    'svc-db': ['svc-cache']
  }

  const links = []
  for (const rack of racks) {
    links.push({ id: `link-${rack.tor}-${rack.id}`, from: rack.tor, to: rack.id, kind: 'tor-rack', medium: 'copper' })
  }
  for (const tor of ['SW-TOR-A', 'SW-TOR-B']) {
    links.push({ id: `link-SW-CORE-1-${tor}`, from: 'SW-CORE-1', to: tor, kind: 'core-tor', medium: 'fiber' })
    links.push({ id: `link-SW-CORE-2-${tor}`, from: 'SW-CORE-2', to: tor, kind: 'core-tor', medium: 'fiber' })
  }
  // 核心交换机 ↔ 核心路由器：光纤全互联，提供等价多路径冗余。
  for (const core of ['SW-CORE-1', 'SW-CORE-2']) {
    for (const rtr of ['RTR-CORE-1', 'RTR-CORE-2']) {
      links.push({ id: `link-${core}-${rtr}`, from: core, to: rtr, kind: 'core-router', medium: 'fiber' })
    }
  }
  // 核心路由器 ↔ 边缘网关：出口链路。
  for (const rtr of ['RTR-CORE-1', 'RTR-CORE-2']) {
    links.push({ id: `link-${rtr}-GW-EDGE`, from: rtr, to: 'GW-EDGE', kind: 'router-gateway', medium: 'fiber' })
  }

  return { racks, switches, routers, gateways, coolers, services, serviceDeps, links }
}

/* -------------------------------------------------------------------------- */
/*  操作目录：可被「失误执行」的运维动作                                       */
/* -------------------------------------------------------------------------- */

export const OPERATION_CATALOG = Object.freeze([
  {
    id: 'rack-power-off',
    label: 'POWER OFF RACK',
    cn: '误关机柜电源',
    kind: 'power',
    targetId: 'R1-03',
    risk: 'high',
    description: '执行下电时未核对标签，误将 R1-03 机柜总电源关闭。',
    consequenceBrief: '该机柜服务器立即宕机，其上订单服务中断并级联影响依赖方。',
    mitigation: '操作前双人复核标签与资产台账；先迁移业务再下电；使用带防呆的断电流程。'
  },
  {
    id: 'ac-setpoint-raise',
    label: 'RAISE AC SETPOINT',
    cn: '误调空调设定',
    kind: 'cooling',
    targetId: 'CRAC-A',
    risk: 'high',
    description: '为节能误将 A 区精密空调回风设定从 22°C 上调至 30°C。',
    consequenceBrief: 'A 区冷通道温度持续爬升，同区机柜进风超温，触发热保护导致降频乃至宕机。',
    mitigation: '调整空调需走变更审批；设定值单次变动不超过 2°C；联动温度阈值实时校验。'
  },
  {
    id: 'switch-port-down',
    label: 'SHUT TOR PORT',
    cn: '误关交换机端口',
    kind: 'network',
    targetId: 'SW-TOR-A',
    risk: 'high',
    description: '排查链路时误将 SW-TOR-A 下联端口 shutdown。',
    consequenceBrief: 'A 排全部机柜失去网络接入，业务出现网络分区，认证/订单等服务不可达。',
    mitigation: '端口操作前确认描述与对端；先在备链路验证；启用端口防误关保护。'
  },
  {
    id: 'config-misapply',
    label: 'MISAPPLY ROUTE',
    cn: '误下发路由配置',
    kind: 'network',
    targetId: 'SW-CORE-1',
    risk: 'medium',
    description: '配置变更脚本参数错误，向核心交换机下发了错误路由。',
    consequenceBrief: '核心转发出现黑洞，跨区访问超时，触发大量服务降级与熔断。',
    mitigation: '配置先在仿真环境验证；灰度推送；保留回滚快照并设定自动回滚定时器。'
  },
  {
    id: 'server-overload',
    label: 'OVERLOAD SERVER',
    cn: '扩缩容失败致过载',
    kind: 'compute',
    targetId: 'R1-04',
    risk: 'medium',
    description: '流量洪峰时自动扩容失败，R1-04 单机持续 100% CPU。',
    consequenceBrief: '支付服务响应超时，触发下游熔断，订单链路延迟飙升。',
    mitigation: '扩容配额与健康检查前置；设定单机 CPU 阈值自动限流；多可用区分散部署。'
  },
  {
    id: 'stp-loop',
    label: 'DISABLE STP',
    cn: '误关 STP 致环路',
    kind: 'network',
    targetId: 'SW-TOR-A',
    targetKind: 'switch',
    risk: 'high',
    description: '为「优化」误将 SW-TOR-A 的 STP 关闭，而该交换机存在冗余上联，形成二层环路。',
    consequenceBrief: '广播风暴在全网扩散，链路利用率打满，交换机 CPU 飙升，所有业务出现严重丢包与降级。',
    mitigation: 'STP 不得随意关闭；冗余链路用 MSTP/RSTP 防环；变更前先做环路检测与仿真验证。'
  },
  {
    id: 'gateway-down',
    label: 'EDGE GW DOWN',
    cn: '边缘网关宕机',
    kind: 'network',
    targetId: 'GW-EDGE',
    targetKind: 'gateway',
    risk: 'high',
    description: '网关固件升级失败，GW-EDGE 重启后进程崩溃，南北向出口中断。',
    consequenceBrief: '全部业务失去对外连通性，出方向流量被丢弃，所有服务降级，外部用户完全不可访问。',
    mitigation: '网关双机热备 + BFD；升级走灰度并预留回滚窗口；出口链路配置运营商级冗余。'
  },
  {
    id: 'link-cut',
    label: 'FIBER CUT',
    cn: '核心链路中断',
    kind: 'network',
    targetId: 'link-SW-CORE-1-SW-TOR-A',
    targetKind: 'link',
    risk: 'medium',
    description: '施工挖断 SW-CORE-1 与 SW-TOR-A 之间的主干光纤。',
    consequenceBrief: 'A 区上行主用中断，流量绕行备用链路，延迟升高、带宽减半，A 区业务降级；若再断一条将全瘫。',
    mitigation: '关键链路双路由物理隔离；定期做链路倒换演练；光功率与误码率实时监控告警。'
  },
  {
    id: 'router-misconfig',
    label: 'BAD STATIC ROUTE',
    cn: '路由器误配静态路由',
    kind: 'network',
    targetId: 'RTR-CORE-1',
    targetKind: 'router',
    risk: 'medium',
    description: '向 RTR-CORE-1 下发静态路由时下一跳指向不存在的地址，形成黑洞。',
    consequenceBrief: '支付与库存方向的流量被静默丢弃，对应服务不可达，订单链路无法完成扣款。',
    mitigation: '静态路由变更必须校验下一跳可达性；优先用动态路由协议；变更后立刻做 traceroute 验证。'
  },
  {
    id: 'vlan-mismatch',
    label: 'VLAN MISMATCH',
    cn: 'Trunk VLAN 不一致',
    kind: 'network',
    targetId: 'SW-TOR-A',
    targetKind: 'switch',
    risk: 'medium',
    description: '修改 Trunk 允许 VLAN 时遗漏 VLAN 10，导致 SW-TOR-A 下联的认证终端被隔离。',
    consequenceBrief: '认证服务所在 VLAN 10 与核心侧 VLAN 不一致，认证流量被丢弃，认证服务中断，所有登录受影响。',
    mitigation: 'VLAN 变更走模板化配置；变更前后对比 allowed VLAN；用 LLDP/连通性探针自动校验。'
  },
  {
    id: 'ospf-flap',
    label: 'OSPF NEIGHBOR FLAP',
    cn: 'OSPF 邻居频繁抖动',
    kind: 'network',
    targetId: 'RTR-CORE-1',
    targetKind: 'router',
    risk: 'medium',
    description: 'RTR-CORE-1 的 OSPF 邻居关系因链路不稳反复 Up/Down，路由表频繁收敛。',
    consequenceBrief: '核心出口路由间歇性丢失，全网出方向流量在奇数 tick 出现丢包与重传，业务呈「抖动式」降级，偶数 tick 短暂恢复。',
    mitigation: '排查光模块与链路误码；配置 BFD 快速检测与邻居震荡抑制（dampening）；收敛期间保留静态兜底路由。'
  },
  {
    id: 'optical-attenuation',
    label: 'OPTICAL ATTENUATION',
    cn: '主干光功率衰减',
    kind: 'network',
    targetId: 'link-SW-CORE-1-SW-TOR-A',
    targetKind: 'link',
    risk: 'medium',
    description: 'SW-CORE-1 与 SW-TOR-A 之间主干光纤老化 / 弯折，光功率低于接收灵敏度，误码率飙升。',
    consequenceBrief: 'A 区上行主用链路未硬断但呈高误码抖动，奇数 tick 丢包重传、A 区服务间歇降级，偶数 tick 暂时恢复；再劣化将硬断。',
    mitigation: '光功率与误码率实时监控并设阈值告警；定期 OTDR 巡检；关键链路双路由物理隔离并保持备路洁净。'
  },
  {
    id: 'firewall-misconfig',
    label: 'FW ACL MISCONFIG',
    cn: '防火墙策略误配',
    kind: 'network',
    targetId: 'GW-EDGE',
    targetKind: 'gateway',
    risk: 'high',
    description: '在 GW-EDGE 下发 ACL 时将支付网段的出向 permit 误写为 deny，阻断支付前缀对外访问。',
    consequenceBrief: '支付服务出向被持续阻断，支付链路降级；依赖支付的订单服务随降级，但其余业务不受影响，故障面精确且持续。',
    mitigation: 'ACL 变更先在仿真/影子策略校验；灰度推送并自动回滚；变更后立即用连通性探针对受影响前缀做端到端验证。'
  },
  {
    id: 'db-config-delete',
    label: 'DELETE DB CONFIG',
    cn: '误删数据库配置',
    kind: 'config',
    targetId: 'svc-db',
    targetKind: 'service',
    risk: 'high',
    description: '变更窗口清理「废弃配置」时误删核心数据库的连接配置，连接串与账号信息失效。',
    consequenceBrief: '核心数据库配置缺失即刻中断，订单 / 支付 / 库存 / 认证依赖方在 1 个 tick 后级联中断，故障面由单点扩散到交易主链路。',
    mitigation: '配置删除走软删除 + 回收站；变更前导出快照并校验引用关系；关键配置启用版本化与一键回滚。'
  },
  {
    id: 'batch-reboot',
    label: 'BATCH REBOOT',
    cn: '批量重启失误',
    kind: 'compute',
    targetId: 'R2-04',
    targetIds: ['R2-03', 'R2-04', 'R2-05'],
    targetKind: 'rack',
    risk: 'high',
    description: '滚动升级脚本的批次并发度配置错误，R2 排 3 个机柜被同时重启，而非逐一滚动。',
    consequenceBrief: '3 个机柜在重启窗口内同时中断，数据库 / 缓存 / 消息队列同时不可用，依赖服务级联中断；重启完成后可自行恢复。',
    mitigation: '批量操作强制串行/小批次并设置并发上限；重启前确认冗余副本；变更窗口内挂起自动扩缩容与告警风暴抑制。'
  }
])

export function operationById(id) {
  return OPERATION_CATALOG.find(item => item.id === id) || null
}

/* -------------------------------------------------------------------------- */
/*  基线状态                                                                   */
/* -------------------------------------------------------------------------- */

/** 构造一份全健康的初始状态（tick = 0，尚未注入任何操作）。 */
export function baselineState(topology) {
  const racks = {}
  for (const rack of topology.racks) {
    const zoneTemp = 22
    const base = 22.6 + hashUnit(rack.id) * 1.6 + (rack.row === 1 ? 0.5 : 0)
    racks[rack.id] = {
      id: rack.id,
      label: rack.label,
      status: 'ok',
      temp: Number(base.toFixed(1)),
      networkLost: false,
      powerOff: false,
      rebootRemaining: 0,
      overload: false,
      pathFlapping: false,
      zone: rack.zone,
      zoneTemp
    }
  }
  const switches = {}
  for (const sw of topology.switches) {
    switches[sw.id] = { id: sw.id, status: 'ok', portDown: false, blackhole: false }
  }
  const routers = {}
  for (const rtr of topology.routers) {
    routers[rtr.id] = { id: rtr.id, status: 'ok', blackhole: false }
  }
  const gateways = {}
  for (const gw of topology.gateways) {
    gateways[gw.id] = { id: gw.id, status: 'ok', down: false }
  }
  const links = {}
  for (const link of topology.links) {
    links[link.id] = { id: link.id, status: 'up', flapping: false }
  }
  const coolers = {}
  for (const cooler of topology.coolers) {
    coolers[cooler.id] = {
      id: cooler.id,
      status: 'ok',
      setpoint: cooler.setpoint,
      zoneTemp: cooler.setpoint
    }
  }
  const services = {}
  for (const svc of topology.services) {
    services[svc.id] = { id: svc.id, label: svc.label, status: 'ok', depDownTicks: 0, transient: false }
  }
  return {
    tick: 0,
    racks, switches, routers, gateways, coolers, services, links,
    broadcastStorm: false,
    stpDisabled: {},
    gatewayDown: false,
    vlanIsolated: {},
    routeBlackhole: {},
    flappingLinks: {},
    flappingRouters: {},
    firewallBlocked: {},
    configDeleted: {},
    events: []
  }
}

function pushEvent(state, assetId, kind, text) {
  state.events.push({
    id: `${state.tick}:${assetId}:${kind}`,
    tick: state.tick,
    assetId,
    kind,
    text
  })
}

/** 深拷贝一份状态快照（存入时间线，避免后续 tick 污染历史）。 */
export function snapshot(state) {
  return {
    tick: state.tick,
    racks: Object.fromEntries(Object.values(state.racks).map(r => [r.id, { ...r }])),
    switches: Object.fromEntries(Object.values(state.switches).map(s => [s.id, { ...s }])),
    routers: Object.fromEntries(Object.values(state.routers).map(r => [r.id, { ...r }])),
    gateways: Object.fromEntries(Object.values(state.gateways).map(g => [g.id, { ...g }])),
    links: Object.fromEntries(Object.values(state.links).map(l => [l.id, { ...l }])),
    coolers: Object.fromEntries(Object.values(state.coolers).map(c => [c.id, { ...c }])),
    services: Object.fromEntries(Object.values(state.services).map(s => [s.id, { ...s }])),
    broadcastStorm: state.broadcastStorm,
    stpDisabled: { ...state.stpDisabled },
    gatewayDown: state.gatewayDown,
    vlanIsolated: { ...state.vlanIsolated },
    routeBlackhole: { ...state.routeBlackhole },
    flappingLinks: { ...state.flappingLinks },
    flappingRouters: { ...state.flappingRouters },
    firewallBlocked: { ...state.firewallBlocked },
    configDeleted: { ...state.configDeleted },
    events: state.events.map(e => ({ ...e }))
  }
}

/* -------------------------------------------------------------------------- */
/*  注入操作                                                                   */
/* -------------------------------------------------------------------------- */

/** 在 tick 0 把操作对应的「失误」注入状态，并记录初始事件。 */
export function applyOperation(state, op) {
  if (!op) return state
  switch (op.id) {
    case 'rack-power-off': {
      const rack = state.racks[op.targetId]
      if (rack) {
        rack.powerOff = true
        rack.status = 'down'
        pushEvent(state, rack.id, 'power', `${rack.label} 总电源被误关闭，服务器立即宕机`)
      }
      break
    }
    case 'ac-setpoint-raise': {
      const cooler = state.coolers[op.targetId]
      if (cooler) {
        cooler.setpoint = 30
        cooler.status = 'warn'
        pushEvent(state, cooler.id, 'cooling', `${cooler.id} 回风设定被误调至 30°C，A 区开始升温`)
      }
      break
    }
    case 'switch-port-down': {
      const sw = state.switches[op.targetId]
      if (sw) {
        sw.portDown = true
        sw.status = 'degraded'
        pushEvent(state, sw.id, 'network', `${sw.id} 下联端口被误 shutdown，其下联机柜网络中断`)
      }
      break
    }
    case 'config-misapply': {
      const sw = state.switches[op.targetId]
      if (sw) {
        sw.blackhole = true
        sw.status = 'degraded'
        pushEvent(state, sw.id, 'network', `${sw.id} 被下发错误路由，跨区转发出现黑洞`)
      }
      break
    }
    case 'server-overload': {
      const rack = state.racks[op.targetId]
      if (rack) {
        rack.overload = true
        rack.status = 'warn'
        pushEvent(state, rack.id, 'compute', `${rack.label} 扩容失败，单机持续过载，CPU 100%`)
      }
      break
    }
    case 'stp-loop': {
      const sw = state.switches[op.targetId]
      if (sw) {
        state.stpDisabled[sw.id] = true
        sw.status = 'warn'
        pushEvent(state, sw.id, 'network', `${sw.id} 的 STP 被误关闭，冗余链路形成二层环路`)
      }
      break
    }
    case 'gateway-down': {
      const gw = state.gateways[op.targetId]
      if (gw) {
        state.gatewayDown = true
        gw.down = true
        gw.status = 'down'
        pushEvent(state, gw.id, 'network', `${gw.id} 宕机，南北向出口中断，对外流量被丢弃`)
      }
      break
    }
    case 'link-cut': {
      const link = state.links[op.targetId]
      if (link) {
        link.status = 'down'
        pushEvent(state, link.id, 'network', `链路 ${op.targetId} 中断，上行可用路径减少`)
      }
      break
    }
    case 'router-misconfig': {
      const rtr = state.routers[op.targetId]
      if (rtr) {
        rtr.blackhole = true
        rtr.status = 'degraded'
        state.routeBlackhole['svc-payment'] = true
        state.routeBlackhole['svc-inventory'] = true
        pushEvent(state, rtr.id, 'network', `${rtr.id} 被下发错误静态路由，支付/库存方向流量进入黑洞`)
      }
      break
    }
    case 'vlan-mismatch': {
      const sw = state.switches[op.targetId]
      if (sw) {
        state.vlanIsolated['svc-auth'] = true
        sw.status = 'warn'
        pushEvent(state, sw.id, 'network', `${sw.id} Trunk allowed VLAN 遗漏 VLAN 10，认证终端被隔离`)
      }
      break
    }
    case 'ospf-flap': {
      const rtr = state.routers[op.targetId]
      if (rtr) {
        state.flappingRouters[rtr.id] = true
        pushEvent(state, rtr.id, 'network', `${rtr.id} 的 OSPF 邻居开始频繁 Up/Down，出口路由间歇性丢失`)
      }
      break
    }
    case 'optical-attenuation': {
      const link = state.links[op.targetId]
      if (link) {
        link.flapping = true
        state.flappingLinks[link.id] = true
        pushEvent(state, link.id, 'network', `链路 ${op.targetId} 光功率衰减，误码率飙升，开始高误码抖动`)
      }
      break
    }
    case 'firewall-misconfig': {
      const gw = state.gateways[op.targetId]
      if (gw) {
        // 错误 ACL 阻断支付前缀出向，故障面精确且持续。
        state.firewallBlocked['svc-payment'] = true
        gw.status = 'degraded'
        pushEvent(state, gw.id, 'network', `${gw.id} 下发错误 ACL，支付前缀出向被 deny，支付链路降级`)
      }
      break
    }
    case 'db-config-delete': {
      // 配置被误删：目标服务直接中断，依赖方由 stepState 按依赖关系滞后级联。
      state.configDeleted['svc-db'] = true
      pushEvent(state, 'svc-db', 'config', '核心数据库连接配置被误删，配置加载失败，服务中断')
      break
    }
    case 'batch-reboot': {
      // 批次并发度配置错误：多个机柜同时进入重启窗口，rebootRemaining > 0 时按断电处理，
      // 归零后由 stepState 恢复供电并重新上线，演示「先中断、后恢复」的级联。
      const rackIds = Array.isArray(op.targetIds) && op.targetIds.length ? op.targetIds : [op.targetId]
      for (const id of rackIds) {
        const rack = state.racks[id]
        if (!rack) continue
        rack.powerOff = true
        rack.rebootRemaining = 4
        rack.status = 'down'
      }
      pushEvent(state, op.targetId, 'power', `${rackIds.join('、')} 被同时重启（并发度配置错误），整批机柜进入中断`)
      break
    }
    default:
      break
  }
  return state
}

/* -------------------------------------------------------------------------- */
/*  单步推演                                                                   */
/* -------------------------------------------------------------------------- */

/** 把状态向前推进一个 tick：温度扩散、网络分区传导、服务依赖级联。 */
export function stepState(state, topology) {
  const prev = snapshot(state)
  state.tick = prev.tick + 1
  state.events = []
  /* 抖动 tick：奇数 tick 为「坏」tick（链路/邻居处于劣化态），偶数 tick 短暂恢复，用于演示间歇性故障。 */
  const badTick = state.tick % 2 === 1

  /* 1) 制冷：区域温度向空调设定值收敛（误调高则持续爬升）。 */
  for (const cooler of Object.values(state.coolers)) {
    const target = cooler.setpoint
    cooler.zoneTemp = Number((cooler.zoneTemp + (target - cooler.zoneTemp) * 0.4).toFixed(2))
    cooler.status = cooler.zoneTemp >= TEMP_THRESHOLDS.critical ? 'critical'
      : cooler.zoneTemp >= TEMP_THRESHOLDS.warn ? 'warn' : 'ok'
  }

  /* 2) 网络分区：核心黑洞 / TOR 端口 down / 接入或上行链路中断 → 机柜失联。 */
  const coreBlackhole = Object.values(state.switches).some(sw => sw.blackhole)
  const linkUp = id => state.links[id]?.status !== 'down'
  for (const rack of Object.values(state.racks)) {
    const rackDef = topology.racks.find(r => r.id === rack.id)
    const torId = rackDef?.tor
    const accessUp = linkUp(`link-${torId}-${rack.id}`)
    const uplinkA = linkUp(`link-SW-CORE-1-${torId}`)
    const uplinkB = linkUp(`link-SW-CORE-2-${torId}`)
    const torPortDown = !!state.switches[torId]?.portDown
    rack.networkLost = coreBlackhole || !accessUp || torPortDown || (!uplinkA && !uplinkB)
  }

  /* 2b) 广播风暴：STP 被关闭后，下一 tick 风暴在整个二层域扩散。 */
  if (Object.keys(state.stpDisabled).length > 0 && !state.broadcastStorm) {
    state.broadcastStorm = true
    pushEvent(state, 'SW-CORE-1', 'network', '二层环路未被阻断，广播风暴开始全网扩散，链路利用率飙升')
  }

  /* 2c) 抖动链路：光功率衰减在坏 tick 使链路降级、好 tick 恢复；并把受影响机柜的上行路径标为抖动。
     注意：降级不等于 down，不触发 networkLost，只形成 pathFlapping 的间歇性劣化。 */
  for (const link of Object.values(state.links)) {
    if (state.flappingLinks[link.id]) {
      link.status = badTick ? 'degraded' : 'up'
    }
  }
  for (const rack of Object.values(state.racks)) {
    const rackDef = topology.racks.find(r => r.id === rack.id)
    const torId = rackDef?.tor
    const flappingUplink = badTick && (
      !!state.flappingLinks[`link-SW-CORE-1-${torId}`] ||
      !!state.flappingLinks[`link-SW-CORE-2-${torId}`]
    )
    rack.pathFlapping = !!flappingUplink
  }

  /* 3) 机柜温度：跟随区域温度 + 负载/断电/失联导致的发热，再映射运行状态。 */
  // 本 tick 刚重启完成的机柜：其上的服务不再按上一帧的依赖状态继续级联中断，允许即刻恢复。
  const justRebooted = new Set()
  for (const rack of Object.values(state.racks)) {
    // 重启窗口倒计时：归零后恢复供电，让业务可在后续 tick 自行恢复。
    if (rack.rebootRemaining > 0) {
      rack.rebootRemaining -= 1
      if (rack.rebootRemaining === 0) {
        rack.powerOff = false
        rack.temp = Number(Math.min(rack.temp, 24.5).toFixed(1))
        justRebooted.add(rack.id)
        pushEvent(state, rack.id, 'power', `${rack.label} 重启完成，服务器重新上线`)
      }
    }
    if (rack.powerOff) {
      rack.temp = Number(Math.min(55, rack.temp + 1.6).toFixed(1))
    } else {
      const zoneTemp = state.coolers[rack.zone === 'A' ? 'CRAC-A' : 'CRAC-B']?.zoneTemp ?? 22
      const target = zoneTemp
        + 1.4
        + (rack.overload ? 6.5 : 0)
        + (rack.networkLost ? 0.8 : 0)
      rack.temp = Number((rack.temp + (target - rack.temp) * 0.32).toFixed(1))
    }
    const tLevel = tempLevel(rack.temp)
    const next = rack.powerOff ? 'down'
      : tLevel === 'down' ? 'critical' // 温度达到关机线：先标严重（触发告警），下一 tick 才中断，留出可见窗口
      : tLevel
    if (next !== rack.status) {
      const labels = { warn: '进风超温预警', critical: '进风严重超温', down: '热保护触发中断', degraded: '网络失联' }
      if (STATUS_RANK[next] > STATUS_RANK[rack.status]) {
        pushEvent(state, rack.id, 'thermal', `${rack.label} ${labels[next] || next}（${rack.temp}°C）`)
      }
      rack.status = next
    }
    /* 达到关机线后下一 tick 真正中断。 */
    if (!rack.powerOff && rack.temp >= TEMP_THRESHOLDS.shutdown && rack.status === 'critical') {
      rack.status = 'down'
      pushEvent(state, rack.id, 'thermal', `${rack.label} 触发热保护，服务器宕机（${rack.temp}°C）`)
    }
  }

  /* 4) 服务级联：机架中断 → 服务中断；机架失联 → 服务降级；依赖受损 → 降级/中断。 */
  const nextServices = {}
  for (const svcDef of topology.services) {
    const prevSvc = prev.services[svcDef.id]
    const rack = state.racks[svcDef.rackId]
    const deps = topology.serviceDeps[svcDef.id] || []
    let status = 'ok'
    let depDownTicks = 0
    let transient = false
    // 宿主机健康：宕机 → 中断；失联/过载/进风严重超温 → 性能降级。
    const hostDegraded = rack.networkLost || rack.overload || STATUS_RANK[rack.status] >= STATUS_RANK.critical
    // 网络实验效应：VLAN 隔离 / 路由黑洞 / 出口中断 / 广播风暴 / 防火墙阻断（持续）。
    const vlanIsolated = !!state.vlanIsolated[svcDef.id]
    const configMissing = !!state.configDeleted[svcDef.id]
    const blackholed = !!state.routeBlackhole[svcDef.id]
    const egressBlocked = state.gatewayDown
    const stormCongested = state.broadcastStorm
    const firewallBlocked = !!state.firewallBlocked[svcDef.id]
    // 间歇性抖动：OSPF 邻居抖动（出口）或主干光功率衰减（上行路径），仅坏 tick 生效。
    const flappingEgress = Object.keys(state.flappingRouters).length > 0
    const flapDegraded = badTick && (flappingEgress || rack.pathFlapping)
    // badDeps 只考虑「持续性」降级：由抖动导致的 transient 降级不传导，避免好 tick 无法恢复。
    const depRackRebooted = dep => justRebooted.has(topology.services.find(svc => svc.id === dep)?.rackId)
    const badDeps = deps.filter(dep => {
      const s = prev.services[dep]
      if (!s) return false
      // 依赖方所在机柜刚重启完成：视为恢复中，不再传导降级。
      if (s.status === 'down') return !depRackRebooted(dep)
      return s.status === 'degraded' && !s.transient
    })
    const downDeps = deps.filter(dep => prev.services[dep]?.status === 'down' && !depRackRebooted(dep))
    if (configMissing) {
      status = 'down' // 配置被误删 → 服务无法加载配置，直接中断
    } else if (vlanIsolated) {
      status = 'down' // VLAN 不一致 → 业务完全不可达
    } else if (rack.status === 'down') {
      status = 'down'
    } else if (downDeps.length > 0) {
      // 依赖已中断：容忍 1 个 tick 的抖动，随后本服务也中断。
      depDownTicks = (prevSvc?.depDownTicks || 0) + 1
      status = depDownTicks >= 1 ? 'down' : 'degraded'
    } else if (hostDegraded || badDeps.length > 0 || blackholed || egressBlocked || stormCongested || firewallBlocked) {
      status = 'degraded'
      transient = false
      depDownTicks = badDeps.length > 0 ? (prevSvc?.depDownTicks || 0) + 1 : 0
    } else if (flapDegraded) {
      // 抖动导致的降级：标记 transient，好 tick 恢复且不向依赖方传导。
      status = 'degraded'
      transient = true
      depDownTicks = 0
    } else {
      status = 'ok'
      transient = false
      depDownTicks = 0
    }
    if (status !== prevSvc?.status && STATUS_RANK[status] > (STATUS_RANK[prevSvc?.status] ?? 0)) {
      const reason = configMissing
        ? '服务配置被误删，无法加载'
        : vlanIsolated
          ? 'VLAN 配置不一致，业务被隔离'
          : rack.status === 'down'
          ? `${rack.label} 宕机`
          : downDeps.length > 0
            ? `依赖 ${downDeps.map(d => prev.services[d]?.label).join('、')} 中断`
            : blackholed
              ? '路由误配，流量被黑洞丢弃'
              : egressBlocked
                ? '边缘网关宕机，出口不可达'
                : stormCongested
                  ? '广播风暴导致链路拥塞'
                  : firewallBlocked
                    ? '防火墙 ACL 误配，出向被阻断'
                    : flapDegraded
                      ? flappingEgress
                        ? 'OSPF 邻居抖动，出口间歇拥塞'
                        : '主干链路光功率衰减，路径高误码'
                      : rack.overload
                        ? '单机过载'
                        : rack.networkLost
                          ? '网络失联'
                          : badDeps.length > 0 ? '依赖受损' : '进风超温'
      const text = status === 'down'
        ? `${svcDef.label} 已中断（${reason}）`
        : `${svcDef.label} 降级（${reason}）`
      pushEvent(state, svcDef.id, 'service', text)
    }
    nextServices[svcDef.id] = { id: svcDef.id, label: svcDef.label, status, depDownTicks, transient }
  }
  state.services = nextServices

  /* 5) 网络设备状态收敛：广播风暴 → 严重；端口 down/黑洞/网关宕机 → 降级或中断。 */
  for (const sw of Object.values(state.switches)) {
    const stpOff = !!state.stpDisabled[sw.id]
    sw.status = state.broadcastStorm ? 'critical'
      : sw.portDown || sw.blackhole ? 'degraded'
      : stpOff ? 'warn'
      : 'ok'
  }
  for (const rtr of Object.values(state.routers)) {
    const flapping = !!state.flappingRouters[rtr.id]
    rtr.status = state.broadcastStorm ? 'critical'
      : flapping && badTick ? 'degraded'
      : rtr.blackhole ? 'degraded'
      : state.gatewayDown ? 'degraded'
      : 'ok'
  }
  for (const gw of Object.values(state.gateways)) {
    const fwBad = Object.keys(state.firewallBlocked).length > 0
    gw.status = gw.down ? 'down' : state.broadcastStorm ? 'critical' : fwBad ? 'degraded' : 'ok'
  }

  return state
}

/* -------------------------------------------------------------------------- */
/*  推演入口                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * 对指定操作推演未来 horizon 个 tick 的级联后果。
 * @returns {{ operation, timeline: Array, summary }}
 */
export function predictConsequences(topology, operationId, horizon = DEFAULT_HORIZON) {
  const op = operationById(operationId)
  const state = baselineState(topology)
  applyOperation(state, op)
  const timeline = [snapshot(state)]
  const steps = Math.max(0, Math.floor(Number(horizon) || 0))
  for (let t = 1; t <= steps; t += 1) {
    stepState(state, topology)
    timeline.push(snapshot(state))
  }
  return { operation: op, timeline, summary: summarize(timeline, op) }
}

/** 汇总推演结果：影响面、严重度、预估中断时长、SLA 风险、级联步骤、建议。 */
export function summarize(timeline, op) {
  const final = timeline[timeline.length - 1]
  const rackValues = Object.values(final.racks)

  /* 间歇性故障在偶数（好）tick 会短暂恢复，单看末帧会低估影响面；
     因此受影响资产按整段时间线取并集，中断/严重数与最高严重度取峰值。 */
  const affectedRackIds = new Set()
  const affectedServiceIds = new Set()
  const allStatuses = []
  let downRacks = 0
  let downServices = 0
  let criticalServices = 0
  let affectedNetwork = 0
  let downLinks = 0
  for (const snap of timeline) {
    const rv = Object.values(snap.racks)
    const sv = Object.values(snap.services)
    const netDevices = [
      ...Object.values(snap.switches),
      ...Object.values(snap.routers),
      ...Object.values(snap.gateways)
    ]
    for (const r of rv) {
      if (r.status !== 'ok') affectedRackIds.add(r.id)
      allStatuses.push(r.status)
    }
    for (const s of sv) {
      if (s.status !== 'ok') affectedServiceIds.add(s.id)
      allStatuses.push(s.status)
    }
    for (const d of [...netDevices, ...Object.values(snap.coolers)]) allStatuses.push(d.status)
    downRacks = Math.max(downRacks, rv.filter(r => r.status === 'down').length)
    downServices = Math.max(downServices, sv.filter(s => s.status === 'down').length)
    criticalServices = Math.max(criticalServices, sv.filter(s => s.status === 'critical').length)
    affectedNetwork = Math.max(affectedNetwork, netDevices.filter(d => d.status !== 'ok').length)
    downLinks = Math.max(downLinks, Object.values(snap.links).filter(l => l.status === 'down').length)
  }
  const maxSeverity = worstStatus(allStatuses)
  const flappingLinksCount = Object.keys(final.flappingLinks || {}).length
  const flappingRoutersCount = Object.keys(final.flappingRouters || {}).length
  const intermittent = (flappingLinksCount + flappingRoutersCount) > 0

  /* 预估中断时长：确定性换算，仅用于演示量级（分钟）。 */
  const estimatedOutageMinutes = Math.min(240, downServices * 6 + downRacks * 4 + criticalServices * 2)

  const slaRisk = downServices > 0 ? 'high'
    : criticalServices > 0 ? 'medium'
    : affectedServiceIds.size > 0 ? 'low'
    : 'none'

  const slaRiskLabel = { high: '高', medium: '中', low: '低', none: '无' }[slaRisk]

  const cascadingSteps = timeline
    .flatMap(snap => snap.events)
    .map(e => ({ tick: e.tick, text: e.text, kind: e.kind }))
    .slice(0, 14)

  const hottestRacks = [...rackValues].sort((a, b) => b.temp - a.temp).slice(0, 5)
    .map(r => ({ id: r.id, label: r.label, temp: r.temp, status: r.status }))

  return {
    operationId: op?.id || null,
    horizon: timeline.length - 1,
    affectedRackCount: affectedRackIds.size,
    affectedServiceCount: affectedServiceIds.size,
    affectedNetworkCount: affectedNetwork,
    downRacks,
    downServices,
    downLinks,
    intermittent,
    flappingLinksCount,
    flappingRoutersCount,
    maxSeverity,
    maxSeverityLabel: STATUS_LABELS[maxSeverity] || maxSeverity,
    estimatedOutageMinutes,
    slaRisk,
    slaRiskLabel,
    impactedBusiness: [...affectedServiceIds].map(id => final.services[id]?.label).filter(Boolean),
    cascadingSteps,
    hottestRacks,
    recommendation: op?.mitigation || ''
  }
}

/**
 * 前向预测：扫描整段推演时间线，返回每个资产在整个时间窗内的「峰值（最坏）状态」。
 * 与 summarize 只给汇总数不同，这里逐资产给出最坏状态与首次劣化 tick，
 * 供 3D 画布在操作执行的瞬间（T+0）就悬浮提示「该资产将恶化到什么程度」，
 * 而不是仅随当前帧着色——这是相对当前帧可视化的增量价值。
 * 仅返回 worstStatus !== 'ok' 的资产；覆盖：
 * 机柜 / 交换机 / 路由器 / 网关 / 空调 / 链路 / 业务服务。
 * 业务服务条目额外携带 rackId（宿主机架，用于 3D 定位）与 criticality（重要级别）。
 * @returns {Array<{ id, label, kind, worstStatus, firstBadTick, rackId?, criticality? }>}
 */
export function predictAssetPeaks(topology, timeline) {
  const out = []
  const scan = (map, kind, labelFn, extraFn) => {
    for (const def of topology[map] || []) {
      let worst = 'ok'
      let firstBad = -1
      for (const snap of timeline || []) {
        const st = snap[map]?.[def.id]?.status
        if (st && (STATUS_RANK[st] ?? -1) > (STATUS_RANK[worst] ?? -1)) {
          worst = st
          firstBad = snap.tick
        }
      }
      if (worst !== 'ok') {
        out.push({
          id: def.id, label: labelFn(def), kind, worstStatus: worst, firstBadTick: firstBad,
          ...(extraFn ? extraFn(def) : {})
        })
      }
    }
  }
  scan('racks', 'rack', r => r.label)
  scan('switches', 'switch', s => s.id)
  scan('routers', 'router', r => r.id)
  scan('gateways', 'gateway', g => g.id)
  scan('coolers', 'cooler', c => c.id)
  scan('links', 'link', l => l.id)
  // 业务服务：附带宿主机架与重要级别，供 3D 定位与侧栏分级展示。
  scan('services', 'service', s => s.label, s => ({ rackId: s.rackId, criticality: s.criticality }))
  return out
}

/** 取某一 tick 的快照（用于时间线拖动 / 动画当前帧）。 */
export function snapshotAt(timeline, tick) {
  if (!timeline || !timeline.length) return null
  const idx = Math.max(0, Math.min(timeline.length - 1, Math.floor(Number(tick) || 0)))
  return timeline[idx]
}

/* ----------------------------- 演练报告导出 ----------------------------- */
const ASSET_KIND_LABELS = Object.freeze({
  rack: '机柜',
  switch: '交换机',
  router: '路由器',
  gateway: '网关',
  cooler: '空调',
  link: '链路',
  service: '业务服务'
})
const CRITICALITY_RANK = Object.freeze({ core: 0, important: 1, normal: 2 })
const CRITICALITY_LABELS = Object.freeze({ core: '核心', important: '重要', normal: '普通' })

/** Markdown 表格单元格转义：防止资产名里的竖线破坏表格结构。 */
function mdCell(value) {
  return String(value ?? '').replace(/\|/g, '\\|')
}

/** HTML 转义：报告含资产名等文本，导出为 HTML 时必须转义，避免标签注入。 */
function escHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ))
}

/** 报告公共模型：Markdown 与 HTML 共用同一份排序结果，避免两种导出物口径漂移。 */
function reportModel(op, prediction, peaks) {
  if (!op || !prediction || !prediction.summary) return null
  const list = Array.isArray(peaks) ? peaks : []
  const sortedPeaks = [...list].sort((a, b) => (
    (STATUS_RANK[b.worstStatus] ?? -1) - (STATUS_RANK[a.worstStatus] ?? -1)
    || String(a.label).localeCompare(String(b.label), 'zh-Hans-CN')
  ))
  const services = sortedPeaks
    .filter(p => p.kind === 'service')
    .sort((a, b) => (CRITICALITY_RANK[a.criticality] ?? 9) - (CRITICALITY_RANK[b.criticality] ?? 9)
      || String(a.label).localeCompare(String(b.label), 'zh-Hans-CN'))
  return { summary: prediction.summary, sortedPeaks, services }
}

/**
 * 生成「操作失误演练报告」Markdown 文本，供复盘留档与跨团队共享。
 * 内容全部来自确定性推演结果（峰值后果 / 业务影响 / 资产峰值 / 级联步骤 / 规避建议），
 * generatedAt 由调用方传入，保证函数本身无副作用、可单测。
 * @param {object} op 操作目录条目
 * @param {object} prediction predictConsequences 的返回值
 * @param {Array} peaks predictAssetPeaks 的返回值
 * @param {string} [generatedAt] 生成时间文本（调用方格式化）
 * @returns {string} Markdown 文本；缺少操作或预测时返回空串
 */
export function buildDrillReport(op, prediction, peaks, generatedAt = '') {
  const model = reportModel(op, prediction, peaks)
  if (!model) return ''
  const { summary: s, sortedPeaks, services } = model
  const label = st => STATUS_LABELS[st] || st

  const lines = []
  lines.push(`# 操作失误演练报告 · ${op.cn}`, '')
  lines.push('> 预测态 · 演示虚拟数据，仅用于演练与风险教育，不作为真实变更决策依据。', '')
  if (generatedAt) lines.push(`- 生成时间：${generatedAt}`)
  lines.push(`- 操作编号：${op.id}`)
  lines.push(`- 目标资产：${op.targetId}（${op.label}）`)
  lines.push(`- 风险等级：${op.risk === 'high' ? '高风险' : '中风险'}`)
  lines.push(`- 推演步数：${s.horizon} 步（T+0 为操作注入时刻）`, '')

  lines.push('## 峰值后果', '', '| 指标 | 值 |', '| --- | --- |')
  lines.push(`| 最高严重度 | ${label(s.maxSeverity)} |`)
  lines.push(`| SLA 风险 | ${s.slaRiskLabel} |`)
  lines.push(`| 预估中断时长 | ${s.estimatedOutageMinutes} 分 |`)
  lines.push(`| 受影响业务 | ${s.affectedServiceCount}（其中中断 ${s.downServices}） |`)
  lines.push(`| 受影响机柜 | ${s.affectedRackCount}（其中中断 ${s.downRacks}） |`)
  lines.push(`| 受影响网络设备 | ${s.affectedNetworkCount} |`)
  lines.push(`| 中断链路 | ${s.downLinks} |`, '')

  lines.push('## 受影响业务（预测峰值）', '')
  if (services.length) {
    lines.push('| 业务 | 重要级别 | 峰值状态 | 首次劣化 |', '| --- | --- | --- | --- |')
    for (const p of services) {
      lines.push(`| ${mdCell(p.label)} | ${CRITICALITY_LABELS[p.criticality] || p.criticality} | ${label(p.worstStatus)} | T+${p.firstBadTick} |`)
    }
  } else {
    lines.push('（无业务受影响）')
  }
  lines.push('')

  lines.push('## 资产峰值预测', '')
  if (sortedPeaks.length) {
    lines.push('| 资产 | 类型 | 峰值状态 | 首次劣化 |', '| --- | --- | --- | --- |')
    for (const p of sortedPeaks) {
      lines.push(`| ${mdCell(p.label)} | ${ASSET_KIND_LABELS[p.kind] || p.kind} | ${label(p.worstStatus)} | T+${p.firstBadTick} |`)
    }
  } else {
    lines.push('（无资产劣化）')
  }
  lines.push('')

  if (s.cascadingSteps?.length) {
    lines.push('## 级联步骤', '')
    s.cascadingSteps.forEach((step, i) => {
      lines.push(`${i + 1}. \`T+${step.tick}\` ${step.text}`)
    })
    lines.push('')
  }

  if (s.recommendation) lines.push('## 规避建议', '', s.recommendation, '')
  return lines.join('\n')
}

/** 状态胶囊：颜色复用 STATUS_COLORS，背景用同色低透明度，保证打印时仍可辨读。 */
function statusChip(status) {
  const color = STATUS_COLORS[status] || '#94a3b8'
  return `<span class="chip" style="background:${color}1f;border-color:${color}">${escHtml(STATUS_LABELS[status] || status)}</span>`
}

/**
 * 生成「操作失误演练报告」自包含 HTML（内联样式、无外部资源、无脚本），
 * 既可直接下载归档，也可在新窗口打印 / 另存为 PDF。
 * 与 buildDrillReport 共用 reportModel，保证两种导出物的排序与口径一致。
 * @param {object} op 操作目录条目
 * @param {object} prediction predictConsequences 的返回值
 * @param {Array} peaks predictAssetPeaks 的返回值
 * @param {string} [generatedAt] 生成时间文本（调用方格式化）
 * @returns {string} 完整 HTML 文档；缺少操作或预测时返回空串
 */
export function buildDrillReportHtml(op, prediction, peaks, generatedAt = '') {
  const model = reportModel(op, prediction, peaks)
  if (!model) return ''
  const { summary: s, sortedPeaks, services } = model

  const serviceRows = services.length
    ? services.map(p => `<tr><td>${escHtml(p.label)}</td><td>${escHtml(CRITICALITY_LABELS[p.criticality] || p.criticality)}</td><td>${statusChip(p.worstStatus)}</td><td>T+${escHtml(p.firstBadTick)}</td></tr>`).join('')
    : '<tr><td colspan="4" class="muted">（无业务受影响）</td></tr>'
  const assetRows = sortedPeaks.length
    ? sortedPeaks.map(p => `<tr><td>${escHtml(p.label)}</td><td>${escHtml(ASSET_KIND_LABELS[p.kind] || p.kind)}</td><td>${statusChip(p.worstStatus)}</td><td>T+${escHtml(p.firstBadTick)}</td></tr>`).join('')
    : '<tr><td colspan="4" class="muted">（无资产劣化）</td></tr>'
  const stepItems = (s.cascadingSteps || [])
    .map(step => `<li><span class="tick">T+${escHtml(step.tick)}</span>${escHtml(step.text)}</li>`)
    .join('')

  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>操作失误演练报告 · ${escHtml(op.cn)}</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 32px 40px 48px; background: #fff; color: #1f2937;
    font: 14px/1.65 "PingFang SC", "Microsoft YaHei", -apple-system, "Segoe UI", sans-serif; }
  .report { max-width: 880px; margin: 0 auto; }
  .eyebrow { margin: 0 0 4px; font-size: 11px; letter-spacing: .16em; color: #0ea5e9; font-weight: 600; }
  h1 { margin: 0 0 8px; font-size: 24px; }
  h2 { margin: 26px 0 10px; font-size: 16px; border-left: 3px solid #0ea5e9; padding-left: 8px; }
  .badge { display: inline-block; margin-right: 6px; padding: 2px 9px; border-radius: 999px; font-size: 11px;
    color: #0c4a6e; background: #e0f2fe; border: 1px solid #7dd3fc; }
  .disclaimer { margin: 8px 0 0; color: #b45309; font-size: 12px; }
  .print-tip { margin: 6px 0 0; font-size: 12px; color: #64748b; }
  .meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 24px;
    margin: 14px 0 0; padding: 12px 16px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; }
  .meta div { display: flex; gap: 8px; }
  .meta dt { color: #64748b; min-width: 72px; }
  .meta dd { margin: 0; font-weight: 600; }
  .kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .kpi { padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; }
  .kpi b { display: block; font-size: 20px; line-height: 1.2; }
  .kpi span { font-size: 11px; color: #64748b; }
  .muted { color: #94a3b8; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 7px 10px; border-bottom: 1px solid #e2e8f0; text-align: left; }
  th { color: #475569; background: #f8fafc; font-weight: 600; }
  .chip { display: inline-block; padding: 1px 8px; border: 1px solid; border-radius: 999px; font-size: 12px; color: #1f2937; }
  ol.steps { margin: 0; padding-left: 20px; }
  ol.steps li { margin: 4px 0; }
  .tick { display: inline-block; margin-right: 8px; padding: 0 6px; border-radius: 4px; background: #f1f5f9;
    color: #0f172a; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
  .advice { margin-top: 26px; padding: 12px 16px; border: 1px solid #fde68a; border-radius: 8px; background: #fffbeb; }
  .advice h2 { margin-top: 0; border-left-color: #f59e0b; }
  footer { margin-top: 28px; padding-top: 10px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 11px; }
  @media print {
    @page { size: A4; margin: 14mm; }
    body { padding: 0; font-size: 12px; }
    .print-tip { display: none; }
    h2 { break-after: avoid; }
    table, .kpis, .meta, .advice { break-inside: avoid; }
  }
</style>
</head>
<body>
<div class="report">
  <header>
    <p class="eyebrow">SENTINEL · VIRTUAL OPS SANDBOX</p>
    <h1>操作失误演练报告 · ${escHtml(op.cn)}</h1>
    <p><span class="badge">预测态</span><span class="badge">演示虚拟数据</span></p>
    <p class="disclaimer">本报告由虚拟环境确定性推演生成，仅用于演练与风险教育，不作为真实变更决策依据。</p>
    <p class="print-tip">提示：在浏览器打印对话框中可选择「另存为 PDF」。</p>
  </header>
  <dl class="meta">
    ${generatedAt ? `<div><dt>生成时间</dt><dd>${escHtml(generatedAt)}</dd></div>` : ''}
    <div><dt>操作编号</dt><dd>${escHtml(op.id)}</dd></div>
    <div><dt>目标资产</dt><dd>${escHtml(op.targetId)}（${escHtml(op.label)}）</dd></div>
    <div><dt>风险等级</dt><dd>${op.risk === 'high' ? '高风险' : '中风险'}</dd></div>
    <div><dt>推演步数</dt><dd>${escHtml(s.horizon)} 步（T+0 为操作注入时刻）</dd></div>
  </dl>

  <h2>峰值后果</h2>
  <div class="kpis">
    <div class="kpi"><b>${escHtml(s.maxSeverityLabel)}</b><span>最高严重度</span></div>
    <div class="kpi"><b>${escHtml(s.slaRiskLabel)}</b><span>SLA 风险</span></div>
    <div class="kpi"><b>${escHtml(s.estimatedOutageMinutes)} 分</b><span>预估中断时长</span></div>
    <div class="kpi"><b>${escHtml(s.affectedServiceCount)}</b><span>受影响业务（中断 ${escHtml(s.downServices)}）</span></div>
  </div>
  <p class="muted">受影响机柜 ${escHtml(s.affectedRackCount)}（中断 ${escHtml(s.downRacks)}） · 受影响网络设备 ${escHtml(s.affectedNetworkCount)} · 中断链路 ${escHtml(s.downLinks)}</p>

  <h2>受影响业务（预测峰值）</h2>
  <table>
    <thead><tr><th>业务</th><th>重要级别</th><th>峰值状态</th><th>首次劣化</th></tr></thead>
    <tbody>${serviceRows}</tbody>
  </table>

  <h2>资产峰值预测</h2>
  <table>
    <thead><tr><th>资产</th><th>类型</th><th>峰值状态</th><th>首次劣化</th></tr></thead>
    <tbody>${assetRows}</tbody>
  </table>

  ${stepItems ? `<h2>级联步骤</h2><ol class="steps">${stepItems}</ol>` : ''}

  ${s.recommendation ? `<section class="advice"><h2>规避建议</h2><p>${escHtml(s.recommendation)}</p></section>` : ''}

  <footer>由智维Agent / SmartOpsAgent · 虚拟运维场景生成 · 数据为演示虚拟数据</footer>
</div>
</body>
</html>`
}
