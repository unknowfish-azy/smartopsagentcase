const FALLBACK_PALETTE = Object.freeze({
  theme: 'dark',
  background: '#05090d',
  surface: '#071018',
  primary: '#2496ed',
  primaryStrong: '#7ad7f5',
  muted: '#92a6b5',
  border: 'rgba(159, 190, 207, .18)',
  glow: 'rgba(122, 215, 245, .42)',
  star: '#e8f2f7',
  effectPrimary: '#2496ed', effectStrong: '#7ad7f5', effectMuted: '#92a6b5', effectStar: '#a8dfff'
})

function readVariable(styles, name, fallback) {
  const value = styles?.getPropertyValue(name)?.trim()
  return value || fallback
}

export function readCanvasPalette(root = typeof document !== 'undefined' ? document.documentElement : null) {
  if (!root || typeof getComputedStyle !== 'function') return { ...FALLBACK_PALETTE }
  const styles = getComputedStyle(root)
  const isLight = root.dataset?.theme === 'light'
  const fallback = isLight
    ? {
        background: '#f4f7f9',
        theme: 'light',
        surface: '#ffffff',
        primary: '#0e5f92',
        primaryStrong: '#084b73',
        muted: '#4d606c',
        border: 'rgba(16, 53, 70, .22)',
        glow: 'rgba(14, 95, 146, .24)',
        star: '#10212b',
        effectPrimary: '#355e78', effectStrong: '#183c53', effectMuted: '#496679', effectStar: '#243e50'
      }
    : FALLBACK_PALETTE
  return {
    theme: isLight ? 'light' : 'dark',
    background: readVariable(styles, '--smart-bg', fallback.background),
    surface: readVariable(styles, '--smart-surface', fallback.surface),
    primary: readVariable(styles, '--smart-primary', fallback.primary),
    primaryStrong: readVariable(styles, '--smart-primary-strong', fallback.primaryStrong),
    muted: readVariable(styles, '--smart-muted', fallback.muted),
    border: readVariable(styles, '--smart-border', fallback.border),
    glow: readVariable(styles, '--smart-primary-soft', fallback.glow),
    star: readVariable(styles, '--smart-text', fallback.star),
    effectPrimary: readVariable(styles, '--smart-effect-primary', fallback.effectPrimary),
    effectStrong: readVariable(styles, '--smart-effect-strong', fallback.effectStrong),
    effectMuted: readVariable(styles, '--smart-effect-muted', fallback.effectMuted),
    effectStar: readVariable(styles, '--smart-effect-star', fallback.effectStar)
  }
}

export function observeCanvasTheme(callback, root = typeof document !== 'undefined' ? document.documentElement : null) {
  if (!root || typeof MutationObserver === 'undefined') return () => {}
  const observer = new MutationObserver(records => {
    if (records.some(record => record.attributeName === 'data-theme')) callback(readCanvasPalette(root))
  })
  observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}
