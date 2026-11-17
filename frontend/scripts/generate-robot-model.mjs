/**
 * 程序化生成巡检机器人车 GLB（M8b 真模型接入的第一版资产）。
 *
 * 产出：frontend/public/models/robot/patrol-car.glb
 * - PBR 材质（MeshStandardMaterial → glTF metallic-roughness）
 * - 轮子 4 个独立旋转动画通道 + LiDAR 扫描动画（Clip "drive"，加载后由 AnimationMixer 播放）
 * - 机头朝 +X，尺寸与场景占位模型一致（车长约 0.5m）
 *
 * 用法：node scripts/generate-robot-model.mjs
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import * as THREE from 'three'
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js'

/* Node 环境补丁：GLTFExporter 依赖 FileReader（无纹理时也走该路径序列化二进制） */
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
const outPath = resolve(root, 'public/models/robot/patrol-car.glb')

const bodyMat = new THREE.MeshStandardMaterial({ color: 0x2f6fd0, metalness: 0.55, roughness: 0.35 })
const darkMat = new THREE.MeshStandardMaterial({ color: 0x22262e, metalness: 0.3, roughness: 0.8 })
const tireMat = new THREE.MeshStandardMaterial({ color: 0x111318, metalness: 0.1, roughness: 0.95 })
const lidarMat = new THREE.MeshStandardMaterial({ color: 0x9fe8ff, metalness: 0.7, roughness: 0.2 })
const lampMat = new THREE.MeshStandardMaterial({ color: 0x5ad691, metalness: 0.4, roughness: 0.3, emissive: 0x1c5a37 })

const car = new THREE.Group()
car.name = 'PatrolCar'

/* 底盘 + 顶盖 */
const chassis = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.14, 0.3), bodyMat)
chassis.name = 'Chassis'
chassis.position.y = 0.15
const roof = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.09, 0.22), darkMat)
roof.name = 'Roof'
roof.position.set(-0.06, 0.26, 0)
car.add(chassis, roof)

/* 4 轮：独立 Group（动画作用在 wheel.quaternion），轮轴沿 Z（车宽方向） */
const wheelGeo = new THREE.CylinderGeometry(0.075, 0.075, 0.055, 18)
wheelGeo.rotateX(Math.PI / 2)
const hubGeo = new THREE.CylinderGeometry(0.03, 0.03, 0.06, 12)
hubGeo.rotateX(Math.PI / 2)
const wheels = []
for (const [wx, wz] of [[0.17, 0.16], [0.17, -0.16], [-0.17, 0.16], [-0.17, -0.16]]) {
  const pivot = new THREE.Group()
  pivot.name = `WheelPivot_${wheels.length}`
  pivot.position.set(wx, 0.075, wz)
  const tire = new THREE.Mesh(wheelGeo, tireMat)
  tire.name = `Tire_${wheels.length}`
  const hub = new THREE.Mesh(hubGeo, darkMat)
  hub.name = `Hub_${wheels.length}`
  pivot.add(tire, hub)
  car.add(pivot)
  wheels.push(pivot)
}

/* LiDAR 云台：立柱 + 旋转扫描头 */
const lidarPost = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.03, 0.1, 10), darkMat)
lidarPost.name = 'LidarPost'
lidarPost.position.set(0.12, 0.32, 0)
const lidarHead = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.05, 14), lidarMat)
lidarHead.name = 'LidarHead'
lidarHead.position.set(0.12, 0.39, 0)
car.add(lidarPost, lidarHead)

/* 天线 */
const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.16, 6), darkMat)
antenna.name = 'Antenna'
antenna.position.set(-0.16, 0.36, 0.06)
const antennaTip = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 8), lampMat)
antennaTip.name = 'AntennaTip'
antennaTip.position.set(-0.16, 0.445, 0.06)
car.add(antenna, antennaTip)

/* 前大灯（机头 +X 方向 2 个） */
const lampGeo = new THREE.BoxGeometry(0.02, 0.03, 0.05)
for (const wz of [0.1, -0.1]) {
  const lamp = new THREE.Mesh(lampGeo, lampMat)
  lamp.name = `HeadLamp_${wz > 0 ? 'L' : 'R'}`
  lamp.position.set(0.252, 0.15, wz)
  car.add(lamp)
}

/* 动画 Clip "drive"：4 轮绕 Z 轴滚动（quaternion 通道）+ LiDAR 扫描头绕 Y 旋转
   注意：quaternion 关键帧至少 3 个 —— 0 和 2π 都是恒等四元数，两端 slerp 会一动不动 */
const tracks = []
for (const pivot of wheels) {
  const n = 5
  const qs = []
  for (let i = 0; i < n; i += 1) {
    qs.push(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), (i / (n - 1)) * Math.PI * 2))
  }
  tracks.push(new THREE.QuaternionKeyframeTrack(
    `${pivot.name}.quaternion`,
    Array.from({ length: n }, (_, i) => i / (n - 1)),
    qs.flatMap((qq) => [qq.x, qq.y, qq.z, qq.w])
  ))
}
{
  const n = 5
  const qs = []
  for (let i = 0; i < n; i += 1) {
    qs.push(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), (i / (n - 1)) * Math.PI * 2))
  }
  tracks.push(new THREE.QuaternionKeyframeTrack(
    'LidarHead.quaternion',
    Array.from({ length: n }, (_, i) => i / (n - 1)),
    qs.flatMap((qq) => [qq.x, qq.y, qq.z, qq.w])
  ))
}
const clip = new THREE.AnimationClip('drive', 1, tracks)

/* 导出 GLB */
const exporter = new GLTFExporter()
exporter.parse(
  car,
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
