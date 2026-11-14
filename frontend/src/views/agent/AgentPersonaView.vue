<template>
  <section class="persona-view">
    <header class="persona-view__head">
      <p class="persona-view__eyebrow">AGENT PERSONA / 小鱼 · 3D 化身</p>
      <h1 class="persona-view__title">小鱼</h1>
      <p class="persona-view__desc">
        继鲸（基础设施）、蛛（集群）、水母（Agent 觉察）之后的第四个生命体：Agent 的人格化身。
        当前处于加载链路验证阶段，形象为 CC0 sendagaya-shino 占位模型，不参与任何控制台决策。
      </p>
    </header>

    <div class="persona-view__stage">
      <AgentPersona
        ref="personaRef"
        :state="previewState"
        @ready="onReady"
        @error="onError"
        @context-lost="onLost"
      />
    </div>

    <div class="persona-view__states" role="group" aria-label="状态预览">
      <p class="persona-view__states-label">状态预览</p>
      <div class="persona-view__state-buttons">
        <button
          v-for="state in PERSONA_STATES"
          :key="state"
          type="button"
          class="persona-view__state-button"
          :class="{ 'is-active': state === previewState }"
          :aria-pressed="state === previewState"
          @click="previewState = state"
        >
          {{ PERSONA_STATE_LABELS[state] }}
        </button>
      </div>
    </div>

    <div class="persona-view__speech">
      <p class="persona-view__states-label">口型演示</p>
      <div class="persona-view__state-buttons">
        <button type="button" class="persona-view__state-button" @click="playDemoClip">
          播放 10 秒示例音频
        </button>
        <button type="button" class="persona-view__state-button" @click="speakDemoText">
          文字近似口型
        </button>
        <button type="button" class="persona-view__state-button" @click="stopSpeech">停止</button>
      </div>
      <audio ref="audioElement" class="persona-view__audio" controls preload="none" />
      <p class="persona-view__note">
        口型来源：<strong>{{ speechSource }}</strong>。示例音频是页面内合成的元音序列，走真实频谱分析；
        文字模式按字推送时间线，<strong>不与音频同步</strong>，只验证「会动、停下后闭嘴」。
      </p>
    </div>

    <dl class="persona-view__stats">
      <div class="persona-view__stat">
        <dt>渲染状态</dt>
        <dd><span class="persona-view__pill" :data-tone="statusTone">{{ statusText }}</span></dd>
      </div>
      <div class="persona-view__stat">
        <dt>Draw call</dt>
        <dd>{{ stats?.drawCalls ?? '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>几何 / 贴图</dt>
        <dd>{{ stats ? `${stats.geometries} / ${stats.textures}` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>帧时（P50 / P90）</dt>
        <dd>{{ stats ? `${stats.frameP50Ms} / ${stats.frameP90Ms} ms` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>首帧</dt>
        <dd>{{ stats ? `${stats.firstFrameMs} ms` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>模型传输</dt>
        <dd>{{ stats?.modelBytes ? `${(stats.modelBytes / 1048576).toFixed(1)} MB` : '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>JS 堆</dt>
        <dd>{{ stats?.heapMB ? `${stats.heapMB} MB` : '不可读' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>像素比</dt>
        <dd>{{ stats?.pixelRatio ?? '—' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>降级</dt>
        <dd>{{ stats?.degraded ? '已降级（慢帧持续 2s）' : '正常' }}</dd>
      </div>
      <div class="persona-view__stat">
        <dt>状态通道</dt>
        <dd>文本 + 色彩（非仅 3D）</dd>
      </div>
    </dl>

    <p class="persona-view__note">
      占位模型：Sendagaya Shino（CC0，VRoid 官方示例）。许可与出处见
      <code>/avatar/sendagaya-shino/model.LICENSE.txt</code> 与 <code>model.SOURCE.txt</code>。
      该模型 15MB / 17 材质，超出正式预算，仅用于打通链路，不作为性能基线。
    </p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import AgentPersona from '../../components/persona/AgentPersona.vue'
import { PERSONA_STATES, PERSONA_STATE_LABELS } from '../../components/persona/personaStates.js'

const previewState = ref('idle')
const status = ref('loading')
const stats = ref(null)
const errorMessage = ref('')
const personaRef = ref(null)
const audioElement = ref(null)
const speechSource = ref('静默')

let demoAudioUrl = ''
let textTimer = 0
let statsTimer = 0

const statusText = computed(() => {
  if (status.value === 'ready') return '加载完成'
  if (status.value === 'error') return `加载失败：${errorMessage.value}`
  if (status.value === 'lost') return '上下文丢失，已降级'
  return '加载中'
})

const statusTone = computed(() => {
  if (status.value === 'ready') return 'success'
  if (status.value === 'error') return 'danger'
  if (status.value === 'lost') return 'warning'
  return 'neutral'
})

function onReady(payload) {
  status.value = 'ready'
  stats.value = payload
  startStatsPolling()
}

function onError(error) {
  stopStatsPolling()
  status.value = 'error'
  errorMessage.value = error?.message ?? '未知错误'
}

function onLost() {
  stopStatsPolling()
  status.value = 'lost'
}

/** 每秒拉一次遥测：帧时 / 降级是持续变化的，只在 ready 时取一次会失真 */
function startStatsPolling() {
  stopStatsPolling()
  statsTimer = setInterval(() => {
    const snapshot = personaRef.value?.readStats?.()
    if (snapshot) stats.value = snapshot
  }, 1000)
}

function stopStatsPolling() {
  if (statsTimer) clearInterval(statsTimer)
  statsTimer = 0
}

/** 页面内合成 10 秒元音序列，接进真实的 <audio> → AnalyserNode 链路 */
async function playDemoClip() {
  const element = audioElement.value
  if (!element || !personaRef.value) return
  if (!demoAudioUrl) demoAudioUrl = buildDemoAudioUrl(10)
  if (element.src !== demoAudioUrl) element.src = demoAudioUrl
  personaRef.value.attachAudio(element)
  await personaRef.value.resumeAudio()
  element.currentTime = 0
  element.addEventListener('ended', () => { speechSource.value = '静默' }, { once: true })
  try {
    await element.play()
    speechSource.value = '合成音频 · 真实频谱'
  } catch {
    speechSource.value = '浏览器拦截了播放，请再点一次'
  }
}

/** 无音频时的近似口型：按字推进，UI 明确标注不是同步 */
function speakDemoText() {
  audioElement.value?.pause()
  const text = '正在检查集群节点健康状态，发现两个副本延迟偏高，准备滚动重启。'
  const duration = personaRef.value?.speakText(text, { cps: 5 }) ?? 0
  speechSource.value = duration ? '文字近似 · 非音频同步' : '静默'
  clearTimeout(textTimer)
  if (duration) textTimer = setTimeout(() => { speechSource.value = '静默' }, duration + 400)
}

function stopSpeech() {
  audioElement.value?.pause()
  personaRef.value?.stopSpeaking()
  clearTimeout(textTimer)
  speechSource.value = '静默'
}

onBeforeUnmount(() => {
  stopStatsPolling()
  clearTimeout(textTimer)
  if (demoAudioUrl) URL.revokeObjectURL(demoAudioUrl)
})

/**
 * 合成一段「元音序列」音频：带音节包络与两处停顿。
 * 只为让频谱有起伏，不是真人声，也不代表任何 TTS 音色。
 */
function buildDemoAudioUrl(seconds = 10, sampleRate = 22050) {
  const totalSamples = Math.floor(seconds * sampleRate)
  const bytes = new ArrayBuffer(44 + totalSamples * 2)
  const view = new DataView(bytes)
  const writeText = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeText(0, 'RIFF')
  view.setUint32(4, 36 + totalSamples * 2, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeText(36, 'data')
  view.setUint32(40, totalSamples * 2, true)

  const harmonics = 18
  const formants = [
    [780, 1200], // aa
    [500, 900], // oh
    [400, 2000], // ih
    [380, 800], // ou
    [300, 2300] // ee
  ]
  // 每种元音的谐波权重只算一次，逐样本只剩 sin
  const weightsByVowel = formants.map(([f1, f2]) =>
    Array.from({ length: harmonics }, (_, index) => {
      const hz = 155 * (index + 1)
      return 0.12 + 1.5 * Math.exp(-(((hz - f1) / 190) ** 2)) + 1.1 * Math.exp(-(((hz - f2) / 230) ** 2))
    })
  )
  const syllable = 0.22
  const pauses = [[3, 3.45], [6.35, 6.8]]
  const twoPi = Math.PI * 2
  for (let i = 0; i < totalSamples; i += 1) {
    const t = i / sampleRate
    const paused = pauses.some(([start, end]) => t >= start && t < end)
    const phase = (t % syllable) / syllable
    const envelope = paused ? 0 : Math.min(1, phase / 0.2, (1 - phase) / 0.25)
    if (envelope <= 0) continue
    const f0 = 155 + 12 * Math.sin(twoPi * 3.1 * t)
    const weights = weightsByVowel[Math.floor(t / syllable) % weightsByVowel.length]
    let sample = 0
    for (let h = 1; h <= harmonics; h += 1) {
      sample += (Math.sin(twoPi * f0 * h * t + h * 0.7) / h) * weights[h - 1]
    }
    const value = Math.max(-1, Math.min(1, sample * envelope * 0.18))
    view.setInt16(44 + i * 2, value * 0x7fff, true)
  }
  return URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }))
}
</script>

<style scoped>
.persona-view {
  display: grid;
  gap: var(--ds-space-6);
  max-width: 720px;
  margin: 0 auto;
  padding: var(--ds-space-8) var(--ds-space-4);
}

.persona-view__head {
  display: grid;
  gap: var(--ds-space-2);
}

.persona-view__eyebrow {
  margin: 0;
  font-size: var(--ds-type-overline-size);
  font-weight: var(--ds-type-overline-weight);
  letter-spacing: .18em;
  color: var(--ds-color-primary-strong);
}

.persona-view__title {
  margin: 0;
  font-size: var(--ds-type-h1-size);
  font-weight: var(--ds-type-h1-weight);
  color: var(--ds-color-text);
}

.persona-view__desc {
  margin: 0;
  font-size: var(--ds-type-body-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-muted);
}

.persona-view__states {
  display: grid;
  gap: var(--ds-space-2);
}

.persona-view__states-label {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-view__state-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-2);
}

.persona-view__state-button {
  padding: var(--ds-space-1) var(--ds-space-3);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-pill);
  background: transparent;
  color: var(--ds-color-muted);
  font-size: var(--ds-type-caption-size);
  cursor: pointer;
  transition: color .18s ease, border-color .18s ease;
}

.persona-view__state-button:hover {
  color: var(--ds-color-text);
}

.persona-view__state-button.is-active {
  color: var(--ds-color-primary-strong);
  border-color: var(--ds-color-primary-strong);
}

.persona-view__speech {
  display: grid;
  gap: var(--ds-space-2);
}

.persona-view__audio {
  width: 100%;
  height: 36px;
}

.persona-view__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--ds-space-3);
  margin: 0;
  padding: var(--ds-space-4);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-card);
}

.persona-view__stat dt {
  font-size: var(--ds-type-caption-size);
  color: var(--ds-color-muted);
}

.persona-view__stat dd {
  margin: var(--ds-space-1) 0 0;
  font-size: var(--ds-font-md);
  color: var(--ds-color-text);
  font-variant-numeric: var(--ds-type-num);
}

.persona-view__pill {
  display: inline-block;
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
  font-size: var(--ds-type-caption-size);
  border: 1px solid var(--ds-color-border-strong);
  color: var(--ds-color-muted);
}

.persona-view__pill[data-tone='success'] {
  color: var(--ds-color-success);
  border-color: color-mix(in srgb, var(--smart-success) 45%, transparent);
}

.persona-view__pill[data-tone='warning'] {
  color: var(--ds-color-warning);
  border-color: color-mix(in srgb, var(--smart-warning) 45%, transparent);
}

.persona-view__pill[data-tone='danger'] {
  color: var(--ds-color-danger);
  border-color: color-mix(in srgb, var(--smart-danger) 45%, transparent);
}

.persona-view__note {
  margin: 0;
  font-size: var(--ds-type-caption-size);
  line-height: var(--ds-line-height-base);
  color: var(--ds-color-muted);
}

.persona-view__note code {
  font-size: 12px;
  color: var(--ds-color-primary-strong);
}
</style>
