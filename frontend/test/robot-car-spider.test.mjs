/**
 * 巡检车 / 蜘蛛机器人 3D 形态测试（与机器狗同一条数据链路）。
 *
 * 覆盖：
 *  - spiderPose：8 足交替四足步态、静止归零、振幅随速度夹紧
 *  - spiderRig：16 关节数量、速度驱动摆动、静止回站立、真机绝对角直驱 + range 夹紧
 *  - patrolCarRig：4 轮数量、轮角速度 = 线速度 / 轮半径、速度归零后不再空转、stale 半透明
 *  - patrolCarRig：左右轮速遥测差速驱动、LiDAR 转速取自遥测
 *  - 构建器：几何节点命名与 rig.json 一一对应、GLB 产物结构、尺寸归一
 */

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { Quaternion, Vector3 } from 'three'

import { spiderPose } from '../src/components/robot/rigs/gait.js'
import { createPatrolCarRig } from '../src/components/robot/rigs/patrolCarRig.js'
import { createSpiderRig } from '../src/components/robot/rigs/spiderRig.js'
import { measureRobotBounds } from '../src/components/robot/rigs/effectLayer.js'
import {
  buildPatrolCarModel, buildPatrolCarRigMeta, CAR_WHEEL_RADIUS, CAR_WHEEL_LAYOUT
} from '../src/components/robot/models/patrolCarModel.js'
import {
  buildSpiderBotModel, buildSpiderRigMeta, SPIDER_LEG_COUNT, SPIDER_LEG_HOME
} from '../src/components/robot/models/spiderBotModel.js'

const assetPath = (name) => fileURLToPath(new URL(`../public/models/robot/${name}`, import.meta.url))
const carMeta = JSON.parse(readFileSync(assetPath('patrol-car.rig.json'), 'utf8'))
const spiderMeta = JSON.parse(readFileSync(assetPath('spider-bot.rig.json'), 'utf8'))

function readGlbJson(name) {
  const buf = readFileSync(assetPath(name))
  assert.equal(buf.readUInt32LE(0), 0x46546c67, 'GLB magic')
  const jsonLen = buf.readUInt32LE(12)
  return JSON.parse(buf.subarray(20, 20 + jsonLen).toString('utf8'))
}

function quatFor(axis, angle) {
  return new Quaternion().setFromAxisAngle(new Vector3(...axis), angle)
}

// ------------------------------------------------------------------
// 蜘蛛步态解算
// ------------------------------------------------------------------

test('spiderPose：速度为零时 8 足全部回到站立增量 0', () => {
  const pose = spiderPose({ speed: 0, t: 1.7 })
  assert.equal(pose.legs.length, SPIDER_LEG_COUNT)
  for (const leg of pose.legs) {
    assert.ok(Math.abs(leg.hip) < 1e-12)
    assert.ok(Math.abs(leg.knee) < 1e-12)
  }
})

test('spiderPose：偶数腿与奇数腿反相，抬腿只发生在摆动相，振幅随速度夹紧', () => {
  const pose = spiderPose({ speed: 0.25, t: 0.2 })
  assert.ok(Math.abs(pose.amp - 0.5) < 1e-12)
  /* 相邻腿相位差 π：hip 严格反号 */
  assert.ok(Math.abs(pose.legs[0].hip + pose.legs[1].hip) < 1e-12)
  for (const leg of pose.legs) {
    assert.ok(leg.knee >= 0, '抬腿增量为非负')
    assert.ok(Math.abs(leg.hip) <= 0.28 + 1e-12)
  }
  assert.equal(spiderPose({ speed: 5, t: 0.2 }).amp, 1)
  /* 反向行走：hip 相位翻转 */
  assert.ok(Math.abs(spiderPose({ speed: -0.25, t: 0.2 }).legs[0].hip + pose.legs[0].hip) < 1e-12)
})

// ------------------------------------------------------------------
// 蜘蛛 rig
// ------------------------------------------------------------------

test('spiderRig：16 个关节节点全部命中，速度驱动摆动，静止回站立', () => {
  const rig = createSpiderRig()
  assert.equal(rig.kind, 'arachnid')
  assert.equal(rig.jointCount, 16)

  const hip0 = rig.group.getObjectByName('Leg0_hip')
  const hip1 = rig.group.getObjectByName('Leg1_hip')
  assert.ok(hip0 && hip1)

  for (let i = 0; i < 20; i += 1) {
    rig.update({ dt: 0.016, pose: spiderPose({ speed: 0.4, t: i * 0.05 }) })
  }
  const q0 = hip0.quaternion.clone()
  const q1 = hip1.quaternion.clone()
  assert.ok(q0.angleTo(new Quaternion()) > 1e-3, '偶数腿在摆动')
  assert.ok(q1.angleTo(new Quaternion()) > 1e-3, '奇数腿在摆动')
  assert.ok(q0.angleTo(q1) > 1e-3, '两组腿相位不同')

  /* 速度归零（含心跳超时）连续站立 → 关节阻尼回 home */
  for (let i = 0; i < 300; i += 1) rig.update({ dt: 0.016, pose: spiderPose({ speed: 0 }) })
  assert.ok(hip0.quaternion.angleTo(quatFor([0, 1, 0], SPIDER_LEG_HOME.hip)) < 1e-2)
  const knee0 = rig.group.getObjectByName('Leg0_knee')
  assert.ok(knee0.quaternion.angleTo(quatFor([0, 0, 1], SPIDER_LEG_HOME.knee)) < 1e-2)
  rig.dispose()
})

test('spiderRig：真机绝对关节角直驱并夹紧到 range，数据源标注 telemetry', () => {
  const rig = createSpiderRig()
  for (let i = 0; i < 300; i += 1) {
    rig.update({ dt: 0.016, pose: spiderPose({ speed: 0 }), joints: { Leg0_hip: 9, Leg2_knee: -9, bogus: 1 } })
  }
  assert.equal(rig.getJointSource(), 'telemetry')
  const hip = rig.group.getObjectByName('Leg0_hip')
  assert.ok(hip.quaternion.angleTo(quatFor([0, 1, 0], spiderMeta.joints.Leg0_hip.range[1])) < 1e-2)
  const knee = rig.group.getObjectByName('Leg2_knee')
  assert.ok(knee.quaternion.angleTo(quatFor([0, 0, 1], spiderMeta.joints.Leg2_knee.range[0])) < 1e-2)

  /* 遥测消失 → 回到步态推算并如实标注 */
  rig.update({ dt: 0.016, pose: spiderPose({ speed: 0 }), joints: null })
  assert.equal(rig.getJointSource(), 'gait')
  rig.dispose()
})

// ------------------------------------------------------------------
// 巡检车 rig
// ------------------------------------------------------------------

test('patrolCarRig：4 轮按「线速度 / 轮半径」滚动，速度为 0 不再空转', () => {
  const rig = createPatrolCarRig()
  assert.equal(rig.kind, 'wheeled')
  assert.equal(rig.wheelCount, 4)
  assert.equal(rig.jointCount, 0)

  const wheel = rig.group.getObjectByName('Wheel_FL')
  assert.ok(wheel)
  /* dt=0.1、速度 0.4 → 角速度 0.4/0.075 ≈ 5.33rad/s，角度 0.533rad */
  rig.update({ dt: 0.1, speed: 0.4 })
  const angle = wheel.rotation.z
  assert.ok(Math.abs(Math.abs(angle) - 0.4 / CAR_WHEEL_RADIUS * 0.1) < 1e-6)
  assert.ok(angle < 0, '前进时绕 +Z 反向滚动')

  /* 位置停止 / 心跳超时（速度 0）→ 轮角冻结 */
  const frozen = wheel.rotation.z
  for (let i = 0; i < 60; i += 1) rig.update({ dt: 0.016, speed: 0 })
  assert.equal(wheel.rotation.z, frozen)

  /* 倒车 → 反向滚动 */
  rig.update({ dt: 0.1, speed: -0.4 })
  assert.ok(Math.abs(wheel.rotation.z) < Math.abs(frozen), '倒车抵消前进角度')
  rig.dispose()
})

test('patrolCarRig：左右轮速遥测差速驱动，LiDAR 转速取自遥测', () => {
  const rig = createPatrolCarRig()
  const fl = rig.group.getObjectByName('Wheel_FL')
  const fr = rig.group.getObjectByName('Wheel_FR')
  assert.ok(fl && fr)

  /* 左右轮速不同 → 各自独立滚动；右转时左轮应更快 */
  rig.update({ dt: 0.1, wheels: { leftSpeed: 0.4, rightSpeed: 0.2 } })
  const leftAngle = fl.rotation.z
  const rightAngle = fr.rotation.z
  assert.ok(Math.abs(Math.abs(leftAngle) - 0.4 / CAR_WHEEL_RADIUS * 0.1) < 1e-6)
  assert.ok(Math.abs(Math.abs(rightAngle) - 0.2 / CAR_WHEEL_RADIUS * 0.1) < 1e-6)
  assert.ok(Math.abs(leftAngle) > Math.abs(rightAngle), '左轮转速高于右轮（右转差速）')

  /* LiDAR 转速取遥测 rpm：60rpm = 1rev/s，0.1s 转 0.2π */
  const lidar = rig.group.getObjectByName('LidarHead')
  const before = lidar.quaternion.clone()
  rig.update({ dt: 0.1, wheels: { leftSpeed: 0, rightSpeed: 0, lidarRpm: 60 } })
  assert.ok(Math.abs(before.angleTo(lidar.quaternion) - Math.PI * 2 * 0.1) < 1e-6)

  /* 遥测缺失 → 回退车体线速度（左右轮同速） */
  rig.update({ dt: 0.1, speed: 0.3, wheels: null })
  const fallbackAngle = fl.rotation.z - leftAngle
  assert.ok(Math.abs(Math.abs(fallbackAngle) - 0.3 / CAR_WHEEL_RADIUS * 0.1) < 1e-6)
  assert.ok(Math.abs(Math.abs(fl.rotation.z - leftAngle) - Math.abs(fr.rotation.z - rightAngle)) < 1e-6)
  rig.dispose()
})

test('patrolCarRig：stale 半透明与动效层挂载', () => {
  const rig = createPatrolCarRig()
  const materials = []
  rig.group.children[0].traverse((n) => { if (n.material) materials.push(n.material) })
  rig.setStale(true)
  for (const m of materials) assert.equal(m.opacity, 0.3)
  rig.setStale(false)
  for (const m of materials) assert.equal(m.opacity, 1)
  assert.ok(rig.group.getObjectByName('robot-effect-layer'), '动效层挂在 rig 容器内')
  rig.dispose()
})

// ------------------------------------------------------------------
// 构建器与 GLB 产物一致
// ------------------------------------------------------------------

test('构建器：车 4 轮 + 顶置 LiDAR，蜘蛛 8 腿 16 关节节点', () => {
  const car = buildPatrolCarModel()
  assert.equal(car.wheels.length, 4)
  assert.equal(car.wheels.map((w) => w.name).join(','), CAR_WHEEL_LAYOUT.map((w) => w.name).join(','))
  assert.ok(car.root.getObjectByName('LidarHead'))

  const spider = buildSpiderBotModel()
  assert.equal(spider.legs.length, SPIDER_LEG_COUNT)
  for (let i = 0; i < SPIDER_LEG_COUNT; i += 1) {
    assert.ok(spider.root.getObjectByName(`Leg${i}_hip`))
    assert.ok(spider.root.getObjectByName(`Leg${i}_knee`))
  }
  assert.ok(spider.root.getObjectByName('SensorHead'))

  /* 元数据构建器与落盘 rig.json 完全一致（资产与兜底不会漂移） */
  assert.deepEqual(buildPatrolCarRigMeta(), carMeta)
  assert.deepEqual(buildSpiderRigMeta(), spiderMeta)
})

test('GLB 产物：节点名与 rig.json 一一对应，且不含烘焙动画', () => {
  const car = readGlbJson('patrol-car.glb')
  const carNodes = new Set(car.nodes.map((n) => n.name))
  for (const wheel of carMeta.wheels) assert.ok(carNodes.has(wheel.node), `缺车轮节点 ${wheel.node}`)
  assert.ok(carNodes.has(carMeta.lidar.node))
  assert.equal(car.animations?.length || 0, 0, '轮速由 rig 驱动，不烘焙动画')

  const spider = readGlbJson('spider-bot.glb')
  const spiderNodes = new Set(spider.nodes.map((n) => n.name))
  const jointNames = Object.keys(spiderMeta.joints)
  assert.equal(jointNames.length, 16)
  for (const name of jointNames) assert.ok(spiderNodes.has(spiderMeta.joints[name].node), `缺关节节点 ${name}`)
  assert.ok(spiderNodes.has(spiderMeta.sensor.node))
  assert.equal(spider.animations?.length || 0, 0)
})

test('尺寸归一：车与蜘蛛视觉体长对齐 1.36m，不再比机器狗小一圈', () => {
  for (const rig of [createPatrolCarRig(), createSpiderRig()]) {
    const bounds = measureRobotBounds(rig.group.children[0])
    assert.ok(Math.abs(bounds.footprint - 1.36) < 0.02, `${rig.kind} footprint=${bounds.footprint}`)
    rig.dispose()
  }
})
