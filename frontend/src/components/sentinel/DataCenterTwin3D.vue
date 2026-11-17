<template>
  <div
    ref="host"
    class="dc3d"
    :class="{ 'dc3d--static': reduced }"
    role="img"
    :aria-label="ariaLabel"
  >
    <p v-if="!webglReady" class="dc3d__fallback">
      当前环境未启用 WebGL，3D 机房视图降级为机柜列表——数据本身不受影响。
    </p>
  </div>
</template>

<script setup>
/**
 * DataCenterTwin3D — 云服务器厂房 3D 虚拟场景
 *
 * 数据红线：场景只负责「把传入的采样画出来」。
 * 机柜颜色、机器人位置、告警脉冲全部来自 props，组件内不生成任何业务数据。
 * 生命周期：ResizeObserver 自适应；onBeforeUnmount 逐个释放 geometry/material/renderer。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AdditiveBlending,
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  CircleGeometry,
  CylinderGeometry,
  EdgesGeometry,
  Group,
  GridHelper,
  LineBasicMaterial,
  LineLoop,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Raycaster,
  Scene,
  SphereGeometry,
  Vector2,
  WebGLRenderer
} from 'three'

const props = defineProps({
  layout: { type: Array, default: () => [] },
  telemetry: { type: Array, default: () => [] },
  robot: { type: Object, default: () => ({ x: 0, z: 0, heading: 0 }) },
  waypoints: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' }
})
const emit = defineEmits(['select'])

const host = ref(null)
const webglReady = ref(false)
const reduced = ref(false)

const LEVEL_COLORS = { ok: 0x4f9fbf, warn: 0xd9b96d, critical: 0xe5484d, unknown: 0x6b7480 }

const ariaLabel = computed(() => {
  const list = props.telemetry || []
  const hot = list.filter(item => item.level !== 'ok').length
  return `机房 3D 孪生视图：${list.length} 个机柜，${hot} 个机柜指标越界`
})

let disposeScene = () => {}
let syncScene = () => {}

onMounted(() => {
  try { reduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { /* SSR */ }
  if (!host.value) return

  let renderer
  try {
    renderer = new WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' })
  } catch {
    return
  }
  const element = host.value
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  element.appendChild(renderer.domElement)
  webglReady.value = true

  const scene = new Scene()
  const camera = new PerspectiveCamera(45, 1, 0.1, 200)
  camera.position.set(7.6, 7.2, 9.4)
  camera.lookAt(0, 0.9, 0)
  const root = new Group()
  scene.add(root)

  /* 地面与冷通道：静态几何，一次创建、卸载时统一释放。 */
  const floorGeo = new PlaneGeometry(22, 16)
  const floorMat = new MeshBasicMaterial({ color: 0x0b1720, transparent: true, opacity: 0.55 })
  const floor = new Mesh(floorGeo, floorMat)
  floor.rotation.x = -Math.PI / 2
  root.add(floor)

  const grid = new GridHelper(22, 22, 0x1f3a47, 0x142a34)
  grid.position.y = 0.01
  root.add(grid)

  const aisleGeo = new PlaneGeometry(13, 1.9)
  const aisleMat = new MeshBasicMaterial({ color: 0x1f6f8b, transparent: true, opacity: 0.16, blending: AdditiveBlending, depthWrite: false })
  const aisle = new Mesh(aisleGeo, aisleMat)
  aisle.rotation.x = -Math.PI / 2
  aisle.position.y = 0.02
  root.add(aisle)

  const RACK_W = 0.86
  const RACK_H = 1.9
  const RACK_D = 1.05
  const boxGeo = new BoxGeometry(RACK_W, RACK_H, RACK_D)
  const edgeGeo = new EdgesGeometry(boxGeo)
  const glowGeo = new CircleGeometry(0.26, 20)
  const racks = new Map()

  function ensureRack(rack) {
    let entry = racks.get(rack.id)
    if (entry) return entry
    const group = new Group()
    group.position.set(rack.x, RACK_H / 2, rack.z)
    const bodyMat = new MeshBasicMaterial({ color: LEVEL_COLORS.ok, transparent: true, opacity: 0.72 })
    const body = new Mesh(boxGeo, bodyMat)
    const edgeMat = new LineBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0.32 })
    const edges = new LineSegments(edgeGeo, edgeMat)
    const glowMat = new MeshBasicMaterial({ color: LEVEL_COLORS.warn, transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false })
    const glow = new Mesh(glowGeo, glowMat)
    glow.rotation.x = -Math.PI / 2
    glow.position.y = RACK_H / 2 + 0.02
    group.add(body, edges, glow)
    root.add(group)
    entry = { group, body, bodyMat, edgeMat, glow, glowMat }
    racks.set(rack.id, entry)
    return entry
  }

  function syncRacks() {
    const wanted = new Set((props.layout || []).map(rack => rack.id))
    for (const [id, entry] of racks) {
      if (wanted.has(id)) continue
      root.remove(entry.group)
      entry.bodyMat.dispose()
      entry.edgeMat.dispose()
      entry.glowMat.dispose()
      racks.delete(id)
    }
    const levels = new Map((props.telemetry || []).map(item => [item.id, item.level]))
    for (const rack of props.layout || []) {
      const entry = ensureRack(rack)
      const level = levels.get(rack.id) || 'ok'
      const color = LEVEL_COLORS[level] ?? LEVEL_COLORS.ok
      entry.bodyMat.color.setHex(color)
      entry.bodyMat.opacity = level === 'ok' ? 0.66 : 0.86
      entry.edgeMat.color.setHex(props.selectedId === rack.id ? 0xffffff : 0x9fe8ff)
      entry.edgeMat.opacity = props.selectedId === rack.id ? 0.95 : 0.32
      entry.glowMat.color.setHex(color)
      if (level === 'ok') entry.glowMat.opacity = 0
      entry.level = level
    }
  }

  /* 巡逻路线：用 LineLoop 画出闭合轨迹，颜色比机柜边线淡一档。 */
  const routeGeo = new BufferGeometry()
  const routeMat = new LineBasicMaterial({ color: 0x7ad7f5, transparent: true, opacity: 0.3 })
  const route = new LineLoop(routeGeo, routeMat)
  route.position.y = 0.05
  root.add(route)
  let routeSignature = ''

  function syncRoute() {
    const points = props.waypoints || []
    /* 路线只在路点变化时重建，避免每秒刷新都重新分配 GPU 缓冲。 */
    const signature = points.map(point => `${point.x},${point.z}`).join('|')
    route.visible = points.length > 1
    if (signature === routeSignature) return
    routeSignature = signature
    const coords = new Float32Array(points.length * 3)
    points.forEach((point, index) => {
      coords[index * 3] = point.x
      coords[index * 3 + 1] = 0
      coords[index * 3 + 2] = point.z
    })
    routeGeo.setAttribute('position', new BufferAttribute(coords, 3))
    routeGeo.computeBoundingSphere()
  }

  /* 机器人：机体 + 桅杆 + 顶部信标，位置直接来自 props.robot。 */
  const robotGroup = new Group()
  const robotBodyGeo = new BoxGeometry(0.62, 0.3, 0.46)
  const robotBodyMat = new MeshBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0.92 })
  const robotBody = new Mesh(robotBodyGeo, robotBodyMat)
  robotBody.position.y = 0.18
  const mastGeo = new CylinderGeometry(0.05, 0.05, 0.72, 10)
  const mastMat = new MeshBasicMaterial({ color: 0x7ad7f5, transparent: true, opacity: 0.75 })
  const mast = new Mesh(mastGeo, mastMat)
  mast.position.y = 0.68
  const beaconGeo = new SphereGeometry(0.14, 14, 12)
  const beaconMat = new MeshBasicMaterial({ color: 0x7ad7f5, transparent: true, opacity: 0.9, blending: AdditiveBlending, depthWrite: false })
  const beacon = new Mesh(beaconGeo, beaconMat)
  beacon.position.y = 1.06
  const haloGeo = new CircleGeometry(0.34, 20)
  const haloMat = new MeshBasicMaterial({ color: 0x7ad7f5, transparent: true, opacity: 0.24, blending: AdditiveBlending, depthWrite: false })
  const halo = new Mesh(haloGeo, haloMat)
  halo.rotation.x = -Math.PI / 2
  halo.position.y = 0.03
  robotGroup.add(robotBody, mast, beacon, halo)
  root.add(robotGroup)

  function syncRobot() {
    const spot = props.robot || { x: 0, z: 0, heading: 0 }
    robotGroup.position.set(spot.x, 0, spot.z)
    robotGroup.rotation.y = spot.heading || 0
  }

  syncScene = () => {
    syncRacks()
    syncRoute()
    syncRobot()
  }

  /* 点击机柜选中：用射线拾取，命中最近机柜后回传 id，父视图负责展示详情。 */
  const raycaster = new Raycaster()
  const pointer = new Vector2()
  function toNdc(event) {
    const rect = renderer.domElement.getBoundingClientRect()
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  }
  function onClick(event) {
    toNdc(event)
    raycaster.setFromCamera(pointer, camera)
    const targets = [...racks.values()].map(entry => entry.body)
    const hit = raycaster.intersectObjects(targets, false)[0]
    if (!hit) return
    const id = [...racks.entries()].find(([, entry]) => entry.body === hit.object)?.[0]
    if (id) emit('select', id)
  }
  renderer.domElement.addEventListener('click', onClick)

  function resize() {
    const w = Math.max(1, element.clientWidth)
    const h = Math.max(1, element.clientHeight)
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
  ro?.observe(element)
  resize()
  syncScene()

  /* 渲染循环：默认静止时也渲染一帧；有越界机柜时只有顶部光晕呼吸。 */
  let frame = 0
  let clock = 0
  let last = 0
  function loop(now) {
    frame = window.requestAnimationFrame(loop)
    const dt = last ? Math.min((now - last) / 1000, 0.06) : 0.016
    last = now
    if (reduced.value) return
    clock += dt
    for (const entry of racks.values()) {
      if (entry.level === 'ok') continue
      const period = entry.level === 'critical' ? 1.1 : 2.6
      const wave = 0.5 + 0.5 * Math.sin((clock / period) * Math.PI * 2)
      entry.glowMat.opacity = 0.12 + wave * 0.34
      entry.glow.scale.setScalar(1 + wave * 0.24)
    }
    beaconMat.opacity = 0.4 + (0.5 + 0.5 * Math.sin(clock * 2.4)) * 0.4
    renderer.render(scene, camera)
  }
  renderer.render(scene, camera)
  if (!reduced.value) frame = window.requestAnimationFrame(loop)

  disposeScene = () => {
    if (frame) window.cancelAnimationFrame(frame)
    frame = 0
    ro?.disconnect()
    renderer.domElement.removeEventListener('click', onClick)
    for (const entry of racks.values()) {
      entry.bodyMat.dispose()
      entry.edgeMat.dispose()
      entry.glowMat.dispose()
    }
    racks.clear()
    boxGeo.dispose(); edgeGeo.dispose(); glowGeo.dispose()
    floorGeo.dispose(); floorMat.dispose()
    aisleGeo.dispose(); aisleMat.dispose()
    routeGeo.dispose(); routeMat.dispose()
    robotBodyGeo.dispose(); robotBodyMat.dispose()
    mastGeo.dispose(); mastMat.dispose()
    beaconGeo.dispose(); beaconMat.dispose()
    haloGeo.dispose(); haloMat.dispose()
    grid.geometry.dispose(); grid.material.dispose()
    renderer.dispose()
    if (renderer.domElement.parentNode === element) element.removeChild(renderer.domElement)
  }
})

watch(
  () => [props.layout, props.telemetry, props.robot, props.waypoints, props.selectedId],
  () => { if (webglReady.value) syncScene() },
  { deep: true }
)

onBeforeUnmount(() => disposeScene())
</script>

<style scoped>
.dc3d {
  position: relative;
  min-height: 420px;
  height: clamp(420px, 52vh, 620px);
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 12px;
  background:
    radial-gradient(circle at 50% 0%, rgba(122, 215, 245, .09), transparent 62%),
    var(--smart-bg, #071018);
  overflow: hidden;
}
.dc3d :deep(canvas) { display: block; width: 100%; height: 100%; }
.dc3d__fallback {
  margin: 0;
  padding: 18px;
  color: var(--smart-muted, #92a6b5);
  font-size: 12px;
  line-height: 1.7;
}
@media (max-width: 860px) {
  .dc3d { min-height: 320px; height: 44vh; }
}
</style>
