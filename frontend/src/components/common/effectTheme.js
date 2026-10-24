export function resolveEffectTheme(palette) {
  const light = palette.theme === 'light'
  return {
    theme: light ? 'light' : 'dark', blend: light ? 'normal' : 'additive',
    primary: palette.effectPrimary, strong: palette.effectStrong,
    muted: palette.effectMuted, star: palette.effectStar, background: palette.background,
    coreColor: light ? palette.effectStrong : '#f5f5ff',
    accentColor: light ? palette.effectPrimary : '#ffe6ad',
    outerColor: light ? palette.effectMuted : '#e05c12'
  }
}
