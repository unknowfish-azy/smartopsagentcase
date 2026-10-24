import { getGlobalFluidField } from './organismMotion.js'

const clamp = (value, minimum = 0, maximum = 1) => Math.min(maximum, Math.max(minimum, value))

export function resolveStellarQuality({ width, dpr = 1, reducedMotion = false }) {
  if (reducedMotion) return { tier: 'low', totalStars: 260, chainCount: 14, flowCount: 16, animate: false }
  if (width >= 1440 && dpr <= 1.5) return { tier: 'high', totalStars: 900, chainCount: 40, flowCount: 52, animate: true }
  if (width >= 768) return { tier: 'medium', totalStars: 520, chainCount: 26, flowCount: 32, animate: true }
  return { tier: 'low', totalStars: 260, chainCount: 14, flowCount: 16, animate: true }
}

function seeded(index, salt) {
  const value = Math.sin(index * 127.1 + salt * 311.7) * 43758.5453123
  return value - Math.floor(value)
}

function createLayer(count, layerIndex) {
  const positions = new Float32Array(count * 3)
  const basePositions = new Float32Array(count * 3)
  const phases = new Float32Array(count)
  const drifts = new Float32Array(count)
  for (let index = 0; index < count; index += 1) {
    const offset = index * 3
    const cluster = index % 4
    const spreadX = seeded(index, layerIndex + 1) * 7.8 - 3.9
    const spreadY = seeded(index, layerIndex + 7) * 4.8 - 2.4
    const clusterX = cluster === 0 ? -1.35 : cluster === 1 ? 1.45 : cluster === 2 ? 0.4 : -0.35
    const clusterY = cluster === 0 ? 0.85 : cluster === 1 ? -0.62 : cluster === 2 ? 1.18 : -1.2
    const density = seeded(index, layerIndex + 12) > 0.38 ? 0.68 : 1
    positions[offset] = (spreadX * density + clusterX * (1 - density))
    positions[offset + 1] = (spreadY * density + clusterY * (1 - density))
    positions[offset + 2] = seeded(index, layerIndex + 22) * 0.55 - 0.275
    basePositions[offset] = positions[offset]
    basePositions[offset + 1] = positions[offset + 1]
    basePositions[offset + 2] = positions[offset + 2]
    phases[index] = seeded(index, layerIndex + 34) * Math.PI * 2
    drifts[index] = 0.28 + seeded(index, layerIndex + 49) * 0.72
  }
  return { positions, basePositions, phases, drifts }
}

export function createStellarField(quality) {
  const backgroundCount = Math.floor(quality.totalStars * 0.64)
  const midCount = Math.floor(quality.totalStars * 0.25)
  const activeCount = quality.totalStars - backgroundCount - midCount
  const layers = [createLayer(backgroundCount, 0), createLayer(midCount, 1), createLayer(activeCount, 2)]
  const chainPairs = new Uint32Array(quality.chainCount * 2)
  for (let index = 0; index < quality.chainCount; index += 1) {
    const source = (index * 7) % midCount
    const sourceOffset = source * 3
    const nearest = []
    for (let candidate = 0; candidate < midCount; candidate += 1) {
      if (candidate === source) continue
      const candidateOffset = candidate * 3
      const dx = layers[1].positions[sourceOffset] - layers[1].positions[candidateOffset]
      const dy = layers[1].positions[sourceOffset + 1] - layers[1].positions[candidateOffset + 1]
      nearest.push({ candidate, distance: dx * dx + dy * dy })
    }
    nearest.sort((a, b) => a.distance - b.distance)
    chainPairs[index * 2] = source
    chainPairs[index * 2 + 1] = nearest[Math.min(index % 3, nearest.length - 1)].candidate
  }
  const flowProgress = new Float32Array(quality.flowCount)
  const flowPairs = new Uint32Array(quality.flowCount)
  for (let index = 0; index < quality.flowCount; index += 1) {
    flowProgress[index] = seeded(index, 75)
    flowPairs[index] = index % quality.chainCount
  }
  return { quality, layers, chainPairs, flowProgress, flowPairs }
}

export function getStellarTide(timeMs = 0) {
  const slow = (Math.sin(timeMs * 0.00021 + 0.8) + 1) * 0.5
  return slow * slow * (3 - 2 * slow)
}

export function getStellarFlowField(x, y, timeMs = 0, seed = 0) {
  return getGlobalFluidField(x, y, timeMs, seed)
}

export function updateStellarField(field, timeMs, effects = {}) {
  const tide = getStellarTide(timeMs)
  const whale = effects.whale || { x: 0, y: 0, inhale: 0, exhale: 0 }
  const jellyfish = effects.jellyfish || { x: 9, y: 9, strength: 0 }
  const pointer = effects.pointer || { x: 99, y: 99, active: false }
  field.layers.forEach((layer, layerIndex) => {
    const scale = layerIndex === 0 ? 0.18 : layerIndex === 1 ? 0.5 : 0.85
    for (let index = 0; index < layer.phases.length; index += 1) {
      const offset = index * 3
      const baseX = layer.basePositions[offset]
      const baseY = layer.basePositions[offset + 1]
      const fluid = getGlobalFluidField(baseX, baseY, timeMs, layer.phases[index])
      let x = baseX + fluid.x * 0.05 * scale * layer.drifts[index] + Math.sin(timeMs * 0.00013 + layer.phases[index]) * 0.018 * scale
      let y = baseY + fluid.y * 0.05 * scale * layer.drifts[index] + Math.cos(timeMs * 0.00011 + layer.phases[index]) * 0.016 * scale
      const whaleDx = whale.x - x
      const whaleDy = whale.y - y
      const whaleDistance = Math.sqrt(whaleDx * whaleDx + whaleDy * whaleDy) + 0.001
      const whaleRange = clamp(1 - whaleDistance / 3.2)
      // The whale bends local currents rather than pulling stars into a point.
      x += whaleDx / whaleDistance * whaleRange * whale.inhale * 0.04 * scale
      y += whaleDy / whaleDistance * whaleRange * whale.inhale * 0.04 * scale
      const ripple = Math.sin(whaleDistance * 4.8 - timeMs * 0.0014) * whale.exhale * whaleRange * 0.035 * scale
      x -= whaleDx / whaleDistance * ripple
      y -= whaleDy / whaleDistance * ripple
      const jellyDx = x - jellyfish.x
      const jellyDy = y - jellyfish.y
      const jellyDistance = Math.sqrt(jellyDx * jellyDx + jellyDy * jellyDy) + 0.001
      const jellyRange = clamp(1 - jellyDistance / 1.55)
      x += jellyDx / jellyDistance * jellyRange * jellyfish.strength * 0.026 * scale
      y += jellyDy / jellyDistance * jellyRange * jellyfish.strength * 0.026 * scale
      if (pointer.active) {
        const dx = x - pointer.x
        const dy = y - pointer.y
        const distance = dx * dx + dy * dy
        if (distance < 0.65) {
          const disturbance = (1 - distance / 0.65) * 0.032 * scale
          x += dx * disturbance
          y += dy * disturbance
        }
      }
      const densityWave = (tide - 0.5) * 0.012 * scale
      layer.positions[offset] = x + baseX * densityWave
      layer.positions[offset + 1] = y + baseY * densityWave
      layer.positions[offset + 2] = layer.basePositions[offset + 2]
    }
  })
  return tide
}
