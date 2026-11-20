/**
 * L2 2D 动态替身渲染器（无 WebGL）。
 *
 * 接口与 useVrmModel / useProgrammaticAvatar 对齐，AgentPersona 可以直接互换：
 *   setState(profile, { state }) / speakText / speakTimeline / seekSpeech /
 *   stopSpeaking / playGesture / stopGesture / stats / ready / dispose
 *
 * 性能取舍：空闲态完全交给 CSS（呼吸、眨眼、光晕），只在播报时跑 rAF 写口型变量，
 * 说完立刻停帧。移动端因此不需要 WebGL、不需要模型下载，也不会持续占用主线程。
 */
import { createLipSync } from './useLipSync.js'
import { build2DVisual, gestureClass, mouthShape, GESTURE_MS } from './persona2d.js'
import { PERSONA_STATE_LABELS } from './personaStates.js'
import './persona2d.css'

const SVG = `
<svg class="p2d__svg" viewBox="0 0 300 400" aria-hidden="true" focusable="false">
  <ellipse class="p2d__aura" cx="150" cy="210" rx="118" ry="152" />
  <g class="p2d__figure">
    <ellipse class="p2d__shadow" cx="150" cy="392" rx="76" ry="8" />
    <g class="p2d__body">
      <g class="p2d__breath">
        <path class="p2d__torso" d="M78 400 C78 334 112 300 150 300 C188 300 222 334 222 400 Z" fill="#1f6f77" />
        <path d="M128 300 L150 328 L172 300" fill="none" stroke="#d8f3ef" stroke-width="3" stroke-linejoin="round" />

        <g class="p2d__arm p2d__arm--left">
          <path d="M88 326 C74 342 68 368 72 392 L96 396 C96 372 100 350 112 336 Z" fill="#1a5f66" />
        </g>
        <g class="p2d__arm p2d__arm--right">
          <path d="M212 326 C226 342 232 368 228 392 L204 396 C204 372 200 350 188 336 Z" fill="#1a5f66" />
        </g>

        <rect x="136" y="208" width="28" height="94" rx="13" fill="#f3c7ae" />

        <g class="p2d__head">
          <g class="p2d__head-motion">
            <ellipse cx="150" cy="150" rx="84" ry="90" fill="#2b3240" />
            <path d="M70 150 C64 210 70 260 84 292 L110 282 C96 240 94 190 100 150 Z" fill="#2b3240" />
            <path d="M230 150 C236 210 230 260 216 292 L190 282 C204 240 206 190 200 150 Z" fill="#2b3240" />

            <ellipse cx="88" cy="158" rx="9" ry="14" fill="#ffe0cd" />
            <ellipse cx="212" cy="158" rx="9" ry="14" fill="#ffe0cd" />
            <ellipse cx="150" cy="150" rx="60" ry="68" fill="#ffe0cd" />

            <path d="M88 140 C88 84 114 62 150 62 C186 62 212 84 212 140 C198 114 176 102 150 102 C124 102 102 114 88 140 Z" fill="#2b3240" />
            <path d="M96 120 C90 150 92 186 100 210 L112 200 C104 174 102 146 108 122 Z" fill="#2b3240" />
            <path d="M204 120 C210 150 208 186 200 210 L188 200 C196 174 198 146 192 122 Z" fill="#2b3240" />

            <circle cx="206" cy="104" r="7" fill="var(--accent)" />
            <circle cx="204" cy="102" r="2.2" fill="#ffffff" opacity=".55" />

            <g class="p2d__eyes">
              <g class="p2d__eye-open">
                <g class="p2d__blink">
                  <ellipse cx="126" cy="160" rx="9" ry="11" fill="#ffffff" />
                  <g class="p2d__pupils">
                    <circle cx="126" cy="160" r="5" fill="#2b3240" />
                    <circle cx="126" cy="161" r="2.3" fill="#0e1a24" />
                    <circle cx="128.4" cy="157.4" r="1.5" fill="#ffffff" opacity=".9" />
                  </g>
                </g>
              </g>
              <g class="p2d__eye-open">
                <g class="p2d__blink">
                  <ellipse cx="174" cy="160" rx="9" ry="11" fill="#ffffff" />
                  <g class="p2d__pupils">
                    <circle cx="174" cy="160" r="5" fill="#2b3240" />
                    <circle cx="174" cy="161" r="2.3" fill="#0e1a24" />
                    <circle cx="176.4" cy="157.4" r="1.5" fill="#ffffff" opacity=".9" />
                  </g>
                </g>
              </g>
            </g>

            <g class="p2d__brows">
              <path d="M114 140 Q126 134 138 140" fill="none" stroke="#2b3240" stroke-width="3.5" stroke-linecap="round" />
              <path d="M162 140 Q174 134 186 140" fill="none" stroke="#2b3240" stroke-width="3.5" stroke-linecap="round" />
            </g>

            <path d="M150 176 q -3 7 2 8" fill="none" stroke="#e3a98c" stroke-width="2" stroke-linecap="round" />
            <ellipse class="p2d__blush" cx="113" cy="182" rx="13" ry="6" />
            <ellipse class="p2d__blush" cx="187" cy="182" rx="13" ry="6" />

            <g class="p2d__mouth">
              <ellipse cx="150" cy="196" rx="15" ry="8" fill="#b4525a" />
              <path d="M140 193 Q150 190 160 193" fill="none" stroke="#ffffff" stroke-width="2" opacity=".45" stroke-linecap="round" />
            </g>
          </g>
        </g>
      </g>
    </g>
  </g>
</svg>`

export function createPersona2DStage({ container, id = 'persona-2d' } = {}) {
  const now = () => globalThis.performance?.now?.() ?? Date.now()
  const startedAt = now()

  const root = document.createElement('div')
  root.className = 'p2d'
  root.dataset.renderer = '2d'
  root.dataset.mode = id
  root.dataset.state = 'idle'
  root.dataset.speaking = 'false'
  root.setAttribute('role', 'img')
  container.replaceChildren(root)
  root.innerHTML = SVG

  const labelFor = (value) => PERSONA_STATE_LABELS[value] ?? value
  root.setAttribute('aria-label', `2D 动态数字人，当前状态：${labelFor('idle')}`)

  const lipSync = createLipSync()
  const frameSamples = []
  let frames = 0
  let firstFrameMs = 0
  let rafId = 0
  let lastFrameAt = 0
  let gestureTimer = 0
  let disposed = false

  const ready = new Promise((resolve) => {
    const done = () => {
      firstFrameMs = now() - startedAt
      resolve({ mode: '2d' })
    }
    if (typeof globalThis.requestAnimationFrame === 'function') {
      globalThis.requestAnimationFrame(() => globalThis.requestAnimationFrame(done))
    } else {
      globalThis.setTimeout(done, 0)
    }
  })

  function applyState(nextState) {
    const visual = build2DVisual(nextState)
    const style = root.style
    style.setProperty('--accent', visual.accent)
    style.setProperty('--head-tilt', `${visual.headTilt}deg`)
    style.setProperty('--head-nod', `${visual.headNod}px`)
    style.setProperty('--head-turn', `${visual.headTurn}px`)
    style.setProperty('--body-shift', `${visual.bodyShift}px`)
    style.setProperty('--gaze-x', `${visual.gazeX}px`)
    style.setProperty('--gaze-y', `${visual.gazeY}px`)
    style.setProperty('--brow-y', `${visual.browLift}px`)
    style.setProperty('--brow-angle', `${visual.browAngle}deg`)
    style.setProperty('--eye-scale', String(visual.eyeOpen))
    style.setProperty('--blush-op', String(visual.blush))
    style.setProperty('--breath-dur', `${visual.breathDuration}s`)
    style.setProperty('--breath-amp', `${visual.breathAmp}px`)
    root.dataset.state = nextState
    root.setAttribute('aria-label', `2D 动态数字人，当前状态：${labelFor(nextState)}`)
  }

  function applyMouth(weights) {
    const shape = mouthShape(weights)
    root.style.setProperty('--mouth-open', String(shape.open))
    root.style.setProperty('--mouth-wide', String(shape.wide))
  }

  function finishSpeaking() {
    root.dataset.speaking = 'false'
    applyMouth({})
  }

  function frame(ts) {
    rafId = 0
    if (disposed) return
    const dt = lastFrameAt ? Math.min((ts - lastFrameAt) / 1000, 0.06) : 1 / 60
    lastFrameAt = ts

    const costStart = now()
    const weights = lipSync.update(dt)
    applyMouth(weights)
    frameSamples.push(now() - costStart)
    if (frameSamples.length > 120) frameSamples.shift()
    frames += 1

    if (lipSync.isActive().mode === 'none') {
      finishSpeaking()
      return
    }
    rafId = globalThis.requestAnimationFrame(frame)
  }

  function startLoop() {
    root.dataset.speaking = 'true'
    if (rafId || disposed) return
    lastFrameAt = 0
    rafId = globalThis.requestAnimationFrame(frame)
  }

  function cancelLoop() {
    if (rafId) globalThis.cancelAnimationFrame(rafId)
    rafId = 0
  }

  function setState(_profile, { state = 'idle' } = {}) {
    if (disposed) return
    applyState(state)
  }

  function speakText(text, { cps } = {}) {
    if (disposed) return 0
    const duration = lipSync.speak(text, { cps })
    if (duration > 0) startLoop()
    else finishSpeaking()
    return duration
  }

  function speakTimeline(text, timing) {
    if (disposed) return false
    const planned = lipSync.speakTimeline(text, timing)
    startLoop()
    return planned
  }

  function seekSpeech(charIndex) {
    if (disposed) return
    lipSync.seek(charIndex)
  }

  function stopSpeaking() {
    lipSync.silence({ immediate: true })
    cancelLoop()
    finishSpeaking()
  }

  function playGesture(name) {
    if (disposed) return false
    clearTimeout(gestureTimer)
    root.dataset.gesture = gestureClass(name)
    gestureTimer = globalThis.setTimeout(() => {
      delete root.dataset.gesture
    }, GESTURE_MS)
    return true
  }

  function stopGesture() {
    clearTimeout(gestureTimer)
    gestureTimer = 0
    delete root.dataset.gesture
  }

  function summary() {
    if (!frameSamples.length) return { avg: 0, max: 0, p50: 0, p90: 0 }
    let sum = 0
    let max = 0
    for (const sample of frameSamples) {
      sum += sample
      if (sample > max) max = sample
    }
    const sorted = [...frameSamples].sort((a, b) => a - b)
    return {
      avg: sum / frameSamples.length,
      max,
      p50: sorted[Math.floor(sorted.length * 0.5)],
      p90: sorted[Math.floor(sorted.length * 0.9)]
    }
  }

  function stats() {
    const frame = summary()
    const heap = globalThis.performance?.memory?.usedJSHeapSize
    return {
      mode: '2d',
      drawCalls: 0,
      geometries: 0,
      textures: 0,
      expressions: [],
      firstFrameMs: Math.round(firstFrameMs),
      frameAvgMs: Number(frame.avg.toFixed(2)),
      frameMaxMs: Number(frame.max.toFixed(2)),
      frameP50Ms: Number(frame.p50.toFixed(2)),
      frameP90Ms: Number(frame.p90.toFixed(2)),
      pixelRatio: globalThis.devicePixelRatio || 1,
      degraded: false,
      frames,
      modelBytes: 0,
      heapMB: heap ? Number((heap / 1048576).toFixed(1)) : null
    }
  }

  function dispose() {
    if (disposed) return
    disposed = true
    cancelLoop()
    stopGesture()
    lipSync.dispose()
    root.remove()
  }

  return {
    ready,
    onContextLost: null,
    setState,
    speakText,
    speakTimeline,
    seekSpeech,
    stopSpeaking,
    playGesture,
    stopGesture,
    attachAudio: (element) => lipSync.attachAudio(element),
    detachAudio: () => lipSync.detachAudio(),
    resumeAudio: () => lipSync.resume(),
    setLookPoint: () => {},
    stats,
    dispose
  }
}
