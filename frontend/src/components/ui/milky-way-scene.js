import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  DataTexture,
  FloatType,
  Group,
  MathUtils,
  Mesh,
  NearestFilter,
  NormalBlending,
  OrthographicCamera,
  PerspectiveCamera,
  PlaneGeometry,
  Points,
  PointsMaterial,
  RGBAFormat,
  Scene,
  ShaderMaterial,
  WebGLRenderTarget,
  WebGLRenderer
} from 'three'
import { PARTICLE_VERT, PARTICLE_FRAG, SIM_FRAG, SMOKE_VERT, SMOKE_FRAG } from './milky-way-shaders.js'

function randomGenerator(seed) {
  return () => {
    seed += 0x6D2B79F5
    let n = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    n ^= n + Math.imul(n ^ (n >>> 7), 61 | n)
    return ((n ^ (n >>> 14)) >>> 0) / 4294967296
  }
}

// Geometry attributes and simulation textures use the same samples, so color,
// radius and seed remain attached to the correct particle throughout its orbit.
function createParticleData(size, seed, smoke) {
  const random = randomGenerator(seed)
  const count = size * size
  const positions = new Float32Array(count * 4)
  const data = new Float32Array(count * 4)
  const refs = new Float32Array(count * 2)
  const radii = new Float32Array(count)
  const seeds = new Float32Array(count)
  const colors = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    // Spread the former dense ring across broad spiral arms and a diffuse halo.
    let radius = Math.min(5.2, -Math.log(1 - random() * .995) * 1.9)
    const inner = radius < .8
    if (inner) radius = .8 + Math.pow(random(), .6) * 3.4
    const scatter = (random() + random() + random() - 1.5) * (smoke ? 1.5 : .85)
    const arm = i % 2 * Math.PI
    const angle = inner ? random() * Math.PI * 2 : arm + radius * 3.4 + scatter * radius
    positions.set([radius * Math.cos(angle), radius * Math.sin(angle), (random() + random() - 1) * .48, random()], i * 4)
    radii[i] = radius / 5.2
    seeds[i] = random()
    colors[i] = random()
    data.set([radii[i], seeds[i], .3 + radii[i] * .22 + random() * .08, (i % 2) / 2], i * 4)
    refs.set([((i % size) + .5) / size, (Math.floor(i / size) + .5) / size], i * 2)
  }
  const texture = array => {
    const value = new DataTexture(array, size, size, RGBAFormat, FloatType)
    value.minFilter = value.magFilter = NearestFilter
    value.needsUpdate = true
    return value
  }
  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(count * 3), 3))
  geometry.setAttribute('aRef', new BufferAttribute(refs, 2))
  geometry.setAttribute('aRadiusFrac', new BufferAttribute(radii, 1))
  geometry.setAttribute('aSeed', new BufferAttribute(seeds, 1))
  geometry.setAttribute('aColor', new BufferAttribute(colors, 1))
  return { geometry, position: texture(positions), data: texture(data) }
}

function createLayer(renderer, size, smoke, options, quadGeometry, simulationCamera) {
  const resources = createParticleData(size, smoke ? 7777 : 91, smoke)
  const targetOptions = { type: FloatType, format: RGBAFormat, minFilter: NearestFilter, magFilter: NearestFilter, depthBuffer: false, stencilBuffer: false }
  let read = new WebGLRenderTarget(size, size, targetOptions)
  let write = new WebGLRenderTarget(size, size, targetOptions)
  let initial = true
  const simulation = new ShaderMaterial({
    vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position,1.0); }',
    fragmentShader: SIM_FRAG,
    uniforms: { uPosition: { value: resources.position }, uData: { value: resources.data }, uTime: { value: 0 }, uDelta: { value: 0 } },
    depthTest: false, depthWrite: false, toneMapped: false,
  })
  const simulationScene = new Scene()
  simulationScene.add(new Mesh(quadGeometry, simulation))
  const material = new ShaderMaterial({
    vertexShader: smoke ? SMOKE_VERT : PARTICLE_VERT,
    fragmentShader: smoke ? SMOKE_FRAG : PARTICLE_FRAG,
    uniforms: {
      uPosition: { value: resources.position }, uTime: { value: 0 },
      uPixelRatio: { value: renderer.getPixelRatio() }, uParticleSize: { value: options.particleSize },
      uCoreColor: { value: new Color(options.coreColor) },
      uAccentColor: { value: new Color(options.accentColor) },
      uOuterColor: { value: new Color(options.outerColor) },
    },
    transparent: true, depthWrite: false, blending: options.theme === 'light' ? NormalBlending : AdditiveBlending,
    premultipliedAlpha: options.theme === 'light',
  })
  const points = new Points(resources.geometry, material)
  points.frustumCulled = false // Positions live in a texture, not the CPU bounding sphere.
  return {
    points,
    setTheme(theme) {
      material.uniforms.uCoreColor.value.set(theme.coreColor)
      material.uniforms.uAccentColor.value.set(theme.accentColor)
      material.uniforms.uOuterColor.value.set(theme.outerColor)
      material.blending = theme.theme === 'light' ? NormalBlending : AdditiveBlending
      material.premultipliedAlpha = theme.theme === 'light'
      material.needsUpdate = true
    },
    update(time, delta) {
      simulation.uniforms.uPosition.value = initial ? resources.position : read.texture
      simulation.uniforms.uTime.value = time
      simulation.uniforms.uDelta.value = delta
      const previousTarget = renderer.getRenderTarget()
      renderer.setRenderTarget(write)
      renderer.render(simulationScene, simulationCamera)
      renderer.setRenderTarget(previousTarget)
      ;[read, write] = [write, read]
      initial = false
      material.uniforms.uPosition.value = read.texture
      material.uniforms.uTime.value = time
    },
    resize() { material.uniforms.uPixelRatio.value = renderer.getPixelRatio() },
    dispose() {
      read.dispose(); write.dispose(); simulation.dispose(); material.dispose()
      resources.geometry.dispose(); resources.position.dispose(); resources.data.dispose()
    },
  }
}

export function createMilkyWayScene(canvas, options) {
  const renderer = new WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: 'low-power' })
  if (!renderer.extensions.has('EXT_color_buffer_float')) {
    renderer.dispose()
    renderer.forceContextLoss()
    throw new Error('Float render targets unavailable')
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  renderer.setClearColor(options.backgroundColor, 1)
  const scene = new Scene()
  const camera = new PerspectiveCamera(45, 1, .1, 100)
  camera.position.set(0, 0, 11)
  const galaxy = new Group()
  galaxy.rotation.set(-.85, -.12, -.32)
  galaxy.scale.setScalar(1.25)
  scene.add(galaxy)
  const quadGeometry = new PlaneGeometry(2, 2)
  const simulationCamera = new OrthographicCamera(-1, 1, 1, -1, 0, 1)
  // Bound background GPU cost on mobile. All motion is simulated in textures.
  const small = window.innerWidth < 768
  const layers = [createLayer(renderer, small ? 160 : 300, false, options, quadGeometry, simulationCamera), createLayer(renderer, small ? 22 : 36, true, options, quadGeometry, simulationCamera)]
  layers.forEach(layer => galaxy.add(layer.points))
  const random = randomGenerator(12345)
  const starPositions = new Float32Array((small ? 900 : 2400) * 3)
  for (let i = 0; i < starPositions.length; i += 3) {
    starPositions[i] = (random() - .5) * 55
    starPositions[i + 1] = (random() - .5) * 36
    starPositions[i + 2] = -8 - random() * 30
  }
  const starGeometry = new BufferGeometry()
  starGeometry.setAttribute('position', new BufferAttribute(starPositions, 3))
  const starMaterial = new PointsMaterial({ color: options.coreColor, size: .025, transparent: true, opacity: .65, depthWrite: false })
  const stars = new Points(starGeometry, starMaterial)
  scene.add(stars)
  let elapsed = 0
  let tiltX = 0, tiltY = 0
  return {
    setTheme(theme) {
      renderer.setClearColor(theme.backgroundColor, 1)
      starMaterial.color.set(theme.coreColor)
      layers.forEach(layer => layer.setTheme(theme))
    },
    resize(width, height) {
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.position.z = width < 768 ? 15 : 10
      camera.updateProjectionMatrix()
      galaxy.position.set(width < 768 ? -.2 : .4, -.35, 0)
      // Optional homepage framing; leave the login composition unchanged.
      if (options.viewportCoverage > 0) {
        const worldWidth = 2 * camera.position.z * Math.tan(MathUtils.degToRad(camera.fov / 2)) * camera.aspect
        galaxy.scale.setScalar(worldWidth * Math.min(1, options.viewportCoverage) / 10.4)
        galaxy.position.x = (Math.max(0, Math.min(1, options.centerX)) - .5) * worldWidth
      }
      layers.forEach(layer => layer.resize())
    },
    render(delta, pointer) {
      const dt = Math.min(delta, .05)
      const speed = options.rotationSpeed
      elapsed += dt * speed
      if (dt > 0) layers.forEach(layer => layer.update(elapsed, dt * speed))
      const easing = 1 - Math.exp(-2 * dt)
      tiltX += (pointer.x - tiltX) * easing
      tiltY += (pointer.y - tiltY) * easing
      galaxy.rotation.x = -.85 + (options.mouseInfluence ? tiltY * .08 : 0)
      galaxy.rotation.y = -.12 + (options.mouseInfluence ? tiltX * .1 : 0)
      galaxy.rotation.z = -.32 + elapsed * .06
      stars.rotation.z = elapsed * .008
      renderer.render(scene, camera)
    },
    dispose() {
      layers.forEach(layer => layer.dispose())
      quadGeometry.dispose(); starGeometry.dispose(); starMaterial.dispose()
      renderer.dispose(); renderer.forceContextLoss()
    },
  }
}
