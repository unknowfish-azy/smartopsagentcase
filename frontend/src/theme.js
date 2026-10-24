import { computed, ref } from 'vue'

export const THEME_MODES = Object.freeze(['light', 'dark', 'system'])
const STORAGE_KEY = 'smartops_theme'

export function normalizeThemeMode(value) {
  return THEME_MODES.includes(value) ? value : 'system'
}

export function resolveTheme(mode, systemPrefersDark) {
  return normalizeThemeMode(mode) === 'system' ? (systemPrefersDark ? 'dark' : 'light') : normalizeThemeMode(mode)
}

function readStoredMode() {
  try { return normalizeThemeMode(globalThis.localStorage?.getItem(STORAGE_KEY)) } catch { return 'system' }
}

export const themeMode = ref(readStoredMode())
export const resolvedTheme = ref('dark')
export const isDarkTheme = computed(() => resolvedTheme.value === 'dark')

let mediaQuery
let initialized = false

function syncTheme() {
  const systemPrefersDark = mediaQuery?.matches ?? true
  resolvedTheme.value = resolveTheme(themeMode.value, systemPrefersDark)
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = resolvedTheme.value
    document.documentElement.style.colorScheme = resolvedTheme.value
  }
}

function onSystemThemeChange() {
  if (themeMode.value === 'system') syncTheme()
}

export function initializeTheme() {
  if (initialized || typeof window === 'undefined') return
  initialized = true
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener?.('change', onSystemThemeChange)
  syncTheme()
}

export function setThemeMode(value) {
  themeMode.value = normalizeThemeMode(value)
  try { globalThis.localStorage?.setItem(STORAGE_KEY, themeMode.value) } catch { /* Storage is optional. */ }
  syncTheme()
}

export function disposeTheme() {
  mediaQuery?.removeEventListener?.('change', onSystemThemeChange)
  mediaQuery = undefined
  initialized = false
}
