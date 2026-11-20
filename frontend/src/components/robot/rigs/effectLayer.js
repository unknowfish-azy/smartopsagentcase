/**
 * 通用动效层：给 GLB 形态（CAR 轮式底盘 / SPIDER 六足）挂载与四足、人形一致的效果。
 *
 * 为什么不直接改 GLB：真实模型来自美术资产，节点命名与朝向不可控；这里按模型包围盒
 * 在顶部中心挂 LiDAR 桅杆、后方挂状态灯，地面铺扩散扫描环，效果尺寸按机身体积归一化，
 * 与 rigs/quadrupedRig.js 的视觉比例对齐。模型自身的驱动动画、材质状态不受影响。
 *
 * 挂载方式：效果层挂在场景上而不是模型内，避免 GLB 自身 scale 把灯球缩成看不见的点；
 * 每帧 `sync(robot)` 同步本体的位置与朝向，效果随本体移动/转向。
 */

import {
  AdditiveBlending, Box3, CircleGeometry, CylinderGeometry, DoubleSide, Group, Mesh,
  MeshBasicMaterial, MeshStandardMaterial, PlaneGeometry, PointLight, SphereGeometry,
  TorusGeometry, Vector3
} from 'three'
import {
  BEACON_STATUS, beaconGlow, beaconPulse, resolveBeaconStatus, resolveEffectConfig, resolveGlowGain
} from './effects.js'
import { buildScanRings } from './scanRings.js'

/** 归一化基准：四足 rig 放大 2.2 倍后的机身体长（米），效果尺寸以此为 1.0。 */
const REFERENCE_FOOTPRINT = 1.36
/** 尺寸缩放上下限：四足 rig 的机身是 1.36，GLB 里 0.5 米级的小车按比例缩到 0.37 左右才不会被光晕糊住 */
const MIN_SCALE = 0.35
const MAX_SCALE = 2.2

/**
 * 量取模型包围盒（模型自身局部坐标）。调用方需保证模型已加入场景且处于初始位姿。
 * @param {import('three').Object3D} object
 * @returns {{centerX:number, centerZ:number, minY:number, topY:number, footprint:number, scale:number}}
 */
export function measureRobotBounds(object) {
  /* 位姿中立化后再量：模型可能是复用的缓存对象，带着上一轮的位移/朝向 */
  const prevPosition = object.position.clone()
  const prevRotation = object.rotation.clone()
  object.position.set(0, 0, 0)
  object.rotation.set(0, 0, 0)
  object.updateMatrixWorld(true)
  const box = new Box3().setFromObject(object)
  object.position.copy(prevPosition)
  object.rotation.copy(prevRotation)
  object.updateMatrixWorld(true)

  const size = box.getSize(new Vector3())
  const footprint = Math.max(size.x, size.z, size.y)
  return {
    centerX: (box.min.x + box.max.x) / 2,
    centerZ: (box.min.z + box.max.z) / 2,
    minY: box.min.y,
    topY: box.max.y,
    footprint,
    scale: Math.min(MAX_SCALE, Math.max(MIN_SCALE, footprint / REFERENCE_FOOTPRINT))
  }
}

/** 所有形态统一到的视觉体长（米），与四足 rig 放大 2.2 倍后的观感对齐。 */
export const ROBOT_DISPLAY_FOOTPRINT = REFERENCE_FOOTPRINT

/**
 * 把模型缩放到统一视觉体长：同为 15m 地图，形态之间不再出现「狗很大、车很小」。
 * 直接改模型根节点的 scale（不影响 rig 容器位姿与效果层尺寸计算）。
 * @param {import('three').Object3D} object
 * @param {number} [target] 目标包围盒最长边（米）
 * @returns {number} 实际应用的缩放系数
 */
export function normalizeRobotFootprint(object, target = ROBOT_DISPLAY_FOOTPRINT) {
  const { footprint } = measureRobotBounds(object)
  if (!Number.isFinite(footprint) || footprint <= 1e-6) return 1
  const scale = target / footprint
  object.scale.multiplyScalar(scale)
  object.updateMatrixWorld(true)
  return scale
}

function fallbackBounds() {
  return { centerX: 0, centerZ: 0, minY: 0, topY: 0.5, footprint: REFERENCE_FOOTPRINT, scale: 1 }
}

/**
 * 构建动效层（不含模型本体）。
 * @param {{accentHex?: number, effects?: object, bounds?: ReturnType<typeof measureRobotBounds>,
 *   theme?: string}} options
 */
export function buildEffectLayer({ accentHex = 0x5b8cff, effects, bounds, theme = 'light' } = {}) {
  let fx = resolveEffectConfig(effects)
  let themeApplied = theme
  let glowGain = resolveGlowGain(theme)
  const b = bounds || fallbackBounds()
  const s = Number.isFinite(b.scale) ? b.scale : 1

  const group = new Group()
  group.name = 'robot-effect-layer'

  const mastMat = new MeshStandardMaterial({
    color: 0x22262e, metalness: 0.55, roughness: 0.5, transparent: true, opacity: 1
  })
  const domeMat = new MeshStandardMaterial({
    color: 0x121418, metalness: 0.9, roughness: 0.15, transparent: true, opacity: 1
  })
  const accentMat = new MeshStandardMaterial({
    color: accentHex, metalness: 0.35, roughness: 0.42, transparent: true, opacity: 1
  })
  const beaconMat = new MeshStandardMaterial({
    color: 0x5ad691, emissive: 0x1c5a37, emissiveIntensity: 1.4, transparent: true, opacity: 1
  })

  /* ---------- LiDAR：桅杆 + 半球罩 + 装饰环 ---------- */
  const lidarBaseY = b.topY + 0.02 * s

  const lidarMast = new Mesh(new CylinderGeometry(0.012 * s, 0.014 * s, 0.1 * s, 10), mastMat)
  lidarMast.position.set(b.centerX, lidarBaseY + 0.05 * s, b.centerZ)
  group.add(lidarMast)

  const lidar = new Group()
  lidar.position.set(b.centerX, lidarBaseY + 0.1 * s, b.centerZ)
  group.add(lidar)

  const lidarDome = new Mesh(new SphereGeometry(0.114 * s, 18, 12, 0, Math.PI * 2, 0, Math.PI / 2), domeMat)
  lidar.add(lidarDome)

  const lidarRing = new Mesh(new TorusGeometry(0.099 * s, 0.0132 * s, 8, 20), accentMat)
  lidarRing.rotation.x = Math.PI / 2
  lidarRing.position.y = 0.026 * s
  lidar.add(lidarRing)

  /* 扫描扇面：随 LiDAR 同轴旋转的激光楔形 */
  const sweepMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.3, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const sweepRadius = 0.66 * s
  const sweep = new Mesh(new CircleGeometry(sweepRadius, 24, -Math.PI / 7, Math.PI * 2 / 7), sweepMat)
  sweep.rotation.x = -Math.PI / 2
  sweep.position.y = 0.013 * s
  lidar.add(sweep)

  /* 拖尾扇面：滞后于主扇面，形成「扫过」的残影 */
  const trailMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.12, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const trail = new Mesh(new CircleGeometry(sweepRadius, 24, -Math.PI / 7 - 0.62, Math.PI * 2 / 7), trailMat)
  trail.rotation.x = -Math.PI / 2
  trail.position.y = 0.011 * s
  lidar.add(trail)

  /* 激光线：从 LiDAR 前端水平射出的细长光束 */
  const beamGeo = new PlaneGeometry(1.36 * s, 0.022 * s)
  beamGeo.rotateX(-Math.PI / 2)
  beamGeo.translate(0.68 * s, 0.02 * s, 0)
  const beamMat = new MeshBasicMaterial({
    color: accentHex, transparent: true, opacity: 0.46, depthWrite: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  lidar.add(new Mesh(beamGeo, beamMat))

  /* ---------- 状态灯：灯球 + 外发光光晕 + 局部点光 ---------- */
  const beaconX = b.centerX - 0.34 * s
  const beaconBaseY = b.topY + 0.02 * s

  const beaconMast = new Mesh(new CylinderGeometry(0.008 * s, 0.01 * s, 0.075 * s, 8), mastMat)
  beaconMast.position.set(beaconX, beaconBaseY + 0.0375 * s, b.centerZ)
  group.add(beaconMast)

  const beaconPos = new Vector3(beaconX, beaconBaseY + 0.085 * s, b.centerZ)

  const beacon = new Mesh(new SphereGeometry(0.0308 * s, 12, 10), beaconMat)
  beacon.position.copy(beaconPos)
  group.add(beacon)

  const glowMat = new MeshBasicMaterial({
    /* 光晕不做深度测试：被车顶遮挡时也能透出，保证远景可见 */
    color: 0x5ad691, transparent: true, opacity: 0.16, depthWrite: false, depthTest: false,
    side: DoubleSide, blending: AdditiveBlending
  })
  const glow = new Mesh(new SphereGeometry(0.0924 * s, 16, 12), glowMat)
  glow.renderOrder = 3
  glow.position.copy(beaconPos)
  group.add(glow)

  const beaconLight = new PointLight(0x5ad691, 0, 2 * s, 2)
  beaconLight.position.copy(beaconPos)
  group.add(beaconLight)

  /* ---------- 地面扫描环（模型底面为地平面）：与四足 / 人形共用共享模块 ---------- */
  const ringY = (Number.isFinite(b.minY) ? b.minY : 0) + 0.008
  const rings = buildScanRings({ color: accentHex, innerRadius: 1.76 * s, outerRadius: 2.2 * s, baseY: ringY })
  group.add(rings.group)

  /* ---------- 运行时 ---------- */
  const materials = [mastMat, domeMat, accentMat, beaconMat]
  let staleApplied = false
  let beaconStatus = { key: 'idle', ...BEACON_STATUS.idle }
  let lidarSpin = 0
  let elapsed = 0

  /** 跟随本体位姿：位置与朝向取自模型的世界变换，尺寸与缩放无关。 */
  function sync(object) {
    if (!object) return
    group.position.set(object.position.x, group.position.y, object.position.z)
    group.rotation.y = object.rotation.y
  }

  function update({ dt = 0.016 } = {}) {
    elapsed += dt
    /* LiDAR：常态匀速扫描，告警态加速 */
    lidarSpin += dt * (beaconStatus.source === 'alarm' ? fx.lidarAlarmSpeed : fx.lidarSpeed)
    lidar.rotation.y = lidarSpin
    /* 状态灯：颜色随业务状态，节奏 = 基准频率 × 状态倍率；心跳超时压暗为常亮微光 */
    const pulse = beaconPulse(elapsed, {
      stale: staleApplied,
      hz: (beaconStatus.source === 'alarm' ? fx.beaconAlarmHz : fx.beaconIdleHz) * beaconStatus.factor,
      intensity: beaconStatus.intensity,
      scaleAmp: beaconStatus.scaleAmp
    })
    beaconMat.emissiveIntensity = pulse.intensity
    beacon.scale.setScalar(pulse.scale)
    /* 外发光光晕 + 局部点光：把呼吸亮度放大成肉眼可见的光圈 */
    const glowState = beaconGlow(pulse, themeApplied)
    glowMat.opacity = glowState.opacity
    glow.scale.setScalar(glowState.scale)
    beaconLight.intensity = pulse.intensity * 0.38 * glowGain.light
    /* 扫描扇面 / 拖尾 / 光束亮度随旋转轻微呼吸 */
    const sweepWave = 0.5 + 0.5 * Math.sin(elapsed * 4)
    sweepMat.opacity = 0.24 + 0.16 * sweepWave
    trailMat.opacity = 0.08 + 0.06 * sweepWave
    beamMat.opacity = 0.36 + 0.24 * sweepWave
    /* 地面扫描环：主环 + 错峰副环向外扩散并淡出（含描边） */
    rings.update(elapsed, fx, staleApplied)
  }

  function setStale(stale) {
    if (stale === staleApplied) return
    staleApplied = stale
    materials.forEach((m) => { m.opacity = stale ? 0.3 : 1 })
  }

  /** 由真实遥测/模式更新状态灯颜色：离线灰、故障红、障碍/低电琥珀、自主蓝、人工青、常态绿。 */
  function setBeaconStatus(input) {
    const next = resolveBeaconStatus(input)
    if (next.key === beaconStatus.key) return
    beaconStatus = next
    beaconMat.color.setHex(next.color)
    beaconMat.emissive.setHex(next.emissive)
    glowMat.color.setHex(next.color)
    beaconLight.color.setHex(next.color)
  }

  /** 运行时热更新动效参数（调节面板拖动滑杆时无需重建）。 */
  function setEffects(next) {
    fx = resolveEffectConfig(next)
  }

  /** 主题切换时更新光晕 / 点光衰减（深色主题下抑制加色过曝）。 */
  function setTheme(next) {
    themeApplied = next
    glowGain = resolveGlowGain(next)
  }

  function dispose() {
    group.traverse((node) => {
      node.geometry?.dispose?.()
      node.material?.dispose?.()
    })
  }

  return {
    group, bounds: b, materials, beaconMat, sync, update, setStale, setBeaconStatus, setEffects, setTheme, dispose
  }
}
