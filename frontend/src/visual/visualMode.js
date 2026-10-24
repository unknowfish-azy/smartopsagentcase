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
export const isLightweightVisualMode = computed(() => visualMode.value !== 'balanced')

export function setVisualMode(value) {
  visualMode.value = normalizeVisualMode(value)
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, visualMode.value)
  } catch {
  }
}
