<template>
  <div class="persona" :data-state="state">
    <WebGLHost v-if="webglEnabled" :key="hostGeneration" @mount="onHostMount" />
    <div v-else class="persona__static" role="img" :aria-label="`静态替身，当前状态：${stateLabel}`">
      <span class="persona__static-mark" aria-hidden="true" />
      <p class="persona__static-title">静态替身模式</p>
      <p class="persona__static-reason">{{ fallbackReason }}</p>
    </div>
    <p class="persona__status">
      当前状态：{{ stateLabel }}
      <span class="persona__hint">{{ stateHint }}</span>
    </p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import WebGLHost from './WebGLHost.vue'
import { createVrmStage } from './useVrmModel.js'
import {
  PERSONA_STATES,
  PERSONA_STATE_LABELS,
  personaProfile,
  personaTransitionMs
} from './personaStates.js'
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
  }
})

const emit = defineEmits(['ready', 'error', 'context-lost'])

/** 进入页面时决定是否加载 3D：宁可退回静态，也不在弱设备上硬拉 15MB 占位模型 */
function detectFallback() {
  if (props.quality === 'static') return '已手动关闭 3D 渲染'
  if (isLightweightVisualMode.value) return '当前视觉档位为轻量模式'
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return '运行环境不支持 WebGL 检测'
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return '系统偏好「减少动态效果」'
  if (window.matchMedia('(pointer: coarse)').matches) return '移动端默认不加载 3D'
  return ''
}

const stateLabel = computed(() => PERSONA_STATE_LABELS[props.state] ?? props.state)
const stateHint = computed(() => personaProfile(props.state).hint)
const fallbackReason = ref(detectFallback())
const webglEnabled = ref(!fallbackReason.value)
const hostGeneration = ref(0)

let stage = null

function teardown() {
  stage?.dispose()
  stage = null
}

function onHostMount({ canvas, container }) {
  teardown()
  stage = createVrmStage({
    canvas,
    container,
    modelUrl: props.modelUrl,
    id: `agent-persona-${hostGeneration.value}`,
    onContextLost: () => {
      teardown()
      fallbackReason.value = 'WebGL 上下文丢失，已降级为静态替身'
      webglEnabled.value = false
      emit('context-lost')
    }
  })

  // 首个状态直接上屏，不做淡入，避免「先站直再变成目标姿态」的抖动
  stage.setState(personaProfile(props.state), { fade: 0 })

  stage.ready
    .then((vrm) => {
      if (!vrm || !stage) return
      emit('ready', stage.stats())
    })
    .catch((error) => {
      teardown()
      fallbackReason.value = `模型加载失败：${error?.message ?? '未知错误'}`
      webglEnabled.value = false
      emit('error', error)
    })
}

watch(
  () => props.state,
  (next, previous) => {
    stage?.setState(personaProfile(next), { fade: personaTransitionMs(previous, next) })
  }
)

/**
 * 口型相关的命令式接口：调用方自己持有 <audio> 与文案，
 * 组件只负责把声音/文字变成嘴型。
 */
defineExpose({
  attachAudio: (element) => stage?.attachAudio(element),
  resumeAudio: () => stage?.resumeAudio(),
  speakText: (text, options) => stage?.speakText(text, options),
  stopSpeaking: () => stage?.stopSpeaking()
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

/* 状态色只做第三通道：灰度下靠姿态/节奏区分，颜色仅用于强化 */
.persona[data-state='warning'] {
  border-color: rgba(217, 185, 109, .5);
}

.persona[data-state='error'] {
  border-color: rgba(220, 132, 144, .55);
}

.persona[data-state='recovering'] {
  border-color: rgba(139, 207, 180, .45);
}

@media (prefers-reduced-motion: reduce) {
  .persona {
    background: var(--ds-color-surface-raised);
  }
}
</style>
