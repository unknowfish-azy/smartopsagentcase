/**
 * 宇树官方 GLB rig 测试。
 *
 * 覆盖：
 *  - unitreeJointMap：站立归零到官方 home、符号约定（前摆负增量 / 回折正增量 / 左右外展异号）
 *  - unitreeGlbRig：真机绝对关节角直驱 + range 夹紧、未知关节名忽略、数据源如实标注、stale 材质
 *  - 转换产物：go2.glb / g1.glb 的关节节点与 rig.json 元数据一一对应、Y-up 根旋转、接地偏移
 */

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { BoxGeometry, Group, Mesh, MeshStandardMaterial, Quaternion, Vector3 } from 'three'

import { go2JointTargets, g1JointTargets } from '../src/components/robot/rigs/unitreeJointMap.js'
import { createUnitreeGlbRig } from '../src/components/robot/rigs/unitreeGlbRig.js'
import { humanoidPose, quadrupedPose } from '../src/components/robot/rigs/gait.js'

const metaPath = (name) => fileURLToPath(new URL(`../public/models/robot/${name}`, import.meta.url))
const go2Meta = JSON.parse(readFileSync(metaPath('go2.rig.json'), 'utf8'))
const g1Meta = JSON.parse(readFileSync(metaPath('g1.rig.json'), 'utf8'))

function readGlbJson(name) {
  const buf = readFileSync(metaPath(name))
  assert.equal(buf.readUInt32LE(0), 0x46546c67, 'GLB magic')
  const jsonLen = buf.readUInt32LE(12)
  return JSON.parse(buf.subarray(20, 20 + jsonLen).toString('utf8'))
}

// ------------------------------------------------------------------
// 步态 → MJCF 关节映射
// ------------------------------------------------------------------

test('go2JointTargets：站立姿态全部回到官方 home（thigh=0.9 / calf=-1.8）', () => {
  const targets = go2JointTargets(quadrupedPose({ speed: 0, t: 0 }), go2Meta.joints)
  assert.equal(Object.keys(targets).length, 12)
  for (const leg of ['FL', 'FR', 'RL', 'RR']) {
    assert.ok(Math.abs(targets[`${leg}_hip_joint`] - 0) < 1e-12)
    assert.ok(Math.abs(targets[`${leg}_thigh_joint`] - 0.9) < 1e-12)
    assert.ok(Math.abs(targets[`${leg}_calf_joint`] - -1.8) < 1e-12)
  }
})

test('go2JointTargets：前摆为负增量、屈膝加深更负、左右外展异号', () => {
  const pose = { legs: { FL: { hip: 0.1, thigh: 0.3, calf: 1.0 }, FR: { hip: 0.1, thigh: 0.3, calf: 1.0 } } }
  const t = go2JointTargets(pose, go2Meta.joints)
  /* thigh：gait 站立 -0.18 → 0.3 为前摆增量 0.48，MJCF q = 0.9 - 0.48 */
  assert.ok(Math.abs(t.FL_thigh_joint - 0.42) < 1e-12)
  /* calf：gait 站立 0.62 → 1.0 屈膝加深 0.38，MJCF q = -1.8 - 0.38（仍在 range [-2.7227, -0.83776] 内） */
  assert.ok(Math.abs(t.FL_calf_joint - -2.18) < 1e-12)
  /* 左髋外展为正、右髋镜像 */
  assert.ok(Math.abs(t.FL_hip_joint - 0.1) < 1e-12)
  assert.ok(Math.abs(t.FR_hip_joint - -0.1) < 1e-12)
  /* 未给出的腿不产生目标 */
  assert.equal(t.RL_thigh_joint, undefined)
})

test('g1JointTargets：站立回到官方 home（直腿、手臂自然下垂），髋前摆为负、膝肘回折为正、腰 yaw 直通', () => {
  const stand = g1JointTargets(humanoidPose({ speed: 0, t: 0 }), g1Meta.joints)
  for (const [name, value] of Object.entries(stand)) {
    assert.ok(Math.abs(value - (g1Meta.joints[name]?.home || 0)) < 1e-12, `${name} 未回 home`)
  }
  /* 展示用站立 home：肘 +1.4（官方零位 L 形前伸 → 自然下垂），且落在官方 range 内 */
  assert.ok(Math.abs(g1Meta.joints.left_elbow_joint.home - 1.4) < 1e-12)
  assert.ok(Math.abs(g1Meta.joints.right_elbow_joint.home - 1.4) < 1e-12)

  const pose = {
    legs: { L: { thigh: 0.4, calf: 0.5, foot: 0.1 } },
    arms: { R: { upper: 0.2, fore: 0.6 } },
    torso: { yaw: 0.1 }
  }
  const t = g1JointTargets(pose, g1Meta.joints)
  assert.ok(Math.abs(t.left_hip_pitch_joint - -0.4) < 1e-12)
  assert.ok(Math.abs(t.left_knee_joint - (0.5 - 0.06)) < 1e-12)
  assert.ok(Math.abs(t.left_ankle_pitch_joint - -0.1) < 1e-12)
  assert.ok(Math.abs(t.right_shoulder_pitch_joint - -0.2) < 1e-12)
  assert.ok(Math.abs(t.right_elbow_joint - (1.4 + 0.6 - 0.3)) < 1e-12)
  assert.ok(Math.abs(t.waist_yaw_joint - 0.1) < 1e-12)
})

// ------------------------------------------------------------------
// GLB rig：真机直驱 / 推算兜底 / 数据源标注
// ------------------------------------------------------------------

function mockGo2Gltf() {
  const scene = new Group()
  const material = new MeshStandardMaterial()
  scene.add(new Mesh(new BoxGeometry(0.6, 0.2, 0.3), material))
  for (const [name, meta] of Object.entries(go2Meta.joints)) {
    const node = new Group()
    node.name = name
    node.quaternion.setFromAxisAngle(new Vector3(...meta.axis), meta.home)
    scene.add(node)
  }
  return { scene, animations: [] }
}

test('unitreeGlbRig：真机绝对角直驱并夹紧到官方 range，数据源标注 telemetry', () => {
  const gltf = mockGo2Gltf()
  const rig = createUnitreeGlbRig({ kind: 'quadruped', gltf, metadata: go2Meta })
  assert.equal(rig.jointCount, 12)
  /* 真机值 9 rad 超出 front_hip range 上限 3.4907 → 夹紧 */
  for (let i = 0; i < 300; i += 1) {
    rig.update({ dt: 0.016, pose: quadrupedPose({ speed: 0 }), joints: { FL_thigh_joint: 9, bogus_joint: 1 } })
  }
  assert.equal(rig.getJointSource(), 'telemetry')
  const node = gltf.scene.getObjectByName('FL_thigh_joint')
  const expected = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), 3.4907)
  assert.ok(node.quaternion.angleTo(expected) < 1e-3)
  /* 未覆盖关节仍由步态（站立 → home）驱动 */
  const calf = gltf.scene.getObjectByName('FL_calf_joint')
  const calfExpected = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), -1.8)
  assert.ok(calf.quaternion.angleTo(calfExpected) < 1e-3)
  rig.dispose()
})

test('unitreeGlbRig：未知关节名不算真机覆盖，无遥测时标注 gait 并回 home', () => {
  const gltf = mockGo2Gltf()
  const rig = createUnitreeGlbRig({ kind: 'quadruped', gltf, metadata: go2Meta })
  rig.update({ dt: 0.016, pose: quadrupedPose({ speed: 0 }), joints: { bogus_joint: 1 } })
  assert.equal(rig.getJointSource(), 'gait')
  for (let i = 0; i < 300; i += 1) rig.update({ dt: 0.016, pose: quadrupedPose({ speed: 0.3, t: 0.4 }) })
  assert.equal(rig.getJointSource(), 'gait')
  /* 行走后回到站立，关节回官方 home */
  for (let i = 0; i < 300; i += 1) rig.update({ dt: 0.016, pose: quadrupedPose({ speed: 0 }) })
  const node = gltf.scene.getObjectByName('RR_thigh_joint')
  const expected = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), 0.9)
  assert.ok(node.quaternion.angleTo(expected) < 1e-3)
  rig.dispose()
})

test('unitreeGlbRig：stale 半透明切换与动效层挂载', () => {
  const gltf = mockGo2Gltf()
  const rig = createUnitreeGlbRig({ kind: 'quadruped', gltf, metadata: go2Meta })
  const materials = []
  gltf.scene.traverse((n) => { if (n.material) materials.push(n.material) })
  rig.setStale(true)
  for (const m of materials) { assert.equal(m.transparent, true); assert.equal(m.opacity, 0.3) }
  rig.setStale(false)
  for (const m of materials) { assert.equal(m.transparent, false); assert.equal(m.opacity, 1) }
  assert.ok(rig.group.getObjectByName('robot-effect-layer'), '动效层挂在 rig 容器内')
  rig.dispose()
})

// ------------------------------------------------------------------
// 转换产物结构：关节节点与元数据一致、Y-up、接地
// ------------------------------------------------------------------

for (const [file, meta, dof] of [['go2.glb', go2Meta, 12], ['g1.glb', g1Meta, 23]]) {
  test(`${file}：${dof} 个关节节点与 rig.json 一一对应，根节点 Y-up 且站立接地`, () => {
    const gltf = readGlbJson(file)
    assert.equal(meta.dof, dof)
    const nodeNames = new Set(gltf.nodes.map((n) => n.name))
    for (const [name, joint] of Object.entries(meta.joints)) {
      assert.ok(nodeNames.has(joint.node), `缺关节节点 ${name}`)
    }
    const rootIndex = gltf.scenes[0].nodes[0]
    const root = gltf.nodes[rootIndex]
    assert.equal(root.name, 'unitree_root')
    /* R_x(-90°)：MJCF Z-up → GLB Y-up */
    assert.ok(Math.abs(root.rotation[0] + Math.SQRT1_2) < 1e-6)
    assert.ok(Math.abs(root.rotation[3] - Math.SQRT1_2) < 1e-6)
    /* 接地偏移 = home 姿态最低点补偿（Go2 ≈0.29m，G1 ≈0.79m） */
    assert.ok(Math.abs(root.translation[1] - meta.groundOffset) < 1e-9)
    assert.ok(meta.groundOffset > 0.1 && meta.groundOffset < 1.2)
    assert.ok(gltf.meshes.length > 0)
    assert.equal(meta.source.license, 'BSD-3-Clause')
  })
}
