/**
 * 巡检车（CAR）rig：轮速由真实位移速度驱动，与机器狗同一条数据链路。
 *
 * - 车轮：线速度 / 轮半径 → 角速度，位移停止（含心跳超时）即停转，不再空转；
 * - LiDAR：与动效层同源转速，告警态加速；
 * - 状态灯 / 扫描环 / stale 半透明复用 rigs/effectLayer.js，与四足、人形一致；
 * - 模型尺寸按 ROBOT_DISPLAY_FOOTPRINT 归一，不再比机器狗小一圈；
 * - GLB 缺失时用 models/patrolCarModel.js 现场构建同款几何。
 */

import { Group, Vector3 } from 'three'
import { BEACON_STATUS, resolveBeaconStatus, resolveEffectConfig } from './effects.js'
import { buildEffectLayer, measureRobotBounds, normalizeRobotFootprint } from './effectLayer.js'
import { buildPatrolCarModel, buildPatrolCarRigMeta, CAR_LIDAR_NODE, CAR_WHEEL_RADIUS } from '../models/patrolCarModel.js'

/* fxLayer.sync 读取本体的 position.x/z 与 rotation.y；动效层挂在 rig 容器内，
   用恒零替身让其留在容器原点，由容器自身位姿插值带动。 */
const FX_ORIGIN = { position: { x: 0, z: 0 }, rotation: { y: 0 } }

/**
 * @param {{gltf?: object, metadata?: object, accentHex?: number, effects?: object, theme?: string}} options
 */
export function createPatrolCarRig({ gltf, metadata, accentHex = 0x5b8cff, effects, theme = 'light' } = {}) {
  const built = gltf ? null : buildPatrolCarModel()
  const modelRoot = gltf?.scene ?? built.root
  normalizeRobotFootprint(modelRoot)

  const group = new Group()
  group.name = 'patrol-car-rig'
  group.add(modelRoot)

  const meta = metadata || buildPatrolCarRigMeta()
  const wheels = []
  for (const def of meta.wheels || []) {
    const node = modelRoot.getObjectByName(def.node)
    if (!node) continue
    const axis = new Vector3(...(def.axis || [0, 0, 1]))
    if (axis.lengthSq() < 1e-12) continue
    wheels.push({
      node,
      side: def.node.endsWith('L') ? 'left' : 'right',
      axis: axis.normalize(),
      radius: Number(def.radius) > 0 ? Number(def.radius) : CAR_WHEEL_RADIUS,
      direction: Number(def.direction) < 0 ? -1 : 1,
      angle: 0
    })
  }

  const lidarNode = modelRoot.getObjectByName(meta.lidar?.node || CAR_LIDAR_NODE)
  const lidarAxis = new Vector3(...(meta.lidar?.axis || [0, 1, 0])).normalize()

  /* 材质清单：stale 只在切换帧写；HeadLamp 材质用于障碍/故障变色 */
  const materials = []
  const lampMats = []
  modelRoot.traverse((node) => {
    if (!node.material) return
    if (!materials.includes(node.material)) materials.push(node.material)
    if (/HeadLamp/.test(node.name || '') && !lampMats.includes(node.material)) lampMats.push(node.material)
  })

  let fx = resolveEffectConfig(effects)
  const fxLayer = buildEffectLayer({ accentHex, effects, bounds: measureRobotBounds(modelRoot), theme })
  group.add(fxLayer.group)
  fxLayer.sync(FX_ORIGIN)

  let lidarSpin = 0
  let staleApplied = false
  let beaconStatus = { key: 'idle', ...BEACON_STATUS.idle }

  function update({ dt = 0.016, speed = 0, wheels: telemetryWheels } = {}) {
    /* 真机轮速遥测优先（左右轮可差速）；缺失时回退到车体线速度统一换算 */
    const leftSpeed = Number(telemetryWheels?.leftSpeed)
    const rightSpeed = Number(telemetryWheels?.rightSpeed)
    const splitDrive = Number.isFinite(leftSpeed) && Number.isFinite(rightSpeed)
    for (const wheel of wheels) {
      const linear = splitDrive ? (wheel.side === 'left' ? leftSpeed : rightSpeed) : (Number(speed) || 0)
      /* 前进（+X）时轮子绕 +Z 反向滚动；速度不变时角度保持不变 */
      wheel.angle += (linear / wheel.radius) * dt * wheel.direction
      wheel.node.quaternion.setFromAxisAngle(wheel.axis, wheel.angle)
    }
    const rpm = Number(telemetryWheels?.lidarRpm)
    const spinSpeed = Number.isFinite(rpm) && rpm > 0
      ? (rpm / 60) * Math.PI * 2
      : (beaconStatus.source === 'alarm' ? fx.lidarAlarmSpeed : fx.lidarSpeed)
    lidarSpin += dt * spinSpeed
    if (lidarNode) lidarNode.quaternion.setFromAxisAngle(lidarAxis, lidarSpin)
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

  /** 告警时前大灯切红，其余状态保持绿色常亮；灯色与状态灯同源。 */
  function setBeaconStatus(input) {
    const next = resolveBeaconStatus(input)
    if (next.key !== beaconStatus.key) {
      beaconStatus = next
      const hex = next.source === 'alarm' ? 0xe5484d : 0x1c5a37
      lampMats.forEach((m) => m.emissive?.setHex(hex))
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
    kind: 'wheeled',
    group,
    wheelCount: wheels.length,
    jointCount: 0,
    update,
    setStale,
    setBeaconStatus,
    setEffects,
    setTheme,
    /* 轮组没有真机绝对角遥测，如实返回 null，由调用方跳过数据源标注 */
    getJointSource: () => null,
    dispose
  }
}
