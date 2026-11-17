<template>
  <section class="video-panel" aria-labelledby="robot-vision-title">
    <div class="panel-head">
      <h2 id="robot-vision-title">视觉回传</h2>
      <div class="head-pills">
        <span v-if="simulated" class="pill pill-neutral">模拟帧</span>
        <span class="pill" :class="visionConfigured ? 'pill-ok' : 'pill-warn'">
          {{ visionConfigured ? '视觉模型已配置' : '视觉模型未配置' }}
        </span>
        <span class="pill pill-neutral">{{ frameTimeText }}</span>
      </div>
    </div>

    <div class="stage">
      <canvas ref="canvasEl" class="stage-canvas" width="640" height="360" aria-label="机器人摄像头关键帧"></canvas>
      <p v-if="!frameSrc" class="stage-placeholder">
        尚无关键帧。关键帧仅在拍照或自主抽帧时低频回传（≥2s/帧），不拉取原始视频流。
      </p>
    </div>

    <div class="panel-actions">
      <button type="button" class="btn" :disabled="captureDisabled" @click="emit('capture')">
        立即拍照
      </button>
      <span class="hint-text">拍照结论写入纠察中心（status=REVIEW，需人工复核）</span>
    </div>

    <dl v-if="analysis" class="analysis" aria-live="polite">
      <div class="analysis-row">
        <dt>识别结论</dt>
        <dd>
          <span class="pill" :class="analysisPillClass">{{ analysisStatusText }}</span>
          <span v-if="abnormalText" class="analysis-claim">{{ abnormalText }}</span>
        </dd>
      </div>
      <div v-if="summaryText" class="analysis-row">
        <dt>模型摘要</dt>
        <dd class="analysis-summary">{{ summaryText }}</dd>
      </div>
      <div v-if="issuesText" class="analysis-row">
        <dt>发现问题</dt>
        <dd class="analysis-summary">{{ issuesText }}</dd>
      </div>
      <div class="analysis-row">
        <dt>追溯</dt>
        <dd>
          <RouterLink v-if="eventId" :to="`/inspector/events/${eventId}`" class="analysis-link">
            {{ eventId }} · 去纠察中心复核
          </RouterLink>
          <span v-else class="analysis-muted">{{ analysisMessage || '暂无事件编号' }}</span>
        </dd>
      </div>
    </dl>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

/**
 * 机器人视觉回传面板（M2）。
 *
 * 关键帧用 canvas 绘制而非 <video>：设备只上报低频 JPEG 关键帧，
 * 不提供流媒体地址，用 video 会伪造出「实时视频」的观感。
 * 识别结论一律标注为模型主张，最终处置在纠察中心人工复核。
 */
const props = defineProps({
  frameSrc: { type: String, default: '' },
  frameAt: { type: String, default: '' },
  simulated: { type: Boolean, default: false },
  visionConfigured: { type: Boolean, default: false },
  analysis: { type: Object, default: null },
  captureDisabled: { type: Boolean, default: false }
})

const emit = defineEmits(['capture'])

const canvasEl = ref(null)
let image = null

const frameTimeText = computed(() => (props.frameAt ? `最近关键帧 ${props.frameAt}` : '等待桥回传'))

const analysisStatusText = computed(() => {
  const status = props.analysis?.status
  if (status === 'OK') return '识别完成'
  if (status === 'THROTTLED') return '触发过频'
  if (status === 'VISION_UNAVAILABLE') return '模型不可用'
  return '识别失败'
})

const analysisPillClass = computed(() => {
  const status = props.analysis?.status
  if (status === 'OK') return 'pill-ok'
  return 'pill-warn'
})

const abnormalText = computed(() => {
  const value = props.analysis?.analysis?.abnormal
  if (value === undefined || value === null) return ''
  return value ? '模型主张：发现异常' : '模型主张：未见异常'
})

const summaryText = computed(() => props.analysis?.analysis?.summary || '')
const issuesText = computed(() => {
  const issues = props.analysis?.analysis?.issues
  return Array.isArray(issues) && issues.length ? issues.join('；') : ''
})
const eventId = computed(() => props.analysis?.eventId || props.analysis?.inspectionId || '')
const analysisMessage = computed(() => props.analysis?.message || '')

function draw() {
  const canvas = canvasEl.value
  if (!canvas) return
  const context = canvas.getContext('2d')
  if (!context) return
  if (!props.frameSrc) {
    context.clearRect(0, 0, canvas.width, canvas.height)
    return
  }
  const picture = new Image()
  picture.onload = () => {
    context.clearRect(0, 0, canvas.width, canvas.height)
    const scale = Math.min(canvas.width / picture.width, canvas.height / picture.height)
    const width = picture.width * scale
    const height = picture.height * scale
    context.drawImage(picture, (canvas.width - width) / 2, (canvas.height - height) / 2, width, height)
  }
  picture.src = props.frameSrc
  image = picture
}

watch(() => props.frameSrc, draw, { immediate: true })

onBeforeUnmount(() => {
  if (image) image.onload = null
  image = null
})
</script>

<style scoped>
.video-panel {
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
}

.panel-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-3);
  margin-bottom: var(--ds-space-3);
}

.panel-head h2 {
  margin: 0;
  font-size: var(--ds-font-lg);
}

.head-pills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space-2);
}

.stage {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  border: 1px dashed var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-canvas);
  overflow: hidden;
}

.stage-canvas {
  width: 100%;
  height: auto;
  max-height: 340px;
  display: block;
}

.stage-placeholder {
  position: absolute;
  margin: 0;
  padding: var(--ds-space-4);
  color: var(--ds-color-muted);
  font-size: var(--ds-font-sm);
  text-align: center;
}

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space-3);
  margin-top: var(--ds-space-3);
}

.analysis {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-2);
  margin: var(--ds-space-3) 0 0;
  padding: var(--ds-space-3);
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
}

.analysis-row {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: var(--ds-space-2);
  align-items: start;
}

.analysis-row dt {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
}

.analysis-row dd {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space-2);
  font-size: var(--ds-font-sm);
}

.analysis-claim,
.analysis-summary,
.analysis-muted {
  color: var(--ds-color-text);
  line-height: var(--ds-line-base);
}

.analysis-link {
  color: var(--ds-color-primary);
  font-family: var(--ds-font-mono);
  font-size: var(--ds-font-xs);
}

.btn {
  height: var(--ds-control-height, 36px);
  padding: 0 var(--ds-space-4);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: var(--ds-color-surface-raised);
  color: var(--ds-color-text);
  font-size: var(--ds-font-sm);
  cursor: pointer;
  transition: border-color var(--ds-duration-fast) ease;
}

.btn:hover:not(:disabled) {
  border-color: var(--ds-color-primary);
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
  font-size: var(--ds-font-xs);
  white-space: nowrap;
}

.pill-ok {
  background: rgba(139, 207, 180, 0.16);
  color: var(--ds-color-success);
}

.pill-warn {
  background: rgba(217, 185, 109, 0.16);
  color: var(--ds-color-warning);
}

.pill-neutral {
  background: var(--ds-pill-neutral-bg, rgba(159, 190, 207, 0.12));
  color: var(--ds-color-muted);
}

.hint-text {
  margin: 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: var(--ds-line-base);
}

@media (prefers-reduced-motion: reduce) {
  .btn {
    transition: none;
  }
}
</style>
