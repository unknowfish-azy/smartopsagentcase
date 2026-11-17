/**
 * 仿宇树 G1 人形机器人 —— 程序化 rig（无 GLB 依赖），用于 ROBOT 形态。
 *
 * 结构：
 *   group
 *   └ pelvis（重心起伏）
 *       ├ 髋部 + 背包电池
 *       ├ torso（胸部 + 肩 + 头，yaw 摆动）
 *       ├ 2 × arm（肩球 → 上臂 → 肘球 → 前臂 → 夹爪）
 *       └ 2 × leg（髋 → 大腿 → 膝 → 小腿 → 足）
 *
 * 关节角来自 rigs/gait.js 的 humanoidPose。
 */

import {
  AdditiveBlending, BoxGeometry, CircleGeometry, CylinderGeometry, DoubleSide, Group, Mesh,
  MeshBasicMaterial, MeshStandardMaterial, RingGeometry, SphereGeometry, TorusGeometry
} from 'three'
import { beaconPulse, resolveEffectConfig, scanRing } from './effects.js'

const HIP_Y = 0.53
const THIGH_LEN = 0.24
const CALF_LEN = 0.23
const TORSO_H = 0.34
const SHOULDER_Y = 0.33
const UPPER_ARM = 0.2
const FOREARM = 0.19

const DAMPING = 10

function dampingFactor(dt) {
  return 1 - Math.exp(-DAMPING * Math.max(0, Math.min(dt, 0.1)))
}

export function buildHumanoidRig({ accentHex = 0x5b8cff, darkHex = 0x22262e, effects } = {}) {
  let fx = resolveEffectConfig(effects)
  const group = new Group()
  const pelvis = new Group()
  pelvis.position.y = HIP_Y
  group.add(pelvis)

  const shellMat = new MeshStandardMaterial({
    color: 0xb9c0cc, metalness: 0.6, roughness: 0.4, transparent: true, opacity: 1
  })
  const jointMat = new MeshStandardMaterial({
    color: darkHex, metalness: 0.55, roughness: 0.5, transparent: true, opacity: 1
  })
  const accentMat = new MeshStandardMaterial({
    color: accentHex, metalness: 0.35, roughness: 0.42, transparent: true, opacity: 1
  })
  const visorMat = new MeshStandardMaterial({
    color: 0x101216, metalness: 0.9, roughness: 0.12, transparent: true, opacity: 1
  })
  const beaconMat = new MeshStandardMaterial({
    color: 0x5ad691, emissive: 0x1c5a37, emissiveIntensity: 1.4, transparent: true, opacity: 1
  })
  const materials = [shellMat, jointMat, accentMat, visorMat, beaconMat]

  /* ---------- 髋 / 背包 ---------- */
  const hipBlock = new Mesh(new BoxGeometry(0.16, 0.12, 0.22), jointMat)
  pelvis.add(hipBlock)

  const battery = new Mesh(new BoxGeometry(0.1, 0.18, 0.14), accentMat)
  battery.position.set(-0.12, 0.1, 0)
  pelvis.add(battery)

  /* ---------- 躯干 + 头 ---------- */
  const torso = new Group()
  torso.position.y = 0.06
  pelvis.add(torso)

  const chest = new Mesh(new BoxGeometry(0.2, TORSO_H, 0.26), shellMat)
  chest.position.y = TORSO_H / 2
  torso.add(chest)

  const chestPlate = new Mesh(new BoxGeometry(0.02, TORSO_H * 0.6, 0.18), accentMat)
  chestPlate.position.set(0.104, TORSO_H * 0.55, 0)
  torso.add(chestPlate)

  const neck = new Mesh(new CylinderGeometry(0.026, 0.03, 0.05, 10), jointMat)
  neck.position.y = TORSO_H + 0.02
  torso.add(neck)

  const head = new Group()
  head.position.y = TORSO_H + 0.1
  torso.add(head)

  const skull = new Mesh(new BoxGeometry(0.13, 0.125, 0.15), shellMat)
  head.add(skull)

  const visor = new Mesh(new BoxGeometry(0.012, 0.05, 0.105), visorMat)
  visor.position.set(0.066, 0.006, 0)
  head.add(visor)

  const beacon = new Mesh(new SphereGeometry(0.014, 12, 10), beaconMat)
  beacon.position.set(0.045, 0.05, 0.045)
  head.add(beacon)

  /* 头顶 LiDAR：半球罩 + 扫描环 + 旋转激光楔形（与四足同款扫描语言） */
  const lidar = new Group()
  lidar.position.set(-0.02, 0.072, 0)
  head.add(lidar)

  const lidarDome = new Mesh(new SphereGeometry(0.04, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2), visorMat)
  lidar.add(lidarDome)

  const lidarRing = new Mesh(new TorusGeometry(0.034, 0.005, 8, 18), accentMat)
  lidarRing.rotation.x = Math.PI / 2
  lidarRing.position.y = 0.009
  lidar.add(lidarRing)

  const sweepMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.24, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const sweep = new Mesh(new CircleGeometry(0.22, 20, -Math.PI / 8, Math.PI / 4), sweepMat)
  sweep.rotation.x = -Math.PI / 2
  sweep.position.y = 0.005
  lidar.add(sweep)

  /* ---------- 手臂 ---------- */
  const shoulderGeo = new SphereGeometry(0.042, 12, 10)
  const upperGeo = new BoxGeometry(0.048, UPPER_ARM, 0.048)
  const foreGeo = new BoxGeometry(0.042, FOREARM, 0.042 )
  const elbowGeo = new SphereGeometry(0.032, 10, 8)
  const handGeo = new BoxGeometry(0.05, 0.05, 0.07)

  const arms = {}
  for (const side of ['L', 'R']) {
    const sign = side === 'L' ? 1 : -1
    const shoulder = new Group()
    shoulder.position.set(0, SHOULDER_Y, sign * 0.14)
    torso.add(shoulder)
    shoulder.add(new Mesh(shoulderGeo, jointMat))

    const upperPivot = new Group()
    shoulder.add(upperPivot)

    const upper = new Mesh(upperGeo, shellMat)
    upper.position.y = -UPPER_ARM / 2
    upperPivot.add(upper)

    const elbow = new Mesh(elbowGeo, accentMat)
    elbow.position.y = -UPPER_ARM
    upperPivot.add(elbow)

    const forePivot = new Group()
    forePivot.position.y = -UPPER_ARM
    upperPivot.add(forePivot)

    const fore = new Mesh(foreGeo, jointMat)
    fore.position.y = -FOREARM / 2
    forePivot.add(fore)

    const hand = new Mesh(handGeo, shellMat)
    hand.position.y = -FOREARM - 0.028
    forePivot.add(hand)

    arms[side] = { upperPivot, forePivot }
  }

  /* ---------- 双腿 ---------- */
  const thighGeo = new BoxGeometry(0.075, THIGH_LEN, 0.085)
  const calfGeo = new BoxGeometry(0.062, CALF_LEN, 0.07)
  const hipGeo = new SphereGeometry(0.048, 12, 10)
  const kneeGeo = new SphereGeometry(0.038, 10, 8)
  const footGeo = new BoxGeometry(0.16, 0.05, 0.09)

  const legs = {}
  for (const side of ['L', 'R']) {
    const sign = side === 'L' ? 1 : -1
    const hip = new Group()
    hip.position.set(0, -0.04, sign * 0.078)
    pelvis.add(hip)
    hip.add(new Mesh(hipGeo, jointMat))

    const thighPivot = new Group()
    hip.add(thighPivot)

    const thigh = new Mesh(thighGeo, shellMat)
    thigh.position.y = -THIGH_LEN / 2
    thighPivot.add(thigh)

    const knee = new Mesh(kneeGeo, accentMat)
    knee.position.y = -THIGH_LEN
    thighPivot.add(knee)

    const calfPivot = new Group()
    calfPivot.position.y = -THIGH_LEN
    thighPivot.add(calfPivot)

    const calf = new Mesh(calfGeo, jointMat)
    calf.position.y = -CALF_LEN / 2
    calfPivot.add(calf)

    const footPivot = new Group()
    footPivot.position.y = -CALF_LEN
    calfPivot.add(footPivot)

    const foot = new Mesh(footGeo, shellMat)
    foot.position.set(0.035, -0.025, 0)
    footPivot.add(foot)

    legs[side] = { thighPivot, calfPivot, footPivot }
  }

  /* ---------- 地面扫描环 ---------- */
  const scanRingMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.35, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const scanRingGeo = new RingGeometry(0.38, 0.5, 48)
  scanRingGeo.rotateX(-Math.PI / 2)
  const scanRingMesh = new Mesh(scanRingGeo, scanRingMat)
  scanRingMesh.position.y = 0.006
  group.add(scanRingMesh)

  /* ---------- 运行时 ---------- */
  let staleApplied = false
  let alarmApplied = false
  let lidarSpin = 0
  let elapsed = 0
  const state = {
    legs: { L: { thigh: 0, calf: 0.06, foot: 0 }, R: { thigh: 0, calf: 0.06, foot: 0 } },
    arms: { L: { upper: 0, fore: 0.3 }, R: { upper: 0, fore: 0.3 } },
    torso: { bob: 0, yaw: 0 }
  }

  function update({ dt = 0.016, pose } = {}) {
    const k = dampingFactor(dt)
    if (pose) {
      for (const side of ['L', 'R']) {
        const lp = pose.legs?.[side]
        if (lp) {
          const s = state.legs[side]
          s.thigh += (lp.thigh - s.thigh) * k
          s.calf += (lp.calf - s.calf) * k
          s.foot += (lp.foot - s.foot) * k
          legs[side].thighPivot.rotation.z = s.thigh
          legs[side].calfPivot.rotation.z = -s.calf
          legs[side].footPivot.rotation.z = s.foot
        }
        const ap = pose.arms?.[side]
        if (ap) {
          const a = state.arms[side]
          a.upper += (ap.upper - a.upper) * k
          a.fore += (ap.fore - a.fore) * k
          arms[side].upperPivot.rotation.z = a.upper
          arms[side].forePivot.rotation.z = -a.fore
        }
      }
      if (pose.torso) {
        state.torso.yaw += ((pose.torso.yaw || 0) - state.torso.yaw) * k
        torso.rotation.y = state.torso.yaw
        pelvis.position.y = HIP_Y + (pose.torso.bob || 0)
      }
    }

    elapsed += dt
    /* LiDAR 扫描：常态匀速，告警加速 */
    lidarSpin += dt * (alarmApplied ? fx.lidarAlarmSpeed : fx.lidarSpeed)
    lidar.rotation.y = lidarSpin
    /* 状态灯呼吸 / 告警闪烁；心跳超时压暗 */
    const pulse = beaconPulse(elapsed, {
      alarm: alarmApplied,
      stale: staleApplied,
      idleHz: fx.beaconIdleHz,
      alarmHz: fx.beaconAlarmHz
    })
    beaconMat.emissiveIntensity = pulse.intensity
    beacon.scale.setScalar(pulse.scale)
    /* 地面扫描环扩散淡出 */
    const wave = scanRing(elapsed, {
      stale: staleApplied,
      period: fx.scanPeriod,
      maxOpacity: fx.ringMaxOpacity,
      staleOpacity: fx.ringStaleOpacity
    })
    scanRingMesh.scale.setScalar(wave.scale)
    scanRingMat.opacity = wave.opacity
  }

  function setStale(stale) {
    if (stale === staleApplied) return
    staleApplied = stale
    materials.forEach((m) => { m.opacity = stale ? 0.3 : 1 })
  }

  function setAlarm(alarm) {
    if (alarm === alarmApplied) return
    alarmApplied = alarm
    beaconMat.color.setHex(alarm ? 0xe5484d : 0x5ad691)
    beaconMat.emissive.setHex(alarm ? 0x7a1418 : 0x1c5a37)
  }

  /** 运行时热更新动效参数（调节面板拖动滑杆时无需重建 rig）。 */
  function setEffects(next) {
    fx = resolveEffectConfig(next)
  }

  function dispose() {
    group.traverse((node) => {
      node.geometry?.dispose?.()
      node.material?.dispose?.()
    })
  }

  return { kind: 'humanoid', group, materials, beaconMat, update, setStale, setAlarm, setEffects, dispose }
}
