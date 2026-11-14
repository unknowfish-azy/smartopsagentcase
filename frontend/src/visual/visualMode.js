import { computed, ref } from 'vue'

export const VISUAL_MODES = Object.freeze(['balanced', 'lightweight', 'reduced-motion'])
const STORAGE_KEY = 'smartops_visual_mode'

export function normalizeVisualMode(value) {
  return VISUAL_MODES.includes(value) ? value : 'balanced'
}

function readStoredMode() {
  try {
    return normalizeVisualMode(globalThis.localStorage?.getItem(STORAGE_KEY))
  } catch {
    return 'balanced'
  }
}

export const visualMode = ref(readStoredMode())
/** 用户是否显式选择过档位（响应式，供工具层决定是否加载装饰性 WebGL）。 */
export const visualModeExplicit = ref((() => {
  try { return VISUAL_MODES.includes(globalThis.localStorage?.getItem(STORAGE_KEY)) } catch { return false }
})())
export const isLightweightVisualMode = computed(() => visualMode.value === 'lightweight')
export const isReducedMotionMode = computed(() => visualMode.value === 'reduced-motion')

export function setVisualMode(value) {
  visualMode.value = normalizeVisualMode(value)
  visualModeExplicit.value = true
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, visualMode.value)
  } catch {
  }
}

/**
 * 自适应视觉预算（P0）：只返回建议，不覆盖用户显式选择、不改写 localStorage。
 * 运行时检测到持续掉帧时，调用方可据此把装饰层降到静态一帧。
 */
export function adaptiveVisualBudget() {
  try {
    const nav = globalThis.navigator || {}
    const motion = typeof globalThis.matchMedia === 'function' && globalThis.matchMedia('(prefers-reduced-motion: reduce)').matches
    const cores = typeof nav.hardwareConcurrency === 'number' ? nav.hardwareConcurrency : 8
    const memory = typeof nav.deviceMemory === 'number' ? nav.deviceMemory : 8
    const narrow = (globalThis.innerWidth || 1440) < 1024
    if (motion) return { mode: 'reduced-motion', reason: '系统偏好减少动态' }
    if (cores <= 4 || memory <= 4) return { mode: 'lightweight', reason: '设备算力或内存较低' }
    if (narrow) return { mode: 'lightweight', reason: '窄视口，优先保证交互流畅' }
    return { mode: 'balanced', reason: '设备与视口资源充足' }
  } catch {
    return { mode: 'balanced', reason: '能力探测不可用，使用默认档位' }
  }
}

/** 用户是否已经显式选择过视觉档位（用于区分默认值与主动选择）。 */
export function hasExplicitVisualMode() {
  try {
    return VISUAL_MODES.includes(globalThis.localStorage?.getItem(STORAGE_KEY))
  } catch {
    return false
  }
}
