export function resolveWhaleQuality({ width, dpr = 1, reducedMotion = false }) {
  if (reducedMotion) {
    return { tier: 'low', particleCount: 4200, animate: false }
  }

  if (width >= 1440 && dpr <= 1.5) {
    return { tier: 'high', particleCount: 18000, animate: true }
  }

  if (width >= 768) {
    return { tier: 'medium', particleCount: 10000, animate: true }
  }

  return { tier: 'low', particleCount: 4200, animate: true }
}
