<template>
  <div class="atc-shader" aria-hidden="true">
    <canvas ref="canvas" class="atc-shader__canvas"></canvas>
    <div class="atc-shader__fallback"></div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { observeCanvasTheme, readCanvasPalette } from './canvasTheme.js'

const canvas = ref(null)
let animationFrame = 0
let resizeObserver
let mediaQuery
let scrollTimer
let scrolling = false
let scrollHandler
let stopTheme = () => {}
let releaseGraphics = () => {}

const vertexSource = `#version 300 es
in vec2 a_pos;
void main(){ gl_Position = vec4(a_pos, 0.0, 1.0); }`

const fragmentSource = `#version 300 es
precision highp float;
out vec4 fragColor;
uniform vec2 u_res;
uniform float u_time;
uniform float u_lightTheme;
uniform vec3 u_ink;
float tanh1(float x){ float e = exp(2.0 * x); return (e - 1.0) / (e + 1.0); }
vec4 tanh4(vec4 v){ return vec4(tanh1(v.x), tanh1(v.y), tanh1(v.z), tanh1(v.w)); }
void main(){
  vec3 FC = vec3(gl_FragCoord.xy, 0.0);
  vec3 r = vec3(u_res, max(u_res.x, u_res.y));
  float t = u_time;
  vec4 o = vec4(0.0);
  vec3 p = vec3(0.0);
  vec3 v = vec3(1.0, 2.0, 6.0);
  float i = 0.0, z = 1.0, d = 1.0, f = 1.0;
  for (; i++ < 34.0; o.rgb += (cos((p.x + z + v) * 0.1) + 1.0) / d / f / z) {
    p = z * normalize(FC * 2.0 - r.xyy);
    vec4 m = cos((p + sin(p)).y * 0.4 + vec4(0.0, 33.0, 11.0, 0.0));
    p.xz = mat2(m) * p.xz;
    p.x += t / 0.2;
    z += (d = length(cos(p / v) * v + v.zxx / 7.0) / (f = 2.0 + d / exp(p.y * 0.2)));
  }
  o = tanh4(0.2 * o);
  float strength = clamp(max(o.r, max(o.g, o.b)), 0.0, 1.0);
  fragColor = u_lightTheme > 0.5 ? vec4(u_ink, strength * 0.65) : vec4(o.rgb, 1.0);
}`

function compile(gl, type, source) {
  const shader = gl.createShader(type)
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'Shader compile error')
  return shader
}

function createProgram(gl) {
  const program = gl.createProgram()
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertexSource))
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragmentSource))
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'Shader link error')
  return program
}

onMounted(() => {
  const element = canvas.value
  const gl = element?.getContext('webgl2', { premultipliedAlpha: false, antialias: false })
  if (!element || !gl) return

  let program
  try { program = createProgram(gl) } catch { return }
  gl.useProgram(program)
  const buffer = gl.createBuffer()
  releaseGraphics = () => {
    for (const shader of gl.getAttachedShaders(program) || []) gl.deleteShader(shader)
    gl.deleteBuffer(buffer)
    gl.deleteProgram(program)
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW)
  const position = gl.getAttribLocation(program, 'a_pos')
  gl.enableVertexAttribArray(position)
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0)
  const resolution = gl.getUniformLocation(program, 'u_res')
  const time = gl.getUniformLocation(program, 'u_time')
  const lightTheme = gl.getUniformLocation(program, 'u_lightTheme')
  const ink = gl.getUniformLocation(program, 'u_ink')
  const colorCanvas = document.createElement('canvas')
  colorCanvas.width = colorCanvas.height = 1
  const colorContext = colorCanvas.getContext('2d', { willReadFrequently: true })
  let lastElapsed = 0
  const applyTheme = palette => {
    colorContext.clearRect(0, 0, 1, 1)
    colorContext.fillStyle = palette.effectStrong
    colorContext.fillRect(0, 0, 1, 1)
    const channels = colorContext.getImageData(0, 0, 1, 1).data
    gl.uniform1f(lightTheme, palette.theme === 'light' ? 1 : 0)
    gl.uniform3f(ink, channels[0] / 255, channels[1] / 255, channels[2] / 255)
    element.dataset.effectTheme = palette.theme
  }
  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 1.35)
    const width = Math.max(1, Math.floor(element.clientWidth * ratio))
    const height = Math.max(1, Math.floor(element.clientHeight * ratio))
    if (element.width !== width || element.height !== height) { element.width = width; element.height = height }
    gl.viewport(0, 0, width, height)
    gl.uniform2f(resolution, width, height)
  }
  const draw = (elapsed) => {
    lastElapsed = elapsed
    gl.uniform1f(time, elapsed)
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.drawArrays(gl.TRIANGLES, 0, 6)
  }
  const start = performance.now()
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
  const frame = (now) => {
    animationFrame = 0
    if (scrolling || reduced.matches) return
    draw((now - start) / 1000)
    animationFrame = requestAnimationFrame(frame)
  }
  const resume = () => {
    scrolling = false
    if (!reduced.matches && !animationFrame) animationFrame = requestAnimationFrame(frame)
  }
  const onScroll = () => {
    scrolling = true
    if (animationFrame) { cancelAnimationFrame(animationFrame); animationFrame = 0 }
    clearTimeout(scrollTimer)
    scrollTimer = window.setTimeout(resume, 180)
  }
  applyTheme(readCanvasPalette())
  stopTheme = observeCanvasTheme(palette => { applyTheme(palette); draw(lastElapsed) })
  resize()
  draw(0)
  if (!reduced.matches) animationFrame = requestAnimationFrame(frame)
  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(element.parentElement)
  scrollHandler = onScroll
  window.addEventListener('scroll', scrollHandler, { passive: true })
  mediaQuery = reduced
  element.dataset.ready = 'true'
})

onBeforeUnmount(() => {
  stopTheme()
  releaseGraphics()
  cancelAnimationFrame(animationFrame)
  clearTimeout(scrollTimer)
  resizeObserver?.disconnect()
  if (scrollHandler) window.removeEventListener('scroll', scrollHandler)
  mediaQuery = undefined
})
</script>

<style scoped>
.atc-shader { position: absolute; inset: 0; z-index: 0; contain: paint; overflow: hidden; pointer-events: none; opacity: .58; mix-blend-mode: screen; }
.atc-shader__canvas, .atc-shader__fallback { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.atc-shader__canvas { opacity: .9; }
.atc-shader__fallback { z-index: -1; background: radial-gradient(circle at 70% 18%, rgba(51, 204, 188, .22), transparent 34%), radial-gradient(circle at 24% 76%, rgba(40, 118, 206, .2), transparent 38%), linear-gradient(140deg, #07131d, #102d3b 48%, #08131c); }
:global([data-theme='light'] .atc-shader) { opacity: .2; mix-blend-mode: normal; }
:global([data-theme='light'] .atc-shader__fallback) { background: radial-gradient(circle at 70% 18%, rgba(40, 162, 151, .18), transparent 34%), radial-gradient(circle at 24% 76%, rgba(42, 112, 190, .14), transparent 38%), linear-gradient(140deg, #edf6f7, #dcecf0 48%, #f3f8f8); }
</style>
