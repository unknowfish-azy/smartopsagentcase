const REGION_BODY = 0
const REGION_TAIL = 1
const REGION_CONTAINERS = 2

function randomInDisk() {
  const angle = Math.random() * Math.PI * 2
  const radius = Math.sqrt(Math.random())
  return [Math.cos(angle) * radius, Math.sin(angle) * radius]
}

export function createWhalePointCloud(count) {
  const positions = new Float32Array(count * 3)
  const basePositions = new Float32Array(count * 3)
  const regions = new Float32Array(count)
  const phases = new Float32Array(count)
  const flows = new Float32Array(count)

  for (let index = 0; index < count; index += 1) {
    const offset = index * 3
    // Interleave structural regions so adaptive draw ranges preserve the silhouette.
    const regionBucket = (index * 37) % 100
    if (regionBucket < 80) {
      const [diskX, diskY] = randomInDisk()
      const x = diskX * 1.38 + .25
      const y = diskY * .76 * (.8 + .2 * diskX) - .02
      // A small clear eye and curved smile cut into the rounded particle body.
      const eye = (x - 1.03) ** 2 + (y - .19) ** 2 < .009
      const smile = x > .94 && y < -.12 && Math.abs(y - (-.23 + .18 * (x - 1.05) ** 2)) < .026
      positions[offset] = eye || smile ? .3 : x
      positions[offset + 1] = eye || smile ? .3 + Math.random() * .16 : y
      positions[offset + 2] = (Math.random() - .5) * .12
      regions[index] = REGION_BODY
    } else if (regionBucket < 94) {
      const wing = index % 2 === 0 ? 1 : -1
      const progress = Math.random()
      positions[offset] = -1.0 - progress * .95
      positions[offset + 1] = .08 + progress * .65 + wing * Math.sin(progress * Math.PI / 2) * .32 * Math.random()
      positions[offset + 2] = (Math.random() - .5) * .12
      regions[index] = REGION_TAIL
    } else {
      const fin = Math.random()
      positions[offset] = .2 - fin * .65 + Math.random() * .22 * (1 - fin)
      positions[offset + 1] = -.4 - Math.sin(fin * Math.PI / 2) * .55
      positions[offset + 2] = .1
      regions[index] = REGION_CONTAINERS
    }

    basePositions[offset] = positions[offset]
    basePositions[offset + 1] = positions[offset + 1]
    basePositions[offset + 2] = positions[offset + 2]
    phases[index] = Math.random() * Math.PI * 2
    flows[index] = 0.35 + Math.random() * 0.65
  }

  return { positions, basePositions, regions, phases, flows }
}

export const whaleRegions = { body: REGION_BODY, tail: REGION_TAIL, containers: REGION_CONTAINERS }
