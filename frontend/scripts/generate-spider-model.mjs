/**
 * 程序化生成 SPIDER 形态巡检机器人 GLB（M8b 管线第二形态）。
 *
 * 产出：frontend/public/models/robot/spider-bot.glb
 * - PBR 材质（MeshStandardMaterial → glTF metallic-roughness）
 * - 8 足摆动（交替相位）+ 传感器头旋转（Clip "walk"，组件兼容首 clip 播放）
 * - 机头朝 +X，尺寸与场景占位模型一致（盘径约 0.5m）
 * - 前置眼灯命名 HeadLamp_Eye：组件按 /HeadLamp/ 收集，障碍红警自动生效
 *
 * 用法：node scripts/generate-spider-model.mjs
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import * as THREE from 'three'
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js'

/* Node 环境补丁：GLTFExporter 依赖 FileReader */
if (typeof globalThis.FileReader === 'undefined') {
  globalThis.FileReader = class {
    readAsArrayBuffer(blob) {
      blob.arrayBuffer().then((buf) => {
        this.result = buf
        this.onloadend?.({ target: this })
        this.onload?.({ target: this })
      })
    }
  }
}

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const outPath = resolve(root, 'public/models/robot/spider-bot.glb')

const shellMat = new THREE.MeshStandardMaterial({ color: 0x2aa06e, metalness: 0.45, roughness: 0.4 })
const darkMat = new THREE.MeshStandardMaterial({ color: 0x22262e, metalness: 0.3, roughness: 0.8 })
const jointMat = new THREE.MeshStandardMaterial({ color: 0x9fe8ff, metalness: 0.7, roughness: 0.2 })
const eyeMat = new THREE.MeshStandardMaterial({ color: 0x5ad691, metalness: 0.4, roughness: 0.3, emissive: 0x1c5a37 })

const spider = new THREE.Group()
spider.name = 'SpiderBot'

/* 机身：下盘 + 上罩（圆盘形态，与占位模型一致） */
const base = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.26, 0.12, 16), shellMat)
base.name = 'Shell'
base.position.y = 0.22
const dome = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.19, 0.09, 14), darkMat)
dome.name = 'Dome'
dome.position.y = 0.32
spider.add(base, dome)

/* 传感器头：顶置旋转扫描头（组件红警/降级逻辑与 CAR 的 LidarHead 同构） */
const sensorPost = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.025, 0.07, 8), darkMat)
sensorPost.name = 'SensorPost'
sensorPost.position.y = 0.4
const sensorHead = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.05, 0.045, 12), jointMat)
sensorHead.name = 'SensorHead'
sensorHead.position.y = 0.45
spider.add(sensorPost, sensorHead)

/* 前置眼灯（+X 机头方向，障碍过近时由组件切红色 emissive） */
const eye = new THREE.Mesh(new THREE.SphereGeometry(0.035, 10, 10), eyeMat)
eye.name = 'HeadLamp_Eye'
eye.position.set(0.24, 0.24, 0)
spider.add(eye)

/* 8 足：LegPivot_i（基础朝向）> LegSwing_i（动画摆动层）> 腿段
   摆动必须挂在无基础旋转的内层节点上，否则 quaternion 轨道会覆盖朝向 */
const legGeo = new THREE.BoxGeometry(0.24, 0.03, 0.03)
legGeo.rotateZ(-0.55) /* 腿段沿 +X 外伸且末端下探 */
const footGeo = new THREE.SphereGeometry(0.022, 8, 8)
const swings = []
for (let i = 0; i < 8; i += 1) {
  const angle = (i / 8) * Math.PI * 2
  const pivot = new THREE.Group()
  pivot.name = `LegPivot_${i}`
  pivot.position.set(Math.cos(angle) * 0.24, 0.2, Math.sin(angle) * 0.24)
  pivot.rotation.y = -angle + Math.PI / 2
  const swing = new THREE.Group()
  swing.name = `LegSwing_${i}`
  const leg = new THREE.Mesh(legGeo, darkMat)
  leg.name = `Leg_${i}`
  leg.position.x = 0.11
  const foot = new THREE.Mesh(footGeo, jointMat)
  foot.name = `Foot_${i}`
  foot.position.set(0.21, -0.12, 0)
  swing.add(leg, foot)
  pivot.add(swing)
  spider.add(pivot)
  swings.push(swing)
}

/* 动画 Clip "walk"：8 足交替相位摆动（绕各自局部 Y）+ 传感器头旋转
   关键帧 ≥3（首尾恒等四元数 slerp 会不动）；偶数腿与奇数腿相位相反形成步态 */
const tracks = []
const phase = (offset) => [0, 1, 2, 3, 4].map((i) => i / 4 + offset)
const swingQs = (offset, amp) => [0, 1, 2, 3, 4].map((i) =>
  new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.sin((i / 4) * Math.PI * 2 + offset) * amp)
)
for (let i = 0; i < swings.length; i += 1) {
  const amp = 0.3
  const offset = i % 2 === 0 ? 0 : Math.PI
  tracks.push(new THREE.QuaternionKeyframeTrack(
    `${swings[i].name}.quaternion`,
    phase(0),
    swingQs(offset, amp).flatMap((qq) => [qq.x, qq.y, qq.z, qq.w])
  ))
}
{
  const n = 5
  const qs = []
  for (let i = 0; i < n; i += 1) {
    qs.push(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), (i / (n - 1)) * Math.PI * 2))
  }
  tracks.push(new THREE.QuaternionKeyframeTrack(
    'SensorHead.quaternion',
    Array.from({ length: n }, (_, i) => i / (n - 1)),
    qs.flatMap((qq) => [qq.x, qq.y, qq.z, qq.w])
  ))
}
const clip = new THREE.AnimationClip('walk', 1, tracks)

/* 导出 GLB */
const exporter = new GLTFExporter()
exporter.parse(
  spider,
  async (gltf) => {
    await mkdir(dirname(outPath), { recursive: true })
    const buffer = gltf instanceof ArrayBuffer ? Buffer.from(gltf) : Buffer.from(JSON.stringify(gltf))
    await writeFile(outPath, buffer)
    const kb = (buffer.length / 1024).toFixed(1)
    console.log(`OK: ${outPath} (${kb} KB, ${gltf instanceof ArrayBuffer ? 'GLB binary' : 'GLTF json'})`)
  },
  (err) => { console.error('export failed:', err); process.exit(1) },
  { binary: true, animations: [clip], onlyVisible: true }
)
