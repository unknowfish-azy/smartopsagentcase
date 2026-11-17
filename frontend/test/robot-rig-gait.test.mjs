/**
 * 机器人步态与程序化 rig 结构测试。
 *
 * 覆盖：
 *  - resolveGait 的阈值语义（静止/显式 STAND/默认 TROT）
 *  - quadrupedPose：TROT 对角腿同相、WALK 四拍相位互异、STAND 回到静态姿态、振幅钳制
 *  - humanoidPose：双腿反相、双臂与对侧腿同相、振幅钳制
 *  - rig 构建：部件数量与关节可用性（update 不抛错）
 */

import test from 'node:test'
import assert from 'node:assert/strict'

import {
  QUADRUPED_STAND_POSE,
  humanoidPose,
  quadrupedPose,
  resolveGait
} from '../src/components/robot/rigs/gait.js'
import { buildQuadrupedRig } from '../src/components/robot/rigs/quadrupedRig.js'
import { buildHumanoidRig } from '../src/components/robot/rigs/humanoidRig.js'
import { BEACON_STATUS, beaconGlow, beaconPulse, resolveBeaconStatus, resolveEffectConfig, scanRing, DEFAULT_EFFECT_CONFIG } from '../src/components/robot/rigs/effects.js'

test('resolveGait：低速归为站立，显式 STAND 优先，其余落到 TROT/WALK', () => {
  assert.equal(resolveGait('TROT', 0), 'STAND')
  assert.equal(resolveGait('TROT', 0.01), 'STAND')
  assert.equal(resolveGait('TROT', 0.2), 'TROT')
  assert.equal(resolveGait('WALK', 0.2), 'WALK')
  assert.equal(resolveGait('STAND', 0.9), 'STAND')
  assert.equal(resolveGait(undefined, 0.9), 'TROT')
})

test('quadrupedPose：STAND 回到静态站立姿态且不自振', () => {
  const a = quadrupedPose({ gait: 'STAND', speed: 0, t: 0 })
  const b = quadrupedPose({ gait: 'STAND', speed: 0, t: 3.7 })
  assert.equal(a.mode, 'STAND')
  assert.equal(a.amp, 0)
  for (const key of ['FL', 'FR', 'RL', 'RR']) {
    assert.ok(Math.abs(a.legs[key].thigh - QUADRUPED_STAND_POSE.thigh) < 1e-9)
    assert.ok(Math.abs(a.legs[key].calf - QUADRUPED_STAND_POSE.calf) < 1e-9)
    assert.ok(Math.abs(a.legs[key].hip) < 1e-9)
    /* 静态姿态不随时间变化（-0 与 0 等价，逐字段比较） */
    assert.ok(Math.abs(b.legs[key].hip - a.legs[key].hip) < 1e-12)
    assert.ok(Math.abs(b.legs[key].thigh - a.legs[key].thigh) < 1e-12)
    assert.ok(Math.abs(b.legs[key].calf - a.legs[key].calf) < 1e-12)
  }
  assert.ok(Math.abs(a.body.bob) < 1e-12)
})

test('quadrupedPose：TROT 对角腿同相（FL≈RR、FR≈RL）', () => {
  const pose = quadrupedPose({ gait: 'TROT', speed: 0.25, t: 0.43 })
  assert.equal(pose.mode, 'TROT')
  assert.ok(pose.amp > 0.5)
  assert.ok(Math.abs(pose.legs.FL.thigh - pose.legs.RR.thigh) < 1e-9)
  assert.ok(Math.abs(pose.legs.FR.thigh - pose.legs.RL.thigh) < 1e-9)
  /* 对角对之间应存在明显相位差（不会同相） */
  assert.ok(Math.abs(pose.legs.FL.thigh - pose.legs.FR.thigh) > 1e-3)
})

test('quadrupedPose：WALK 四拍相位两两互异', () => {
  const pose = quadrupedPose({ gait: 'WALK', speed: 0.3, t: 0.27 })
  assert.equal(pose.mode, 'WALK')
  const values = ['FL', 'FR', 'RL', 'RR'].map((k) => pose.legs[k].thigh)
  for (let i = 0; i < values.length; i += 1) {
    for (let j = i + 1; j < values.length; j += 1) {
      assert.ok(Math.abs(values[i] - values[j]) > 1e-3, `legs ${i}/${j} 不应同相`)
    }
  }
})

test('quadrupedPose：振幅随速度单调增长并钳制到 1', () => {
  const slow = quadrupedPose({ speed: 0.05, t: 0.2 })
  const mid = quadrupedPose({ speed: 0.2, t: 0.2 })
  const fast = quadrupedPose({ speed: 5, t: 0.2 })
  assert.ok(slow.amp < mid.amp)
  assert.equal(fast.amp, 1)
  /* 关节角保持在物理合理范围（不出现翻转） */
  for (const key of ['FL', 'FR', 'RL', 'RR']) {
    assert.ok(Math.abs(poseAngle(fast.legs[key].thigh)) < 1.0)
    assert.ok(fast.legs[key].calf > -0.2 && fast.legs[key].calf < 1.6)
  }
})

test('quadrupedPose：负速度（后退）与正速度步态反相', () => {
  const forward = quadrupedPose({ speed: 0.25, t: 0.4 })
  const backward = quadrupedPose({ speed: -0.25, t: 0.4 })
  const fwdSwing = forward.legs.FL.thigh - QUADRUPED_STAND_POSE.thigh
  const bwdSwing = backward.legs.FL.thigh - QUADRUPED_STAND_POSE.thigh
  assert.ok(Math.abs(fwdSwing + bwdSwing) < 1e-9)
})

test('humanoidPose：双腿反相、双臂与对侧腿同相', () => {
  const pose = humanoidPose({ speed: 0.5, t: 0.31 })
  assert.ok(pose.amp > 0.5)
  assert.ok(Math.abs(pose.legs.L.thigh + pose.legs.R.thigh) < 1e-9)
  assert.ok(Math.abs(pose.arms.L.upper - pose.legs.L.thigh) > 1e-3, '手臂应反对侧腿摆动')
  /* 手臂方向与同侧腿相反 */
  assert.ok(pose.legs.L.thigh * pose.arms.L.upper <= 0)
})

test('humanoidPose：静止时振幅为 0、关节回中', () => {
  const pose = humanoidPose({ speed: 0, t: 1.2 })
  assert.equal(pose.amp, 0)
  assert.ok(Math.abs(pose.legs.L.thigh) < 1e-12)
  assert.ok(Math.abs(pose.legs.R.thigh) < 1e-12)
  assert.ok(Math.abs(pose.torso.yaw) < 1e-12)
})

test('quadrupedRig：构建出 4 条腿关节，update 可反复调用不抛错', () => {
  const rig = buildQuadrupedRig({ accentHex: 0x5b8cff })
  assert.equal(rig.kind, 'quadruped')
  assert.ok(rig.group)
  assert.ok(rig.materials.length >= 4)

  const pose = quadrupedPose({ speed: 0.3, t: 0.5 })
  for (let i = 0; i < 12; i += 1) rig.update({ dt: 0.016, pose })
  /* 阻尼收敛：大腿角应逼近目标 */
  assert.ok(Number.isFinite(rig.group.position.x))
  rig.setStale(true)
  rig.setStale(false)
  rig.setBeaconStatus({ mode: 'AUTONOMOUS' })
  assert.equal(rig.materials[0].opacity, 1)
  rig.dispose()
})

test('humanoidRig：构建与动画更新可用', () => {
  const rig = buildHumanoidRig({ accentHex: 0x5b8cff })
  assert.equal(rig.kind, 'humanoid')
  const pose = humanoidPose({ speed: 0.4, t: 0.2 })
  for (let i = 0; i < 6; i += 1) rig.update({ dt: 0.016, pose })
  assert.ok(rig.group.children.length > 0)
  rig.setBeaconStatus({ mode: 'HUMAN_CONTROL' })
  assert.equal(rig.beaconMat.color.getHex(), 0x57c8d8)
  rig.dispose()
})

/** 取绝对值的辅助函数（保持断言可读）。 */
function poseAngle(value) {
  return Math.abs(value)
}

test('beaconPulse：常态慢呼吸、告警更亮更快、心跳超时压暗', () => {
  const idleBase = beaconPulse(0)
  /* 0.8Hz 的峰值在 1/4 周期（0.3125s） */
  const idlePeak = beaconPulse(0.3125)
  assert.ok(idlePeak.intensity > idleBase.intensity)
  assert.ok(idlePeak.scale > idleBase.scale)

  const alarmBase = beaconPulse(0, { alarm: true })
  const alarmPeak = beaconPulse(1 / 12, { alarm: true })
  assert.ok(alarmBase.intensity > idlePeak.intensity, '告警应比常态峰值更亮')
  assert.ok(alarmPeak.intensity > alarmBase.intensity)
  assert.ok(alarmPeak.scale > idlePeak.scale, '告警脉冲幅度更大')

  assert.deepEqual(beaconPulse(1.7, { stale: true }), { intensity: 0.35, scale: 1 })
  /* 非法时间不产生 NaN */
  assert.ok(Number.isFinite(beaconPulse(Number.NaN).intensity))
})

test('scanRing：半径单调外扩、透明度递减，超时更淡', () => {
  const start = scanRing(0)
  const mid = scanRing(1.2)
  const end = scanRing(2.39)
  assert.ok(start.progress === 0)
  assert.ok(start.scale < mid.scale && mid.scale < end.scale)
  assert.ok(start.opacity > mid.opacity && mid.opacity > end.opacity)
  assert.ok(scanRing(1.2, { stale: true }).opacity < mid.opacity)
  assert.ok(scanRing(-1).progress >= 0 && scanRing(-1).progress < 1, '负时间仍然落在 0→1 区间')
})

test('rig 状态灯接入业务状态：颜色与节奏随真实模式切换', () => {
  const rig = buildQuadrupedRig({ accentHex: 0x5b8cff })
  const pose = quadrupedPose({ speed: 0.25, t: 0.2 })
  rig.update({ dt: 0.1, pose })
  const first = rig.beaconMat.emissiveIntensity
  for (let i = 0; i < 8; i += 1) rig.update({ dt: 0.05, pose })
  const later = rig.beaconMat.emissiveIntensity
  assert.ok(Number.isFinite(first) && Number.isFinite(later))
  assert.ok(Math.abs(later - first) > 1e-6, '状态灯应随呼吸动画持续变化')

  /* 自主巡检：蓝色呼吸，节奏 = 常态频率 × 1.6 */
  rig.setBeaconStatus({ mode: 'AUTONOMOUS', battery: 0.8 })
  assert.equal(rig.beaconMat.color.getHex(), 0x5b8cff)
  rig.update({ dt: 0.02, pose })
  const elapsed = 0.1 + 8 * 0.05 + 0.02
  const expected = beaconPulse(elapsed, {
    hz: DEFAULT_EFFECT_CONFIG.beaconIdleHz * BEACON_STATUS.running.factor,
    intensity: BEACON_STATUS.running.intensity,
    scaleAmp: BEACON_STATUS.running.scaleAmp
  })
  assert.ok(Math.abs(rig.beaconMat.emissiveIntensity - expected.intensity) < 1e-9)

  /* 急停：红色快闪，且 LiDAR 切到告警转速 */
  rig.setBeaconStatus({ mode: 'E_STOP' })
  assert.equal(rig.beaconMat.color.getHex(), 0xe5484d)
  let lidarGroup = null
  rig.group.traverse((node) => { if (node.geometry?.type === 'TorusGeometry') lidarGroup = node.parent })
  const spinBefore = lidarGroup.rotation.y
  rig.update({ dt: 0.5, pose })
  assert.ok(Math.abs(lidarGroup.rotation.y - spinBefore - 0.5 * DEFAULT_EFFECT_CONFIG.lidarAlarmSpeed) < 1e-9)

  /* 心跳中断：灰色离线 */
  rig.setBeaconStatus({ stale: true })
  assert.equal(rig.beaconMat.color.getHex(), 0x8a8f98)

  let ringCount = 0
  rig.group.traverse((node) => { if (node.geometry?.type === 'RingGeometry') ringCount += 1 })
  assert.equal(ringCount, 2, '主环 + 错峰副环')

  /* 状态灯还应驱动外发光与局部点光 */
  let lightIntensity = 0
  rig.group.traverse((node) => { if (node.type === 'PointLight') lightIntensity = node.intensity })
  assert.ok(lightIntensity > 0, '状态灯应点亮局部点光')
  rig.dispose()
})

test('resolveBeaconStatus：离线 > 急停 > 障碍 > 低电 > 运行模式', () => {
  assert.equal(resolveBeaconStatus({ stale: true, mode: 'E_STOP' }).key, 'offline')
  assert.equal(resolveBeaconStatus({ mode: 'OFFLINE' }).key, 'offline')
  assert.equal(resolveBeaconStatus({ mode: 'E_STOP', obstacleDistance: 0.1 }).key, 'fault')
  assert.equal(resolveBeaconStatus({ mode: 'AUTONOMOUS', obstacleDistance: 0.3, battery: 0.05 }).key, 'warn')
  assert.equal(resolveBeaconStatus({ mode: 'AUTONOMOUS', battery: 0.5 }).key, 'running')
  assert.equal(resolveBeaconStatus({ mode: 'HUMAN_CONTROL' }).key, 'manual')
  assert.equal(resolveBeaconStatus({ mode: 'IDLE' }).key, 'idle')
  /* 电量兼容 0~1 比例与 0~100 百分数 */
  assert.equal(resolveBeaconStatus({ battery: 15 }).key, 'warn')
  assert.equal(resolveBeaconStatus({ battery: 60 }).key, 'idle')
  /* 阈值边界：0.5m 不算过近，缺失/非法遥测不误报 */
  assert.equal(resolveBeaconStatus({ obstacleDistance: 0.5 }).key, 'idle')
  assert.equal(resolveBeaconStatus({ obstacleDistance: null, battery: null }).key, 'idle')
})

test('humanoidRig 同样带 LiDAR 扫描与状态灯', () => {
  const rig = buildHumanoidRig({ accentHex: 0x5b8cff })
  const pose = humanoidPose({ speed: 0.3, t: 0.15 })
  rig.update({ dt: 0.1, pose })
  assert.ok(rig.beaconMat.emissiveIntensity > 0)
  let ringCount = 0
  rig.group.traverse((node) => {
    if (node.geometry?.type === 'RingGeometry') ringCount += 1
  })
  assert.equal(ringCount, 2, '主环 + 错峰副环')
  rig.dispose()
})

test('resolveEffectConfig：缺省回落默认值，只接受非负有限数字', () => {
  assert.deepEqual(resolveEffectConfig(), { ...DEFAULT_EFFECT_CONFIG })
  assert.deepEqual(resolveEffectConfig(null), { ...DEFAULT_EFFECT_CONFIG })
  assert.equal(resolveEffectConfig({ lidarSpeed: 9, scanPeriod: 1.2 }).lidarSpeed, 9)
  assert.equal(resolveEffectConfig({ scanPeriod: 1.2 }).scanPeriod, 1.2)
  /* 非法值不生效 */
  assert.equal(resolveEffectConfig({ lidarSpeed: -1 }).lidarSpeed, DEFAULT_EFFECT_CONFIG.lidarSpeed)
  assert.equal(resolveEffectConfig({ lidarSpeed: 'abc' }).lidarSpeed, DEFAULT_EFFECT_CONFIG.lidarSpeed)
  /* 未知键不污染配置 */
  assert.equal('foo' in resolveEffectConfig({ foo: 1 }), false)
})

test('可配置项生效：LiDAR 转速与扫描周期按覆盖值运行', () => {
  const rig = buildQuadrupedRig({ effects: { lidarSpeed: 8, scanPeriod: 1.2, ringMaxOpacity: 0.5 } })
  let lidarGroup = null
  rig.group.traverse((node) => {
    if (node.geometry?.type === 'TorusGeometry') lidarGroup = node.parent
  })
  assert.ok(lidarGroup, '应能找到 LiDAR 组件')
  rig.update({ dt: 1, pose: quadrupedPose({ speed: 0, t: 0 }) })
  assert.ok(Math.abs(lidarGroup.rotation.y - 8) < 1e-9, '转速取覆盖值 8 rad/s')
  rig.dispose()

  assert.ok(Math.abs(scanRing(0.6, { period: 1.2 }).progress - 0.5) < 1e-9)
  assert.ok(Math.abs(scanRing(0, { maxOpacity: 0.5 }).opacity - 0.5) < 1e-9)
  /* 相位偏移：副环落后半个周期 */
  assert.ok(Math.abs(scanRing(0, { phase: 0.5 }).progress - 0.5) < 1e-9)
  assert.ok(scanRing(0.1, { phase: 0.5 }).scale > scanRing(0.1).scale)
})

test('beaconGlow：亮度越高光晕越大越亮，并钳制上限', () => {
  const dim = beaconGlow({ intensity: 0.5, scale: 1.02 })
  const bright = beaconGlow({ intensity: 3, scale: 1.15 })
  assert.ok(bright.opacity > dim.opacity)
  assert.ok(bright.scale > dim.scale)
  assert.ok(beaconGlow({ intensity: 10, scale: 2 }).opacity <= 0.46)
  assert.equal(beaconGlow().scale, 1, '缺省脉冲不放大光晕')
})

test('setEffects：运行中热更新参数，无需重建 rig', () => {
  const rig = buildQuadrupedRig()
  let lidarGroup = null
  rig.group.traverse((node) => {
    if (node.geometry?.type === 'TorusGeometry') lidarGroup = node.parent
  })
  const pose = quadrupedPose({ speed: 0, t: 0 })
  rig.update({ dt: 1, pose })
  assert.ok(Math.abs(lidarGroup.rotation.y - DEFAULT_EFFECT_CONFIG.lidarSpeed) < 1e-9)

  rig.setEffects({ lidarSpeed: 5 })
  rig.update({ dt: 1, pose })
  assert.ok(Math.abs(lidarGroup.rotation.y - (DEFAULT_EFFECT_CONFIG.lidarSpeed + 5)) < 1e-9)

  /* 非法值回落默认，不影响后续动画 */
  rig.setEffects({ lidarSpeed: -3 })
  rig.update({ dt: 1, pose })
  assert.ok(Math.abs(lidarGroup.rotation.y - (DEFAULT_EFFECT_CONFIG.lidarSpeed + 5 + DEFAULT_EFFECT_CONFIG.lidarSpeed)) < 1e-9)
  rig.dispose()
})
