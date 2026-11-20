/**
 * 宇树官方 GLB 模型 rig：与程序化 rig（quadrupedRig / humanoidRig）同一接口，
 * 把 gait.js 的步态角或真机绝对关节角驱动到官方模型的命名关节节点上。
 *
 * 关节数据源（诚实原则）：
 * - 真机遥测 telemetry.joints（{关节名: 弧度}，与宇树 SDK 电机名一致）优先，按绝对角驱动；
 * - 未覆盖的关节回退步态推算（增量叠加官方 home 姿态），getJointSource() 如实标注；
 * - 心跳超时由调用方清空 joints 并将速度归零，本 rig 自然回到官方站立姿态，不做假动作。
 *
 * 动效：状态灯 / LiDAR / 扫描环复用 effectLayer（挂在 rig 容器内原点，随本体移动），
 * 与 CAR / SPIDER 的 GLB 形态及两种程序化 rig 视觉一致。
 */

import { Group, Vector3 } from 'three'
import { buildEffectLayer, measureRobotBounds } from './effectLayer.js'
import { g1JointTargets, go2JointTargets } from './unitreeJointMap.js'

const DAMPING = 10
/* fxLayer.sync 读取本体的 position.x/z 与 rotation.y；动效层挂在 rig 容器内，
   用恒零替身让其留在容器原点，由容器自身的位姿插值带动，避免双重位移。 */
const FX_ORIGIN = { position: { x: 0, z: 0 }, rotation: { y: 0 } }

/**
 * @param {{kind: 'quadruped'|'humanoid', gltf: object, metadata: object,
 *   accentHex?: number, effects?: object, theme?: string}} options
 */
export function createUnitreeGlbRig({ kind, gltf, metadata, accentHex = 0x5b8cff, effects, theme = 'light' }) {
  const group = new Group()
  const body = new Group()
  body.name = `unitree-${kind}-body`
  group.add(body)
  body.add(gltf.scene)

  const mapTargets = kind === 'quadruped' ? go2JointTargets : g1JointTargets
  const jointsMeta = metadata?.joints || {}
  const joints = {}
  for (const [name, meta] of Object.entries(jointsMeta)) {
    const node = gltf.scene.getObjectByName(meta.node || name)
    if (!node) continue
    const axis = new Vector3(...(meta.axis || [0, 1, 0]))
    if (axis.lengthSq() < 1e-12) continue
    joints[name] = {
      node,
      axis: axis.normalize(),
      home: Number(meta.home) || 0,
      range: Array.isArray(meta.range) ? meta.range : null,
      current: Number(meta.home) || 0
    }
  }

  /* 材质清单：stale 半透明只在状态切换帧写入 */
  const modelMaterials = []
  gltf.scene.traverse((node) => {
    if (node.material && !modelMaterials.includes(node.material)) modelMaterials.push(node.material)
  })

  const fxLayer = buildEffectLayer({
    accentHex, effects, bounds: measureRobotBounds(body), theme
  })
  group.add(fxLayer.group)
  fxLayer.sync(FX_ORIGIN)

  let jointSource = 'gait'
  let staleApplied = false

  function clampRange(joint, value) {
    if (!joint.range) return value
    return Math.min(joint.range[1], Math.max(joint.range[0], value))
  }

  function update({ dt = 0.016, pose, joints: telemetryJoints } = {}) {
    const k = 1 - Math.exp(-DAMPING * Math.max(0, Math.min(dt, 0.1)))
    const targets = pose ? mapTargets(pose, jointsMeta) : {}
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
    if (pose?.body && kind === 'quadruped') {
      body.position.y = pose.body.bob || 0
      body.rotation.z = pose.body.pitch || 0
    } else if (pose?.torso) {
      body.position.y = pose.torso.bob || 0
    }
    fxLayer.sync(FX_ORIGIN)
    fxLayer.update({ dt })
  }

  function setStale(stale) {
    if (stale === staleApplied) return
    staleApplied = stale
    for (const m of modelMaterials) {
      m.transparent = stale
      m.opacity = stale ? 0.3 : 1
    }
    fxLayer.setStale(stale)
  }

  function dispose() {
    gltf.scene.traverse((node) => {
      node.geometry?.dispose?.()
      node.material?.dispose?.()
    })
    fxLayer.dispose()
  }

  return {
    kind,
    group,
    jointCount: Object.keys(joints).length,
    update,
    setStale,
    setBeaconStatus: fxLayer.setBeaconStatus,
    setEffects: fxLayer.setEffects,
    setTheme: fxLayer.setTheme,
    getJointSource: () => jointSource,
    dispose
  }
}
