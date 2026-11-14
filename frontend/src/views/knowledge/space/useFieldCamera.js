/* useFieldCamera.js
 *
 * CSS 3D 受限轨道相机 composable（DESIGN §5）。
 *   yaw:   ±35°       水平旋转
 *   pitch: 8°…52°     俯仰
 *   dist:  520…2600   相机到 target 的距离
 *   target: [cx, cy, 0]  相机看向的世界坐标
 *
 * 三机位预设：overlook / shelf / trace
 * Esc 三级回退：focus 平面 → 所在域 → overlook
 * focus billboard：lod === 'focus' 的平面 yaw 缓动到 0
 * 全部补间走 motionScheduler；prefers-reduced-motion 下时长 = 0，直接赋值。
 */

import { ref, computed, reactive } from 'vue'

export const ORBIT = {
  yawMin: -35, yawMax: 35,
  pitchMin: 8, pitchMax: 52,
  distMin: 520, distMax: 2600,
}

export const PRESET_NAMES = ['overlook', 'shelf', 'trace']

export function useFieldCamera (options = {}) {
  const { reducedMotion = false } = options

  // —— 状态 ——
  const yaw   = ref(0)    // deg
  const pitch = ref(28)   // deg（overlook 是 28°）
  const dist  = ref(1500) // px
  const target = reactive({ x: 0, y: 300, z: 0 })
  const preset = ref('overlook')
  const focusPlaneId = ref(null)     // 当前 focus 的平面 id（用于 Esc 回退）
  const focusDomainId = ref(null)    // focus 平面所在域（回退中间站）

  const clampYaw   = v => clamp(v, ORBIT.yawMin,   ORBIT.yawMax)
  const clampPitch = v => clamp(v, ORBIT.pitchMin, ORBIT.pitchMax)
  const clampDist  = v => clamp(v, ORBIT.distMin,  ORBIT.distMax)

  function clamp (v, a, b) { return v < a ? a : v > b ? b : v }

  // —— 当前相机位置（球坐标 → 直角坐标）——
  // yaw 绕 Y 轴（水平），pitch 绕 X 轴（俯仰）
  // CSS 3D 约定：y 向下为正，这里用右手系，pitch 正角表示向上抬
  const eye = computed(() => {
    const radYaw   = yaw.value   * Math.PI / 180
    const radPitch = pitch.value * Math.PI / 180
    const cosP = Math.cos(radPitch)
    return {
      x: target.x + dist.value * cosP * Math.sin(radYaw),
      y: target.y - dist.value * Math.sin(radPitch),  // 上为正，所以负
      z: target.z + dist.value * cosP * Math.cos(radYaw),
    }
  })

  // —— LOD 判断（§6.1）：按 dist ——
  function lodOf () {
    if (focusPlaneId.value) return 'focus'
    if (dist.value <= 620) return 'near'
    if (dist.value <= 1200) return 'mid'
    return 'far'
  }

  // —— 轨道增量（拖拽/滚轮）——
  function orbitTo ({ yaw: ny, pitch: np, dist: nd, tx, ty, tz, animate = false, duration = 480 } = {}) {
    const steps = [
      [yaw,   ny   !== undefined ? clampYaw(ny)   : yaw.value],
      [pitch, np   !== undefined ? clampPitch(np) : pitch.value],
      [dist,  nd   !== undefined ? clampDist(nd)  : dist.value],
      // target 不做 clamp（它是世界坐标，不受轨道约束）
    ]
    if (tx !== undefined) target.x = tx
    if (ty !== undefined) target.y = ty
    if (tz !== undefined) target.z = tz

    if (reducedMotion || !animate) {
      yaw.value   = steps[0][1]
      pitch.value = steps[1][1]
      dist.value  = steps[2][1]
      return
    }
    // 简化：直接赋值。后续可以接入 motionScheduler 做补间。
    // 当前 useFieldCamera 只提供最终目标状态，补间在 FieldStage 层处理。
    yaw.value   = steps[0][1]
    pitch.value = steps[1][1]
    dist.value  = steps[2][1]
  }

  // —— 三机位预设 ——
  function setPreset (name, opts = {}) {
    preset.value = name
    const cx = opts.cx ?? target.x
    if (name === 'overlook') {
      orbitTo({ yaw: 0, pitch: 28, dist: 1500, tx: cx, ty: 300, tz: 0, animate: true })
    } else if (name === 'shelf') {
      orbitTo({ yaw: 0, pitch: 18, dist: 760, tx: cx, ty: 330, tz: 0, animate: true })
    } else if (name === 'trace') {
      // trace 的 target 由调用方传 cx/cy（链条中点）
      const cy = opts.cy ?? 330
      orbitTo({ yaw: 0, pitch: 22, dist: 760, tx: cx, ty: cy, tz: 0, animate: true })
    } else if (name === 'focus') {
      // focus 预设：target 在指定世界坐标
      const cy = opts.cy ?? 330
      orbitTo({ yaw: 0, pitch: 15, dist: 520, tx: cx, ty: cy, tz: 0, animate: true })
    }
  }

  // —— 聚焦一个平面（focus billboard + 相机前推）——
  function focusOn (plane) {
    if (!plane) return
    focusPlaneId.value = plane.id
    focusDomainId.value = plane.domainId || plane.kind === 'knowledge' ? plane.domainId : null
    setPreset('focus', { cx: plane.x, cy: plane.y })
  }

  // —— 三级回退：focus → domain → overlook ——
  function back () {
    if (focusPlaneId.value) {
      // 中间站：聚焦所在域
      if (focusDomainId.value) {
        focusPlaneId.value = null
        focusDomainId.value = null
        // 调用方负责提供域锚点 x；这里只清 focus 状态
        return 'domain'
      }
      // 没域信息 → 直接 overlook
      focusPlaneId.value = null
      focusDomainId.value = null
      setPreset('overlook')
      return 'overlook'
    }
    // 没有 focus → overlook
    setPreset('overlook')
    return 'overlook'
  }

  // —— 手动轨道（拖拽/滚轮）——
  function orbit (deltaYaw, deltaPitch) {
    orbitTo({
      yaw:   yaw.value   + deltaYaw,
      pitch: pitch.value + deltaPitch,
    })
  }

  function zoom (factor) {
    orbitTo({ dist: clampDist(dist.value * factor) })
  }

  return {
    yaw, pitch, dist, target, preset, focusPlaneId, focusDomainId,
    eye,
    lodOf,
    orbitTo,
    setPreset,
    focusOn,
    back,
    orbit,
    zoom,
    // 供 Esc 三级回退外部编排使用
    clearFocus () { focusPlaneId.value = null; focusDomainId.value = null },
  }
}
