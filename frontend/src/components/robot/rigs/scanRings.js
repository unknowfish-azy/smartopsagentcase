/**
 * 地面扫描环：主环 + 错峰副环 + 两圈实色描边环。
 *
 * 加色混合（AdditiveBlending）在白底浅色主题上几乎看不见，所以每条环外沿再叠一圈
 * 常态混合的细描边；描边透明度由「扫描环亮度」派生，保证深色 / 浅色主题都清晰。
 * 四足、人形与 GLB 动效层共用本模块，尺寸由调用方按各自机身比例传入。
 */

import { AdditiveBlending, DoubleSide, Group, Mesh, MeshBasicMaterial, RingGeometry } from 'three'
import { scanRing } from './effects.js'

/** 描边宽度占外半径的比例：细一圈即可，太宽会看成实心盘 */
const STROKE_RATIO = 0.07
/** 描边透明度上限：主环 / 副环 */
const STROKE_MAX_OPACITY = [0.85, 0.55]
/** 描边相对加色环的亮度倍率 */
const STROKE_GAIN = 2.2

/**
 * @param {{color: number, innerRadius: number, outerRadius: number, baseY?: number, segments?: number}} options
 *   baseY：环所在高度（相对 rig 原点，通常是地面上方几毫米，避免与地面 z-fighting）
 */
export function buildScanRings({ color, innerRadius, outerRadius, baseY = 0.008, segments = 48 }) {
  const group = new Group()
  group.name = 'scan-rings'

  const ringGeo = new RingGeometry(innerRadius, outerRadius, segments)
  ringGeo.rotateX(-Math.PI / 2)
  const strokeGeo = new RingGeometry(outerRadius * (1 - STROKE_RATIO), outerRadius, segments)
  strokeGeo.rotateX(-Math.PI / 2)

  const makeMesh = (geometry, name, y, additive, opacity) => {
    const material = new MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      depthWrite: false,
      side: DoubleSide,
      ...(additive ? { blending: AdditiveBlending } : {})
    })
    const mesh = new Mesh(geometry, material)
    mesh.name = name
    mesh.position.y = y
    group.add(mesh)
    return mesh
  }

  /* 主环 / 副环用加色混合做「能量感」，描边环用常态混合保证可见性 */
  const main = makeMesh(ringGeo, 'fx-ring-main', baseY, true, 0.35)
  const echo = makeMesh(ringGeo, 'fx-ring-echo', baseY + 0.001, true, 0.18)
  const strokeMain = makeMesh(strokeGeo, 'fx-ring-stroke-main', baseY + 0.002, false, 0.6)
  const strokeEcho = makeMesh(strokeGeo, 'fx-ring-stroke-echo', baseY + 0.003, false, 0.36)

  /**
   * @param {number} elapsed 累计秒数
   * @param {object} fx resolveEffectConfig 的结果
   * @param {boolean} stale 心跳是否超时
   */
  function update(elapsed, fx, stale) {
    const base = { stale, period: fx.scanPeriod, maxOpacity: fx.ringMaxOpacity, staleOpacity: fx.ringStaleOpacity }

    const wave = scanRing(elapsed, base)
    main.scale.setScalar(wave.scale)
    main.material.opacity = wave.opacity
    strokeMain.scale.setScalar(wave.scale)
    strokeMain.material.opacity = Math.min(STROKE_MAX_OPACITY[0], wave.opacity * STROKE_GAIN)

    const echoWave = scanRing(elapsed, { ...base, phase: 0.5 })
    echo.scale.setScalar(echoWave.scale)
    echo.material.opacity = echoWave.opacity * 0.6
    strokeEcho.scale.setScalar(echoWave.scale)
    strokeEcho.material.opacity = Math.min(STROKE_MAX_OPACITY[1], echoWave.opacity * STROKE_GAIN)
  }

  return { group, update }
}
