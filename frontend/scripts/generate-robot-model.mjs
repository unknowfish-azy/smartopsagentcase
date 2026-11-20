/**
 * 程序化生成巡检车 GLB + rig 元数据。
 *
 * 产出：
 * - frontend/public/models/robot/patrol-car.glb
 * - frontend/public/models/robot/patrol-car.rig.json
 *
 * 几何来自 src/components/robot/models/patrolCarModel.js，与运行时兜底同源；
 * 动画不烘焙进 GLB：轮速 / LiDAR 由 rigs/patrolCarRig.js 按真实位移速度驱动。
 *
 * 用法：node scripts/generate-robot-model.mjs
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js'
import { buildPatrolCarModel, buildPatrolCarRigMeta } from '../src/components/robot/models/patrolCarModel.js'

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
const outPath = resolve(root, 'public/models/robot/patrol-car.glb')
const metaPath = resolve(root, 'public/models/robot/patrol-car.rig.json')

const { root: model } = buildPatrolCarModel()
const metadata = buildPatrolCarRigMeta()

const exporter = new GLTFExporter()
exporter.parse(
  model,
  async (gltf) => {
    await mkdir(dirname(outPath), { recursive: true })
    const buffer = gltf instanceof ArrayBuffer ? Buffer.from(gltf) : Buffer.from(JSON.stringify(gltf))
    await writeFile(outPath, buffer)
    await writeFile(metaPath, `${JSON.stringify(metadata, null, 2)}\n`)
    const kb = (buffer.length / 1024).toFixed(1)
    console.log(`OK: ${outPath} (${kb} KB, ${gltf instanceof ArrayBuffer ? 'GLB binary' : 'GLTF json'})`)
    console.log(`OK: ${metaPath}`)
  },
  (err) => { console.error('export failed:', err); process.exit(1) },
  { binary: true, onlyVisible: true }
)
