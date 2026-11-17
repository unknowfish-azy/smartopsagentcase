/**
 * 仿宇树 Go2 四足机器狗 —— 程序化 rig（无 GLB 依赖）。
 *
 * 结构（组层级）：
 *   group
 *   └ torso（重心起伏 / 俯仰）
 *       ├ 机身壳体 + 顶部散热格栅 + 侧板
 *       ├ head（前倾头罩 + 旋转 LiDAR 半球 + 双目相机 + 状态灯）
 *       └ 4 × leg（髋球 → 大腿枢轴 → 膝球 → 小腿枢轴 → 足垫）
 *
 * 关节角由 rigs/gait.js 的 quadrupedPose 提供，本文件只负责几何与阻尼。
 */

import {
  AdditiveBlending, BoxGeometry, CircleGeometry, CylinderGeometry, DoubleSide, Group, Mesh,
  MeshBasicMaterial, MeshStandardMaterial, RingGeometry, SphereGeometry, TorusGeometry
} from 'three'
import { beaconPulse, resolveEffectConfig, scanRing } from './effects.js'

/* 机身尺寸（米级，与真实 Go2 同一量级，方便和 1m 网格对照） */
const BODY = Object.freeze({ length: 0.62, height: 0.115, width: 0.26 })
const BODY_Y = 0.4
const HIP_ATTACH_Y = -0.055
const LEG_ATTACH = Object.freeze({ x: 0.235, z: 0.104 })
const THIGH_LEN = 0.17
const CALF_LEN = 0.17

const DAMPING = 12

function dampingFactor(dt) {
  return 1 - Math.exp(-DAMPING * Math.max(0, Math.min(dt, 0.1)))
}

function lerpAngle(current, target, k) {
  return current + (target - current) * k
}

export function buildQuadrupedRig({ accentHex = 0x5b8cff, darkHex = 0x22262e, effects } = {}) {
  let fx = resolveEffectConfig(effects)
  const group = new Group()
  const torso = new Group()
  torso.position.y = BODY_Y
  group.add(torso)

  const bodyMat = new MeshStandardMaterial({
    color: 0xb9c0cc, metalness: 0.62, roughness: 0.38, transparent: true, opacity: 1
  })
  const panelMat = new MeshStandardMaterial({
    color: darkHex, metalness: 0.5, roughness: 0.55, transparent: true, opacity: 1
  })
  const accentMat = new MeshStandardMaterial({
    color: accentHex, metalness: 0.3, roughness: 0.4, transparent: true, opacity: 1
  })
  const lensMat = new MeshStandardMaterial({
    color: 0x121418, metalness: 0.9, roughness: 0.15, transparent: true, opacity: 1
  })
  const beaconMat = new MeshStandardMaterial({
    color: 0x5ad691, emissive: 0x1c5a37, emissiveIntensity: 1.4, transparent: true, opacity: 1
  })
  const materials = [bodyMat, panelMat, accentMat, lensMat, beaconMat]

  /* ---------- 机身 ---------- */
  const chassis = new Mesh(new BoxGeometry(BODY.length, BODY.height, BODY.width), bodyMat)
  torso.add(chassis)

  /* 顶部壳（略窄，形成层次） */
  const topShell = new Mesh(new BoxGeometry(BODY.length * 0.86, 0.035, BODY.width * 0.8), panelMat)
  topShell.position.y = BODY.height / 2 + 0.016
  torso.add(topShell)

  /* 散热格栅：三条细条 */
  for (let i = -1; i <= 1; i += 1) {
    const grille = new Mesh(new BoxGeometry(0.2, 0.008, 0.012), accentMat)
    grille.position.set(-0.06, BODY.height / 2 + 0.036, i * 0.055)
    torso.add(grille)
  }

  /* 侧板（深色，形成机身分色） */
  for (const side of [-1, 1]) {
    const panel = new Mesh(new BoxGeometry(BODY.length * 0.9, BODY.height * 0.62, 0.012), panelMat)
    panel.position.set(0, -0.004, side * (BODY.width / 2 + 0.002))
    torso.add(panel)
  }

  /* 前保险杠 */
  const bumper = new Mesh(new BoxGeometry(0.03, 0.06, BODY.width * 0.92), panelMat)
  bumper.position.set(BODY.length / 2 + 0.006, -0.012, 0)
  torso.add(bumper)

  /* ---------- 头部 ---------- */
  const head = new Group()
  head.position.set(BODY.length / 2 - 0.03, 0.055, 0)
  torso.add(head)

  const headShell = new Mesh(new BoxGeometry(0.14, 0.1, 0.2), bodyMat)
  headShell.position.x = 0.05
  head.add(headShell)

  const headVisor = new Mesh(new BoxGeometry(0.02, 0.055, 0.16), lensMat)
  headVisor.position.set(0.121, 0.004, 0)
  head.add(headVisor)

  /* LiDAR 半球：绕 Y 轴旋转扫描 */
  const lidar = new Group()
  lidar.position.set(0.045, 0.055, 0)
  const lidarDome = new Mesh(new SphereGeometry(0.052, 18, 12, 0, Math.PI * 2, 0, Math.PI / 2), lensMat)
  lidar.add(lidarDome)
  const lidarRing = new Mesh(new TorusGeometry(0.045, 0.006, 8, 20), accentMat)
  lidarRing.rotation.x = Math.PI / 2
  lidarRing.position.y = 0.012
  lidar.add(lidarRing)

  /* LiDAR 扫描扇面：与 LiDAR 同轴旋转的激光楔形，加色混合避免遮挡本体 */
  const sweepMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.24, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const sweep = new Mesh(new CircleGeometry(0.26, 20, -Math.PI / 8, Math.PI / 4), sweepMat)
  sweep.rotation.x = -Math.PI / 2
  sweep.position.y = 0.006
  lidar.add(sweep)
  head.add(lidar)

  /* 双目相机 */
  for (const side of [-1, 1]) {
    const lensGeo = new CylinderGeometry(0.019, 0.019, 0.014, 14)
    lensGeo.rotateZ(Math.PI / 2)
    const lens = new Mesh(lensGeo, lensMat)
    lens.position.set(0.125, -0.018, side * 0.05)
    head.add(lens)
  }

  /* 状态灯（障碍报警 / 心跳异常时变色） */
  const beacon = new Mesh(new SphereGeometry(0.014, 12, 10), beaconMat)
  beacon.position.set(0.05, 0.108, 0)
  head.add(beacon)

  /* ---------- 天线 ---------- */
  const antenna = new Mesh(new CylinderGeometry(0.004, 0.004, 0.16, 6), panelMat)
  antenna.position.set(-BODY.length / 2 + 0.05, 0.11, 0)
  antenna.rotation.z = 0.28
  torso.add(antenna)

  /* ---------- 四条腿 ---------- */
  const thighGeo = new BoxGeometry(0.05, THIGH_LEN, 0.052)
  const calfGeo = new BoxGeometry(0.04, CALF_LEN, 0.042)
  const hipBallGeo = new SphereGeometry(0.046, 14, 10)
  const kneeBallGeo = new SphereGeometry(0.034, 12, 10)
  const footGeo = new CylinderGeometry(0.034, 0.03, 0.028, 14)

  const legs = {}
  for (const key of ['FL', 'FR', 'RL', 'RR']) {
    const front = key[0] === 'F'
    const left = key[1] === 'L'
    const sideSign = left ? 1 : -1

    const hip = new Group()
    hip.position.set(front ? LEG_ATTACH.x : -LEG_ATTACH.x, HIP_ATTACH_Y, sideSign * LEG_ATTACH.z)
    torso.add(hip)

    const hipBall = new Mesh(hipBallGeo, panelMat)
    hip.add(hipBall)

    const thighPivot = new Group()
    hip.add(thighPivot)

    const thigh = new Mesh(thighGeo, bodyMat)
    thigh.position.y = -THIGH_LEN / 2
    thighPivot.add(thigh)

    const kneeBall = new Mesh(kneeBallGeo, accentMat)
    kneeBall.position.y = -THIGH_LEN
    thighPivot.add(kneeBall)

    const calfPivot = new Group()
    calfPivot.position.y = -THIGH_LEN
    thighPivot.add(calfPivot)

    const calf = new Mesh(calfGeo, panelMat)
    calf.position.y = -CALF_LEN / 2
    calfPivot.add(calf)

    const foot = new Mesh(footGeo, panelMat)
    foot.position.y = -CALF_LEN - 0.012
    calfPivot.add(foot)

    legs[key] = { hip, thighPivot, calfPivot, sideSign }
  }

  /* ---------- 地面扫描环 ---------- */
  /* 从本体向外扩散淡出的雷达波：纯视觉层，depthWrite=false 不参与遮挡与拾取排序 */
  const scanRingMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.35, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const scanRingGeo = new RingGeometry(0.8, 1, 48)
  scanRingGeo.rotateX(-Math.PI / 2)
  const scanRingMesh = new Mesh(scanRingGeo, scanRingMat)
  scanRingMesh.position.y = 0.008
  group.add(scanRingMesh)

  /* ---------- 运行时状态 ---------- */
  let staleApplied = false
  let alarmApplied = false
  let lidarSpin = 0
  let elapsed = 0
  const jointState = {}
  for (const key of Object.keys(legs)) jointState[key] = { hip: 0, thigh: -0.18, calf: 0.62 }

  function update({ dt = 0.016, pose } = {}) {
    const k = dampingFactor(dt)
    if (pose?.legs) {
      for (const key of Object.keys(legs)) {
        const target = pose.legs[key]
        if (!target) continue
        const cur = jointState[key]
        cur.hip = lerpAngle(cur.hip, target.hip, k)
        cur.thigh = lerpAngle(cur.thigh, target.thigh, k)
        cur.calf = lerpAngle(cur.calf, target.calf, k)
        const rig = legs[key]
        rig.thighPivot.rotation.z = cur.thigh
        rig.thighPivot.rotation.x = cur.hip * rig.sideSign
        /* 小腿相对大腿回折（负号：膝向后折，符合四足结构） */
        rig.calfPivot.rotation.z = -cur.calf
      }
    }
    if (pose?.body) {
      torso.position.y = BODY_Y + (pose.body.bob || 0)
      torso.rotation.z = pose.body.pitch || 0
    }
    elapsed += dt
    /* LiDAR：常态匀速扫描，告警时加速，强化「发现异常」的观感 */
    lidarSpin += dt * (alarmApplied ? fx.lidarAlarmSpeed : fx.lidarSpeed)
    lidar.rotation.y = lidarSpin
    /* 状态灯呼吸 / 告警闪烁；心跳超时压暗为常亮微光 */
    const pulse = beaconPulse(elapsed, {
      alarm: alarmApplied,
      stale: staleApplied,
      idleHz: fx.beaconIdleHz,
      alarmHz: fx.beaconAlarmHz
    })
    beaconMat.emissiveIntensity = pulse.intensity
    beacon.scale.setScalar(pulse.scale)
    /* 地面扫描环：向外扩散并淡出 */
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

  return {
    kind: 'quadruped',
    group,
    materials,
    beaconMat,
    update,
    setStale,
    setAlarm,
    setEffects,
    dispose
  }
}
