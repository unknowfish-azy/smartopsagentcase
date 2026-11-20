/**
 * 蜘蛛机器人（SPIDER）rig：8 足 16 关节由真实位移速度驱动，与机器狗同一条数据链路。
 *
 * - 步态：rigs/gait.js 的 spiderPose（偶数腿 / 奇数腿反相，摆动相抬腿），速度归零即站立；
 * - 真机遥测 telemetry.joints（{关节名: 弧度}）存在时按绝对角直驱并夹紧到 range；
 * - 状态灯 / LiDAR / 扫描环 / stale 半透明复用 rigs/effectLayer.js；
 * - 模型尺寸按 ROBOT_DISPLAY_FOOTPRINT 归一；
 * - GLB 缺失时用 models/spiderBotModel.js 现场构建同款几何。
 */

import { Group, Vector3 } from 'three'
import { BEACON_STATUS, resolveBeaconStatus, resolveEffectConfig } from './effects.js'
import { buildEffectLayer, measureRobotBounds, normalizeRobotFootprint } from './effectLayer.js'
import { buildSpiderBotModel, buildSpiderRigMeta, SPIDER_LEG_COUNT, SPIDER_SENSOR_NODE } from '../models/spiderBotModel.js'

const FX_ORIGIN = { position: { x: 0, z: 0 }, rotation: { y: 0 } }
const DAMPING = 10

/**
 * @param {{gltf?: object, metadata?: object, accentHex?: number, effects?: object, theme?: string}} options
 */
export function createSpiderRig({ gltf, metadata, accentHex = 0x5b8cff, effects, theme = 'light' } = {}) {
  const built = gltf ? null : buildSpiderBotModel()
  const modelRoot = gltf?.scene ?? built.root
  normalizeRobotFootprint(modelRoot)

  const group = new Group()
  group.name = 'spider-rig'
  group.add(modelRoot)

  const meta = metadata || buildSpiderRigMeta()
  const jointsMeta = meta.joints || {}
  const joints = {}
  for (const [name, def] of Object.entries(jointsMeta)) {
    const node = modelRoot.getObjectByName(def.node || name)
    if (!node) continue
    const axis = new Vector3(...(def.axis || [0, 1, 0]))
    if (axis.lengthSq() < 1e-12) continue
    joints[name] = {
      node,
      axis: axis.normalize(),
      home: Number(def.home) || 0,
      range: Array.isArray(def.range) ? def.range : null,
      current: Number(def.home) || 0
    }
  }
  /* 关节名固定为 Leg{i}_hip / Leg{i}_knee，按索引把 spiderPose 的增量叠加到站立角上 */
  const legs = []
  for (let i = 0; i < SPIDER_LEG_COUNT; i += 1) {
    legs.push({ hip: joints[`Leg${i}_hip`], knee: joints[`Leg${i}_knee`] })
  }

  const sensorNode = modelRoot.getObjectByName(meta.sensor?.node || SPIDER_SENSOR_NODE)
  const sensorAxis = new Vector3(...(meta.sensor?.axis || [0, 1, 0])).normalize()

  const materials = []
  const eyeMats = []
  modelRoot.traverse((node) => {
    if (!node.material) return
    if (!materials.includes(node.material)) materials.push(node.material)
    if (/HeadLamp/.test(node.name || '') && !eyeMats.includes(node.material)) eyeMats.push(node.material)
  })

  let fx = resolveEffectConfig(effects)
  const fxLayer = buildEffectLayer({ accentHex, effects, bounds: measureRobotBounds(modelRoot), theme })
  group.add(fxLayer.group)
  fxLayer.sync(FX_ORIGIN)

  let sensorSpin = 0
  let staleApplied = false
  let beaconStatus = { key: 'idle', ...BEACON_STATUS.idle }
  let jointSource = 'gait'

  function clampRange(joint, value) {
    if (!joint.range) return value
    return Math.min(joint.range[1], Math.max(joint.range[0], value))
  }

  function update({ dt = 0.016, pose, joints: telemetryJoints } = {}) {
    const k = 1 - Math.exp(-DAMPING * Math.max(0, Math.min(dt, 0.1)))
    const targets = {}
    if (pose?.legs) {
      for (let i = 0; i < legs.length; i += 1) {
        const p = pose.legs[i]
        if (!p) continue
        if (legs[i].hip) targets[`Leg${i}_hip`] = legs[i].hip.home + p.hip
        if (legs[i].knee) targets[`Leg${i}_knee`] = legs[i].knee.home + p.knee
      }
    }
    let usedTelemetry = false
    if (telemetryJoints && typeof telemetryJoints === 'object') {
      for (const [name, value] of Object.entries(telemetryJoints)) {
        if (!joints[name] || !Number.isFinite(value)) continue
        targets[name] = value /* 真机绝对角直接覆盖，不经步态映射 */
        usedTelemetry = true
      }
    }
    jointSource = usedTelemetry ? 'telemetry' : 'gait'
    for (const [name, joint] of Object.entries(joints)) {
      const target = clampRange(joint, targets[name] ?? joint.home)
      joint.current += (target - joint.current) * k
      joint.node.quaternion.setFromAxisAngle(joint.axis, joint.current)
    }
    sensorSpin += dt * (beaconStatus.source === 'alarm' ? fx.lidarAlarmSpeed : fx.lidarSpeed)
    if (sensorNode) sensorNode.quaternion.setFromAxisAngle(sensorAxis, sensorSpin)
    fxLayer.sync(FX_ORIGIN)
    fxLayer.update({ dt })
  }

  function setStale(stale) {
    if (stale === staleApplied) return
    staleApplied = stale
    materials.forEach((m) => {
      m.transparent = true
      m.opacity = stale ? 0.3 : 1
    })
    fxLayer.setStale(stale)
  }

  function setBeaconStatus(input) {
    const next = resolveBeaconStatus(input)
    if (next.key !== beaconStatus.key) {
      beaconStatus = next
      const hex = next.source === 'alarm' ? 0xe5484d : 0x1c5a37
      eyeMats.forEach((m) => m.emissive?.setHex(hex))
    }
    fxLayer.setBeaconStatus(input)
  }

  function setEffects(next) {
    fx = resolveEffectConfig(next)
    fxLayer.setEffects(next)
  }

  function setTheme(next) {
    fxLayer.setTheme(next)
  }

  function dispose() {
    modelRoot.traverse((node) => {
      node.geometry?.dispose?.()
      node.material?.dispose?.()
    })
    fxLayer.dispose()
  }

  return {
    kind: 'arachnid',
    group,
    jointCount: Object.keys(joints).length,
    update,
    setStale,
    setBeaconStatus,
    setEffects,
    setTheme,
    getJointSource: () => jointSource,
    dispose
  }
}
