<template>
  <div class="persona" :data-state="state" :data-render-mode="renderMode">
    <WebGLHost v-if="renderMode === 'webgl'" :key="hostGeneration" @mount="onHostMount" />
    <div v-else-if="renderMode === '2d'" ref="stage2d" class="persona__2d" />
    <div v-else class="persona__static" role="img" :aria-label="`静态替身，当前状态：${stateLabel}`">
      <span class="persona__static-mark" aria-hidden="true" />
      <p class="persona__static-title">静态替身模式</p>
      <p class="persona__static-reason">{{ staticReason }}</p>
    </div>
    <p class="persona__status">
      当前状态：{{ stateLabel }}
      <span class="persona__hint">{{ stateHint }}</span>
      <span v-if="emotionSource" class="persona__emotion" :data-tone="emotionSource.tone">
        · 情绪：{{ emotionText }}（{{ emotionSource.text }}）
      </span>
      <span class="persona__mode">· {{ modeLabel }}</span>
    </p>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import WebGLHost from './WebGLHost.vue'
import { createPersona2DStage } from './usePersona2D.js'
import {
  PERSONA_STATES,
  PERSONA_STATE_LABELS,
  personaProfile,
  personaTransitionMs
} from './personaStates.js'
import { emotionLabelText, emotionSourceLabel, withEmotion } from './emotionInput.js'
import { isLightweightVisualMode } from '../../visual/visualMode.js'

const props = defineProps({
  state: {
    type: String,
    default: 'idle',
    validator: (value) => PERSONA_STATES.includes(value)
  },
  quality: {
    type: String,
    default: 'auto',
    validator: (value) => ['auto', 'high', 'low', 'static'].includes(value)
  },
  modelUrl: {
    type: String,
    default: `${import.meta.env.BASE_URL}avatar/sendagaya-shino/model.vrm`
  },
  mode: {
    type: String,
    default: 'vrm',
    validator: (value) => ['vrm', 'programmatic'].includes(value)
  },
  /**
   * 情绪识别输入（P2-8）：`/api/nn/emotion` 的返回，或调用方自备的同形对象。
   * 只做 expressions 的 max 加成；告警 / 故障态不叠加（状态主导）。
   */
  emotion: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['ready', 'error', 'context-lost'])

/** 检测 WebGL：创建临时上下文即可，失败不抛错，交给 2D 兜底 */
function hasWebGL() {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

function staticReasonFor() {
  if (props.quality === 'static') return '已手动关闭 3D 渲染'
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return '运行环境不支持 WebGL 检测'
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return '系统偏好「减少动态效果」'
  return ''
}

/**
 * 渲染模式分三档：
 *  - webgl：桌面且硬件支持，走完整 3D；
 *  - 2d：移动端 / 无 WebGL / 轻量档位，走无 WebGL 的 2D 动态替身（口型、状态、手势仍生效）；
 *  - static：手动关闭或系统要求减少动态，才退回静态。
 */
function resolveRenderMode() {
  if (props.quality === 'static') return 'static'
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'static'
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return 'static'
  if (isLightweightVisualMode.value) return '2d'
  if (!hasWebGL()) return '2d'
  if (window.matchMedia('(pointer: coarse)').matches) return '2d'
  return 'webgl'
}

const stateLabel = computed(() => PERSONA_STATE_LABELS[props.state] ?? props.state)
const stateHint = computed(() => personaProfile(props.state).hint)
/** 状态 profile（未叠加情绪）；stageProfile 由它派生，保持渲染层入参形状不变 */
const baseProfile = computed(() => personaProfile(props.state))
const stageProfile = computed(() =>
  withEmotion(baseProfile.value, props.emotion, { state: props.state })
)
/** 情绪是否真的生效（被状态拦下 / 引擎不可用 / 低置信 → false） */
const emotionActive = computed(() => stageProfile.value !== baseProfile.value)
const emotionSource = computed(() => (emotionActive.value ? emotionSourceLabel(props.emotion) : null))
const emotionText = computed(() =>
  emotionActive.value ? emotionLabelText(props.emotion?.label) : ''
)
const initialMode = resolveRenderMode()
const renderMode = ref(initialMode)
const staticReason = ref(initialMode === 'static' ? staticReasonFor() : '')
const modeLabel = computed(() => {
  if (renderMode.value === 'webgl') return '3D 实时'
  if (renderMode.value === '2d') return '2D 动态替身'
  return '静态替身'
})
const hostGeneration = ref(0)
const stage2d = ref(null)

let stage = null
/** 异步加载 3D 期间页面可能已卸载或降级，用令牌丢弃过期结果 */
let mountToken = 0

function teardown() {
  mountToken += 1
  stage?.dispose()
  stage = null
}

/** 降级到 2D 动态替身：优先保留"会动、会说话"的数字人，而不是直接变静态图 */
function degradeTo2D(reason) {
  teardown()
  staticReason.value = reason
  renderMode.value = '2d'
  nextTick(() => mount2D())
}

function mount2D() {
  if (!stage2d.value) return
  teardown()
  try {
    stage = createPersona2DStage({ container: stage2d.value, id: `agent-persona-2d-${hostGeneration.value}` })
  } catch (error) {
    renderMode.value = 'static'
    staticReason.value = `2D 替身初始化失败：${error?.message ?? '未知错误'}`
    emit('error', error)
    return
  }
  stage.setState(stageProfile.value, { fade: 0, state: props.state })
  stage.ready
    .then(() => {
      if (!stage) return
      emit('ready', stage.stats())
    })
    .catch((error) => {
      teardown()
      renderMode.value = 'static'
      staticReason.value = `2D 替身初始化失败：${error?.message ?? '未知错误'}`
      emit('error', error)
    })
}

async function onHostMount({ canvas, container }) {
  teardown()
  const token = mountToken

  // 3D 依赖（three.js / VRM 运行时）按需加载：移动端走 2D 时完全不下载
  let module = null
  try {
    module = props.mode === 'programmatic'
      ? await import('./useProgrammaticAvatar.js')
      : await import('./useVrmModel.js')
  } catch (error) {
    if (token === mountToken) degradeTo2D(`3D 模块加载失败：${error?.message ?? '未知错误'}`)
    return
  }
  if (token !== mountToken || renderMode.value !== 'webgl') return

  const factory = props.mode === 'programmatic' ? module.createProgrammaticAvatar : module.createVrmStage
  const options =
    props.mode === 'programmatic'
      ? { canvas, container, id: `agent-persona-pgm-${hostGeneration.value}` }
      : { canvas, container, modelUrl: props.modelUrl, id: `agent-persona-${hostGeneration.value}` }
  try {
    stage = factory(options)
  } catch (error) {
    degradeTo2D(`3D 初始化失败：${error?.message ?? '未知错误'}`)
    return
  }
  // context-lost 降级：先切 2D 动态替身，再通知上层
  stage.onContextLost = () => {
    degradeTo2D('WebGL 上下文丢失，已切换 2D 动态替身')
    emit('context-lost')
  }

  // 首个状态直接上屏，不做淡入，避免「先站直再变成目标姿态」的抖动
  stage.setState(stageProfile.value, { fade: 0, state: props.state })

  stage.ready
    .then(() => {
      if (!stage) return
      emit('ready', stage.stats())
    })
    .catch((error) => {
      // 模型失败不再直接变静态图：切 2D 动态替身仍可完成演示
      degradeTo2D(`模型加载失败：${error?.message ?? '未知错误'}`)
    })
}

watch(
  () => props.state,
  (next, previous) => {
    // 情绪与状态一起参与合成：告警 / 故障态由 withEmotion 拦下，不改变状态语义
    const nextProfile = withEmotion(personaProfile(next), props.emotion, { state: next })
    stage?.setState(nextProfile, { fade: personaTransitionMs(previous, next), state: next })
  }
)

// 情绪输入变化（用户这句话识别结果回来）时，只刷 expressions，不重启渲染
watch(
  () => props.emotion,
  (next) => {
    const nextProfile = withEmotion(baseProfile.value, next, { state: props.state })
    if (nextProfile !== baseProfile.value) {
      stage?.setState(nextProfile, {
        fade: personaTransitionMs(props.state, props.state),
        state: props.state
      })
    }
  }
)

onMounted(() => {
  if (renderMode.value === '2d') mount2D()
})

/**
 * 命令式接口：口型由调用方驱动（自己持有 <audio> 与文案），
 * readStats 供页面轮询帧时 / 降级状态。
 */
defineExpose({
  attachAudio: (element) => stage?.attachAudio(element),
  detachAudio: () => stage?.detachAudio?.(),
  resumeAudio: () => stage?.resumeAudio(),
  speakText: (text, options) => stage?.speakText(text, options),
  speakTimeline: (text, timing) => stage?.speakTimeline(text, timing),
  seekSpeech: (charIndex) => stage?.seekSpeech(charIndex),
  stopSpeaking: () => stage?.stopSpeaking(),
  playGesture: (name, options) => stage?.playGesture(name, options) ?? false,
  stopGesture: () => stage?.stopGesture(),
  setLookPoint: (x, y) => stage?.setLookPoint?.(x, y),
  readStats: () => stage?.stats() ?? null
})

onBeforeUnmount(teardown)
</script>

<style scoped>
.persona {
  display: grid;
  gap: var(--ds-space-3);
  padding: var(--ds-space-4);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: radial-gradient(120% 90% at 50% 0%, rgba(36, 150, 237, .12), transparent 62%), var(--ds-color-surface-raised);
}

.persona__2d {
  width: 100%;
  min-height: 0;
}

.persona__static {
  display: grid;
  place-content: center;
  justify-items: center;
  gap: var(--ds-space-2);
  width: 100%;
  max-width: 420px;
  margin-inline: auto;
  aspect-ratio: 3 / 4;
  border: 1px dashed var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  color: var(--ds-color-muted);
  text-align: center;
  padding: var(--ds-space-6);
}

.persona__static-mark {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 1px solid var(--ds-color-border-strong);
  background: radial-gradient(circle at 50% 38%, rgba(122, 215, 245, .45), transparent 68%);
}

.persona__static-title {
  margin: 0;
  color: var(--ds-color-text);
  font-size: var(--ds-font-md);
}

.persona__static-reason {
  margin: 0;
  font-size: var(--ds-font-xs);
  max-width: 28ch;
}

.persona__status {
  margin: 0;
  font-size: var(--ds-font-xs);
  color: var(--ds-color-muted);
  letter-spacing: .04em;
}

.persona__hint {
  margin-left: var(--ds-space-2);
  color: var(--ds-color-text);
}

.persona__mode {
  margin-left: var(--ds-space-2);
  color: var(--ds-color-muted);
  opacity: .8;
}

.persona__emotion {
  margin-left: var(--ds-space-2);
  color: var(--ds-color-muted);
}

.persona__emotion[data-tone='model'] {
  color: var(--ds-color-primary-strong);
}

.persona__emotion[data-tone='lexicon'] {
  color: var(--ds-color-warning);
}

/* 状态色只做第三通道：灰度下靠姿态/节奏区分，颜色仅用于强化 */
.persona[data-state='warning'] {
  border-color: color-mix(in srgb, var(--smart-warning) 50%, transparent);
}

.persona[data-state='error'] {
  border-color: color-mix(in srgb, var(--smart-danger) 55%, transparent);
}

.persona[data-state='recovering'] {
  border-color: color-mix(in srgb, var(--smart-success) 45%, transparent);
}

@media (prefers-reduced-motion: reduce) {
  .persona {
    background: var(--ds-color-surface-raised);
  }
}
</style>
