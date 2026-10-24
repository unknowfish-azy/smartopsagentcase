const clamp = (value, minimum = 0, maximum = 1) => Math.min(maximum, Math.max(minimum, value))
const smooth = (value) => {
  const clamped = clamp(value)
  return clamped * clamped * (3 - 2 * clamped)
}

const whaleStates = {
  idle: { duration: 9.3, swimDuration: 32, strength: 0.78, flow: 0.42, turbulence: 0 },
  thinking: { duration: 7.4, swimDuration: 27, strength: 0.92, flow: 0.7, turbulence: 0.04 },
  observing: { duration: 8.1, swimDuration: 30, strength: 0.86, flow: 0.58, turbulence: 0.02 },
  executing: { duration: 6.4, swimDuration: 23, strength: 1, flow: 0.94, turbulence: 0.07 },
  warning: { duration: 7.7, swimDuration: 28, strength: 0.9, flow: 0.7, turbulence: 0.18 },
  error: { duration: 8.4, swimDuration: 31, strength: 0.82, flow: 0.52, turbulence: 0.26 },
  recovering: { duration: 8.8, swimDuration: 32, strength: 0.82, flow: 0.5, turbulence: 0.06 }
}

const jellyfishStates = {
  idle: { driftDuration: 5.8, breathDuration: 6.7, flow: 0.42, scanStrength: 0.08, tentacle: 0.68 },
  thinking: { driftDuration: 5.4, breathDuration: 5.6, flow: 0.78, scanStrength: 0.18, tentacle: 0.76 },
  observing: { driftDuration: 5.1, breathDuration: 6.2, flow: 0.62, scanStrength: 0.52, tentacle: 0.86 },
  working: { driftDuration: 4.9, breathDuration: 5.2, flow: 0.94, scanStrength: 0.28, tentacle: 0.94 },
  warning: { driftDuration: 5.5, breathDuration: 5.6, flow: 0.76, scanStrength: 0.34, tentacle: 1.04 },
  error: { driftDuration: 6.1, breathDuration: 6.4, flow: 0.48, scanStrength: 0.24, tentacle: 0.94 },
  recovering: { driftDuration: 5.9, breathDuration: 6.8, flow: 0.54, scanStrength: 0.18, tentacle: 0.72 }
}

export function getWhaleMotionProfile(state = 'idle') {
  const profile = whaleStates[state] || whaleStates.idle
  return { ...profile, rotationLimit: 0.02, tailDelay: 0.68, ambientDuration: 15.1 }
}

export function getWhaleSwimMotion(timeMs = 0, state = 'idle') {
  const phase = (timeMs / 1000 / getWhaleMotionProfile(state).swimDuration) * Math.PI * 2
  return {
    x: Math.sin(phase) * 0.48,
    y: Math.sin(phase * 2 - 0.8) * 0.09,
    rotation: Math.cos(phase) * 0.055
  }
}

export function getWhaleBreath(timeMs = 0, state = 'idle') {
  const profile = getWhaleMotionProfile(state)
  const progress = ((timeMs / 1000) % profile.duration) / profile.duration
  if (progress < 0.28) {
    return { phase: 'inhale', progress, intensity: smooth(progress / 0.28) * profile.strength, inhale: smooth(progress / 0.28), exhale: 0 }
  }
  if (progress < 0.38) {
    return { phase: 'hold', progress, intensity: profile.strength, inhale: 1, exhale: 0 }
  }
  if (progress < 0.76) {
    const release = smooth((progress - 0.38) / 0.38)
    return { phase: 'exhale', progress, intensity: (1 - release * 0.72) * profile.strength, inhale: 1 - release, exhale: release }
  }
  return { phase: 'rest', progress, intensity: (1 - smooth((progress - 0.76) / 0.24)) * 0.28 * profile.strength, inhale: 0, exhale: 0 }
}

export function getJellyfishProfile(state = 'idle') {
  return jellyfishStates[state] || jellyfishStates.idle
}

// One quiet field gives the organisms a shared "water" without synchronizing their motion.
export function getGlobalFluidField(x, y, timeMs = 0, seed = 0) {
  const time = timeMs / 1000
  return {
    x: Math.sin(time * 0.37 + y * 0.42 + seed * 1.7) * 0.52 + Math.sin(time * 0.13 + x * 0.31) * 0.22,
    y: Math.cos(time * 0.29 + x * 0.38 + seed * 2.1) * 0.44 + Math.sin(time * 0.11 + y * 0.57) * 0.16
  }
}

export function getEcosystemTide(timeMs = 0, state = 'idle') {
  const breath = getWhaleBreath(timeMs, state === 'working' ? 'executing' : state)
  return { intake: breath.inhale, release: breath.exhale, phase: breath.phase }
}

export { clamp, smooth }
