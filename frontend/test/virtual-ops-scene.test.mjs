// 虚拟运维场景 / 后果预测数据层单测：确定性、级联传导、边界与汇总口径。
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  DEFAULT_HORIZON,
  OPERATION_CATALOG,
  STATUS_COLORS,
  STATUS_RANK,
  TEMP_THRESHOLDS,
  baselineState,
  buildDrillReport,
  buildDrillReportHtml,
  buildVirtualTopology,
  hashUnit,
  operationById,
  predictAssetPeaks,
  predictConsequences,
  snapshotAt,
  stepState,
  summarize,
  tempLevel,
  worstStatus
} from '../src/domain/sentinel/virtualOpsScene.js'

test('buildVirtualTopology：拓扑规模与对称排布确定', () => {
  const topo = buildVirtualTopology()
  assert.equal(topo.racks.length, 12)
  assert.equal(topo.switches.length, 4)
  assert.equal(topo.routers.length, 2)
  assert.equal(topo.gateways.length, 1)
  assert.equal(topo.coolers.length, 2)
  assert.equal(topo.services.length, 8)
  // 链路：12 条接入 + 4 条核心-TOR + 4 条核心-路由器全互联 + 2 条路由器-网关 = 22
  assert.equal(topo.links.length, 22)
  // 两排关于原点对称
  const row0 = topo.racks.filter(r => r.row === 0)
  assert.ok(row0.every(r => r.z < 0))
  assert.equal(row0[0].x, -row0[row0.length - 1].x)
  // 服务的机架引用都存在
  for (const svc of topo.services) {
    assert.ok(topo.racks.some(r => r.id === svc.rackId), `${svc.id} 引用了不存在的机架`)
  }
  // 链路两端都能在拓扑里找到对应设备
  const deviceIds = new Set([
    ...topo.racks.map(r => r.id),
    ...topo.switches.map(s => s.id),
    ...topo.routers.map(r => r.id),
    ...topo.gateways.map(g => g.id)
  ])
  for (const link of topo.links) {
    assert.ok(deviceIds.has(link.from), `${link.id} 的 from 不存在`)
    assert.ok(deviceIds.has(link.to), `${link.id} 的 to 不存在`)
  }
})

test('OPERATION_CATALOG：每个操作的目标资产都存在于拓扑', () => {
  const topo = buildVirtualTopology()
  const ids = new Set([
    ...topo.racks.map(r => r.id),
    ...topo.switches.map(s => s.id),
    ...topo.routers.map(r => r.id),
    ...topo.gateways.map(g => g.id),
    ...topo.coolers.map(c => c.id),
    ...topo.links.map(l => l.id),
    ...topo.services.map(s => s.id)
  ])
  assert.equal(OPERATION_CATALOG.length, 15)
  for (const op of OPERATION_CATALOG) {
    assert.ok(ids.has(op.targetId), `${op.id} 目标 ${op.targetId} 不在拓扑中`)
    assert.ok(['high', 'medium'].includes(op.risk))
    assert.ok(op.cn && op.description && op.consequenceBrief && op.mitigation)
  }
  assert.equal(operationById('rack-power-off')?.cn, '误关机柜电源')
  assert.equal(operationById('stp-loop')?.cn, '误关 STP 致环路')
  assert.equal(operationById('ospf-flap')?.cn, 'OSPF 邻居频繁抖动')
  assert.equal(operationById('optical-attenuation')?.targetId, 'link-SW-CORE-1-SW-TOR-A')
  assert.equal(operationById('firewall-misconfig')?.risk, 'high')
  assert.equal(operationById('db-config-delete')?.targetId, 'svc-db')
  assert.deepEqual(operationById('batch-reboot')?.targetIds, ['R2-03', 'R2-04', 'R2-05'])
  assert.equal(operationById('不存在'), null)
})

test('baselineState：全健康、可重放', () => {
  const topo = buildVirtualTopology()
  const a = baselineState(topo)
  const b = baselineState(topo)
  assert.deepEqual(a, b)
  assert.equal(a.tick, 0)
  assert.equal(a.events.length, 0)
  assert.ok(Object.values(a.racks).every(r => r.status === 'ok'))
  assert.ok(Object.values(a.services).every(s => s.status === 'ok'))
})

test('tempLevel / worstStatus：阈值边界正确', () => {
  assert.equal(tempLevel(27.9), 'ok')
  assert.equal(tempLevel(TEMP_THRESHOLDS.warn), 'warn')
  assert.equal(tempLevel(TEMP_THRESHOLDS.critical), 'critical')
  assert.equal(tempLevel(TEMP_THRESHOLDS.shutdown), 'down')
  assert.equal(tempLevel(Number.NaN), 'unknown')
  assert.equal(worstStatus(['ok', 'degraded', 'warn']), 'warn')
  assert.equal(worstStatus(['critical', 'down']), 'down')
  assert.equal(worstStatus([]), 'ok')
})

test('hashUnit：稳定且落在 [0,1)', () => {
  assert.equal(hashUnit('R1-03'), hashUnit('R1-03'))
  assert.notEqual(hashUnit('R1-03'), hashUnit('R1-04'))
  for (let i = 0; i < 40; i += 1) {
    const v = hashUnit(`key-${i}`)
    assert.ok(v >= 0 && v < 1)
  }
})

test('predictConsequences：同一输入可重放（确定性）', () => {
  const topo = buildVirtualTopology()
  const a = predictConsequences(topo, 'rack-power-off')
  const b = predictConsequences(topo, 'rack-power-off')
  assert.deepEqual(a.timeline, b.timeline)
  assert.deepEqual(a.summary, b.summary)
  assert.equal(a.timeline.length, DEFAULT_HORIZON + 1)
})

test('误关机柜电源：目标机架中断，订单服务中断并级联', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'rack-power-off')
  const final = timeline[timeline.length - 1]
  assert.equal(final.racks['R1-03'].powerOff, true)
  assert.equal(final.racks['R1-03'].status, 'down')
  assert.equal(final.services['svc-order'].status, 'down')
  assert.ok(summary.affectedRackCount >= 1)
  assert.ok(summary.downServices >= 1)
  assert.equal(summary.slaRisk, 'high')
  assert.ok(summary.cascadingSteps.length > 0)
  assert.equal(summary.recommendation, operationById('rack-power-off').mitigation)
})

test('误调空调设定：A 区升温，同区机架超温，B 区不受热影响', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'ac-setpoint-raise')
  const final = timeline[timeline.length - 1]
  assert.equal(final.coolers['CRAC-A'].setpoint, 30)
  assert.ok(final.coolers['CRAC-A'].zoneTemp > 26)
  // A 区至少有机架进入预警及以上
  const aRacks = Object.values(final.racks).filter(r => r.zone === 'A')
  assert.ok(aRacks.some(r => STATUS_RANK[r.status] >= STATUS_RANK.warn))
  // B 区空调未动，温度仍正常
  assert.equal(final.coolers['CRAC-B'].setpoint, 22)
  assert.ok(final.coolers['CRAC-B'].zoneTemp < 24)
  assert.ok(summary.hottestRacks.length > 0)
})

test('误关 TOR 端口：A 排机柜网络分区，B 排不受网络影响', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'switch-port-down')
  const final = timeline[timeline.length - 1]
  assert.equal(final.switches['SW-TOR-A'].portDown, true)
  const aRacks = topo.racks.filter(r => r.zone === 'A').map(r => r.id)
  const bRacks = topo.racks.filter(r => r.zone === 'B').map(r => r.id)
  assert.ok(aRacks.every(id => final.racks[id].networkLost))
  assert.ok(bRacks.every(id => !final.racks[id].networkLost))
  // A 排上的服务降级（认证/订单/支付/通知）
  for (const id of ['svc-auth', 'svc-order', 'svc-payment', 'svc-notify']) {
    assert.notEqual(final.services[id].status, 'ok', `${id} 应受网络分区影响`)
  }
  assert.ok(summary.cascadingSteps.length > 0)
})

test('误下发路由：核心黑洞导致全部分区，所有服务降级', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'config-misapply')
  const final = timeline[timeline.length - 1]
  assert.equal(final.switches['SW-CORE-1'].blackhole, true)
  assert.ok(Object.values(final.racks).every(r => r.networkLost))
  assert.ok(Object.values(final.services).every(s => s.status !== 'ok'))
  assert.notEqual(summary.slaRisk, 'none')
})

test('扩缩容失败致过载：目标机架升温，支付服务受影响', () => {
  const topo = buildVirtualTopology()
  const { timeline } = predictConsequences(topo, 'server-overload')
  const final = timeline[timeline.length - 1]
  assert.equal(final.racks['R1-04'].overload, true)
  assert.ok(final.racks['R1-04'].temp > 28)
  assert.notEqual(final.services['svc-payment'].status, 'ok')
})

test('误关 STP 致环路：广播风暴扩散，全网设备严重、服务降级', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'stp-loop')
  const final = timeline[timeline.length - 1]
  // tick 0 关闭 STP，tick 1 起风暴扩散
  assert.equal(timeline[0].broadcastStorm, false)
  assert.ok(timeline[1].broadcastStorm)
  assert.equal(final.switches['SW-TOR-A'].status, 'critical')
  assert.equal(final.routers['RTR-CORE-1'].status, 'critical')
  assert.ok(Object.values(final.services).every(s => s.status !== 'ok'))
  assert.ok(summary.cascadingSteps.some(step => step.text.includes('广播风暴')))
})

test('边缘网关宕机：出口中断，全部服务降级但不中断', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'gateway-down')
  const final = timeline[timeline.length - 1]
  assert.equal(final.gatewayDown, true)
  assert.equal(final.gateways['GW-EDGE'].status, 'down')
  // 出口断 → 所有服务降级（非宕机），路由器也降级
  assert.ok(Object.values(final.services).every(s => s.status === 'degraded'))
  assert.equal(final.routers['RTR-CORE-1'].status, 'degraded')
  assert.equal(summary.downServices, 0)
  assert.notEqual(summary.slaRisk, 'none')
})

test('核心链路中断：A 区仅单链路降级，B 区不受影响', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'link-cut')
  const final = timeline[timeline.length - 1]
  assert.equal(final.links['link-SW-CORE-1-SW-TOR-A'].status, 'down')
  assert.equal(summary.downLinks, 1)
  // 还有 CORE-2 备用链路，A 区不应完全失联
  const aRacks = topo.racks.filter(r => r.zone === 'A').map(r => r.id)
  assert.ok(aRacks.every(id => !final.racks[id].networkLost), 'A 区有备用链路，不应失联')
  // B 区完全正常
  const bRacks = topo.racks.filter(r => r.zone === 'B').map(r => r.id)
  assert.ok(bRacks.every(id => final.racks[id].status === 'ok'))
})

test('路由器误配静态路由：支付/库存被黑洞，其余服务正常', () => {
  const topo = buildVirtualTopology()
  const { timeline } = predictConsequences(topo, 'router-misconfig')
  const final = timeline[timeline.length - 1]
  assert.equal(final.routers['RTR-CORE-1'].blackhole, true)
  assert.equal(final.routeBlackhole['svc-payment'], true)
  assert.equal(final.routeBlackhole['svc-inventory'], true)
  assert.notEqual(final.services['svc-payment'].status, 'ok')
  assert.notEqual(final.services['svc-inventory'].status, 'ok')
  // 未被黑洞的服务仍正常
  assert.equal(final.services['svc-queue'].status, 'ok')
  assert.equal(final.services['svc-notify'].status, 'ok')
})

test('Trunk VLAN 不一致：认证服务被隔离中断，其余正常', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'vlan-mismatch')
  const final = timeline[timeline.length - 1]
  assert.equal(final.vlanIsolated['svc-auth'], true)
  assert.equal(final.services['svc-auth'].status, 'down')
  assert.ok(summary.impactedBusiness.includes('认证服务'))
  assert.equal(summary.slaRisk, 'high')
  // 其他服务未被隔离，保持正常
  for (const id of ['svc-order', 'svc-payment', 'svc-db']) {
    assert.equal(final.services[id].status, 'ok', `${id} 不应受 VLAN 隔离影响`)
  }
})

test('OSPF 邻居抖动：出口间歇性降级，奇数 tick 降级、偶数 tick 恢复', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'ospf-flap')
  const final = timeline[timeline.length - 1]
  assert.equal(final.flappingRouters['RTR-CORE-1'], true)
  assert.equal(summary.intermittent, true)
  assert.equal(summary.flappingRoutersCount, 1)
  // 奇数（坏）tick：路由器与业务降级且标记 transient；偶数（好）tick：恢复正常
  for (let t = 1; t < timeline.length; t += 2) {
    assert.equal(timeline[t].routers['RTR-CORE-1'].status, 'degraded', `tick ${t} 应为坏 tick`)
    assert.equal(timeline[t].services['svc-payment'].status, 'degraded')
    assert.equal(timeline[t].services['svc-payment'].transient, true)
  }
  for (let t = 2; t < timeline.length; t += 2) {
    assert.equal(timeline[t].routers['RTR-CORE-1'].status, 'ok', `tick ${t} 应为好 tick`)
    assert.equal(timeline[t].services['svc-payment'].status, 'ok')
  }
  // 影响面按时间线并集统计，不因末帧恢复而归零；抖动不产生中断
  assert.ok(summary.affectedServiceCount > 0)
  assert.equal(summary.downServices, 0)
})

test('主干光功率衰减：A 区上行路径抖动，A 区服务间歇降级，B 区不受影响', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'optical-attenuation')
  assert.equal(timeline[0].flappingLinks['link-SW-CORE-1-SW-TOR-A'], true)
  assert.equal(summary.intermittent, true)
  assert.equal(summary.flappingLinksCount, 1)
  const aServices = ['svc-auth', 'svc-order', 'svc-payment', 'svc-notify']
  const bServices = ['svc-inventory', 'svc-cache', 'svc-db', 'svc-queue']
  for (let t = 1; t < timeline.length; t += 2) {
    assert.equal(timeline[t].links['link-SW-CORE-1-SW-TOR-A'].status, 'degraded')
    assert.equal(timeline[t].racks['R1-03'].pathFlapping, true)
    for (const id of aServices) {
      assert.equal(timeline[t].services[id].status, 'degraded', `${id} 在坏 tick 应降级`)
    }
  }
  // B 区全程不受影响
  for (let t = 0; t < timeline.length; t += 1) {
    for (const id of bServices) {
      assert.equal(timeline[t].services[id].status, 'ok', `${id} 不应受光功率衰减影响`)
    }
  }
  // 链路未硬断，不计入中断链路
  assert.equal(summary.downLinks, 0)
})

test('防火墙策略误配：支付服务持续降级，订单级联降级，其余业务正常', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'firewall-misconfig')
  const final = timeline[timeline.length - 1]
  assert.equal(final.firewallBlocked['svc-payment'], true)
  assert.equal(final.gateways['GW-EDGE'].status, 'degraded')
  // 非抖动：持续降级，transient 为 false（会向依赖方传导）
  for (let t = 1; t < timeline.length; t += 1) {
    assert.equal(timeline[t].services['svc-payment'].status, 'degraded')
    assert.equal(timeline[t].services['svc-payment'].transient, false)
  }
  // 订单依赖支付，滞后 1 个 tick 级联降级
  assert.equal(timeline[1].services['svc-order'].status, 'ok')
  assert.equal(timeline[2].services['svc-order'].status, 'degraded')
  // 其余业务不受影响
  assert.equal(final.services['svc-auth'].status, 'ok')
  assert.equal(final.services['svc-db'].status, 'ok')
  assert.equal(final.services['svc-queue'].status, 'ok')
  assert.equal(summary.intermittent, false)
  assert.equal(summary.downServices, 0)
  assert.notEqual(summary.slaRisk, 'none')
})

test('snapshotAt：越界钳制到端点', () => {
  const topo = buildVirtualTopology()
  const { timeline } = predictConsequences(topo, 'rack-power-off')
  assert.equal(snapshotAt(timeline, 0).tick, 0)
  assert.equal(snapshotAt(timeline, DEFAULT_HORIZON).tick, DEFAULT_HORIZON)
  assert.equal(snapshotAt(timeline, 999).tick, DEFAULT_HORIZON)
  assert.equal(snapshotAt(timeline, -5).tick, 0)
  assert.equal(snapshotAt([], 0), null)
})

test('stepState：无操作时全健康推演不产生事件', () => {
  const topo = buildVirtualTopology()
  const state = baselineState(topo)
  stepState(state, topo)
  assert.equal(state.tick, 1)
  assert.equal(state.events.length, 0)
  assert.ok(Object.values(state.services).every(s => s.status === 'ok'))
})

test('summarize：无操作时风险为 none、影响为 0', () => {
  const topo = buildVirtualTopology()
  const timeline = [baselineState(topo)]
  const summary = summarize(timeline, null)
  assert.equal(summary.affectedRackCount, 0)
  assert.equal(summary.affectedServiceCount, 0)
  assert.equal(summary.slaRisk, 'none')
  assert.equal(summary.maxSeverity, 'ok')
  assert.equal(summary.estimatedOutageMinutes, 0)
})

test('predictAssetPeaks：全健康基线返回空数组', () => {
  const topo = buildVirtualTopology()
  assert.deepEqual(predictAssetPeaks(topo, [baselineState(topo)]), [])
})

test('predictAssetPeaks：误关机柜时目标机架峰值为中断，且在 T+0 即劣化', () => {
  const topo = buildVirtualTopology()
  const { timeline } = predictConsequences(topo, 'rack-power-off')
  const peaks = predictAssetPeaks(topo, timeline)
  const rack = peaks.find(p => p.id === 'R1-03')
  assert.ok(rack, '目标机架应出现在峰值预测中')
  assert.equal(rack.kind, 'rack')
  assert.equal(rack.worstStatus, 'down')
  assert.equal(rack.firstBadTick, 0) // 操作在 tick 0 注入即中断
})

test('predictAssetPeaks：链路中断目标被标记为 link 峰值', () => {
  const topo = buildVirtualTopology()
  const { timeline } = predictConsequences(topo, 'link-cut')
  const peaks = predictAssetPeaks(topo, timeline)
  const link = peaks.find(p => p.id === 'link-SW-CORE-1-SW-TOR-A')
  assert.ok(link, '被切断的链路应出现在峰值预测中')
  assert.equal(link.kind, 'link')
  assert.equal(link.worstStatus, 'down')
})

test('predictAssetPeaks：前向预测取整段时间窗峰值，不受末帧恢复影响', () => {
  const topo = buildVirtualTopology()
  const { timeline } = predictConsequences(topo, 'ospf-flap')
  // OSPF 抖动为间歇性故障：偶数 tick 路由器恢复为 ok；
  // 若推演窗末帧落在偶数 tick，末帧为 ok，但峰值预测仍应报告 degraded。
  const peaks = predictAssetPeaks(topo, timeline)
  const rtr = peaks.find(p => p.id === 'RTR-CORE-1')
  assert.ok(rtr, '抖动路由器应出现在峰值预测中')
  assert.equal(rtr.worstStatus, 'degraded')
  assert.ok(rtr.firstBadTick >= 1, `首次劣化 tick 应 >= 1，实际 ${rtr.firstBadTick}`)
})

test('STATUS_COLORS：与 STATUS_RANK 同键且为合法 6 位 hex，避免色阶漂移', () => {
  assert.deepEqual(Object.keys(STATUS_COLORS).sort(), Object.keys(STATUS_RANK).sort())
  for (const c of Object.values(STATUS_COLORS)) {
    assert.match(c, /^#[0-9a-fA-F]{6}$/, `色值应为 6 位 hex，实际 ${c}`)
  }
})

test('predictAssetPeaks：业务服务峰值预测附带宿主机架与重要级别', () => {
  const topo = buildVirtualTopology()
  // rack-power-off 目标 R1-03，承载订单服务（core）。
  const { timeline } = predictConsequences(topo, 'rack-power-off')
  const peaks = predictAssetPeaks(topo, timeline)
  const svc = peaks.find(p => p.id === 'svc-order')
  assert.ok(svc, 'R1-03 宕机应导致其承载的订单服务出现在峰值预测中')
  assert.equal(svc.kind, 'service')
  assert.equal(svc.worstStatus, 'down')
  assert.equal(svc.rackId, 'R1-03')
  assert.equal(svc.criticality, 'core')
  assert.ok(svc.firstBadTick >= 0, `首次劣化 tick 应 >= 0，实际 ${svc.firstBadTick}`)
})

test('predictAssetPeaks：全健康基线不产生业务服务预测', () => {
  const topo = buildVirtualTopology()
  const peaks = predictAssetPeaks(topo, [baselineState(topo)])
  assert.equal(peaks.filter(p => p.kind === 'service').length, 0)
})

test('buildDrillReport：缺操作或预测时返回空串（不产出半截报告）', () => {
  assert.equal(buildDrillReport(null, null, []), '')
  assert.equal(buildDrillReport({ cn: 'X' }, null, []), '')
  assert.equal(buildDrillReport(null, { summary: {} }, []), '')
})

test('buildDrillReport：包含操作信息、峰值后果、业务/资产峰值与级联步骤', () => {
  const topo = buildVirtualTopology()
  const op = operationById('rack-power-off')
  const prediction = predictConsequences(topo, 'rack-power-off')
  const peaks = predictAssetPeaks(topo, prediction.timeline)
  const md = buildDrillReport(op, prediction, peaks, '2026-01-01 00:00:00')

  assert.match(md, /^# 操作失误演练报告 · /)
  // 红线声明与生成时间必须出现，避免导出物被当成真实变更依据
  assert.ok(md.includes('不作为真实变更决策依据'))
  assert.ok(md.includes('生成时间：2026-01-01 00:00:00'))
  assert.ok(md.includes('目标资产：R1-03'))
  // 峰值后果表：机柜与业务均中断
  assert.ok(md.includes('| 最高严重度 | 中断 |'))
  assert.ok(md.includes('| 受影响业务 | 1（其中中断 1） |'))
  // 业务峰值表带重要级别与首次劣化时点
  assert.ok(/\| 订单服务 \| 核心 \| 中断 \| T\+\d+ \|/.test(md))
  // 资产峰值与级联步骤
  assert.ok(md.includes('## 资产峰值预测'))
  assert.ok(md.includes('## 级联步骤'))
  assert.ok(/1\. `T\+\d+` /.test(md))
  // 规避建议存在且非空
  assert.ok(md.includes('## 规避建议'))
})

test('误删数据库配置：数据库中断，依赖方滞后级联为交易主链路故障', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'db-config-delete')
  assert.equal(timeline[0].configDeleted['svc-db'], true)
  // T+1 数据库直接中断（配置缺失）
  assert.equal(timeline[1].services['svc-db'].status, 'down')
  // 依赖方滞后 1 个 tick 级联：支付 T+1 仍正常，T+2 中断
  assert.equal(timeline[1].services['svc-payment'].status, 'ok')
  assert.equal(timeline[2].services['svc-payment'].status, 'down')
  // 订单依赖支付，再滞后 1 个 tick
  assert.equal(timeline[2].services['svc-order'].status, 'ok')
  assert.equal(timeline[3].services['svc-order'].status, 'down')
  // 认证 / 库存直接依赖数据库，T+2 中断
  assert.equal(timeline[2].services['svc-auth'].status, 'down')
  assert.equal(timeline[2].services['svc-inventory'].status, 'down')
  // 与数据库无关的通知链路不受影响
  assert.equal(timeline[timeline.length - 1].services['svc-notify'].status, 'ok')
  assert.equal(summary.slaRisk, 'high')
  assert.ok(summary.downServices >= 5)
  assert.ok(summary.cascadingSteps.some(step => step.text.includes('配置被误删')))
})

test('批量重启失误：整批机柜同时中断，重启完成后自行恢复', () => {
  const topo = buildVirtualTopology()
  const { timeline, summary } = predictConsequences(topo, 'batch-reboot', 12)
  const rackIds = ['R2-03', 'R2-04', 'R2-05']
  // T+0 整批机柜进入中断，带重启倒计时
  for (const id of rackIds) {
    assert.equal(timeline[0].racks[id].status, 'down')
    assert.ok(timeline[0].racks[id].rebootRemaining > 0, `${id} 应处于重启窗口内`)
  }
  // 窗口内数据库随之中断
  assert.equal(timeline[2].services['svc-db'].status, 'down')
  // 重启完成后机柜恢复供电与正常状态，业务链随之恢复
  const final = timeline[timeline.length - 1]
  for (const id of rackIds) {
    assert.equal(final.racks[id].powerOff, false)
    assert.equal(final.racks[id].rebootRemaining, 0)
    assert.equal(final.racks[id].status, 'ok')
  }
  assert.equal(final.services['svc-db'].status, 'ok')
  assert.equal(final.services['svc-payment'].status, 'ok')
  assert.equal(final.services['svc-order'].status, 'ok')
  assert.equal(final.services['svc-cache'].status, 'ok')
  // 峰值统计仍记录了窗口内的中断
  assert.ok(summary.downServices > 0)
  assert.ok(summary.estimatedOutageMinutes > 0)
  assert.ok(summary.cascadingSteps.some(step => step.text.includes('重启完成')))
})

test('buildDrillReportHtml：缺操作或预测时返回空串', () => {
  assert.equal(buildDrillReportHtml(null, null, []), '')
  assert.equal(buildDrillReportHtml({ cn: 'X' }, null, []), '')
  assert.equal(buildDrillReportHtml(null, { summary: {} }, []), '')
})

test('buildDrillReportHtml：自包含 HTML 含打印样式、红线声明与转义', () => {
  const topo = buildVirtualTopology()
  const op = operationById('rack-power-off')
  const prediction = predictConsequences(topo, 'rack-power-off')
  const peaks = predictAssetPeaks(topo, prediction.timeline)
  const html = buildDrillReportHtml(op, prediction, peaks, '2026-01-01 00:00:00')

  assert.match(html, /^<!doctype html>/i)
  assert.ok(html.includes('<meta charset="utf-8">'))
  assert.ok(html.includes('@media print'))
  assert.ok(html.includes('不作为真实变更决策依据'))
  assert.ok(html.includes('生成时间'))
  assert.ok(html.includes('订单服务'))
  assert.ok(/T\+\d+/.test(html))
  // 无外部资源、无脚本：可离线归档并安全打印
  assert.ok(!/<script/i.test(html))
  assert.ok(!/https?:\/\//i.test(html))
  // 资产名必须转义，避免导出物成为注入载体
  const evil = [...peaks, { id: 'x', label: '<img src=x onerror=alert(1)>', kind: 'rack', worstStatus: 'down', firstBadTick: 0 }]
  const escaped = buildDrillReportHtml(op, prediction, evil, '')
  assert.ok(!escaped.includes('<img src=x'))
  assert.ok(escaped.includes('&lt;img src=x'))
})
