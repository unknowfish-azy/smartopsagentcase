<template>
  <article class="vision-event" :data-status="event.analysisStatus" aria-label="视觉证据分析状态">
    <div class="vision-event__head"><strong>视觉证据 · {{ sourceLabel }}</strong><span>{{ event.ocrStatus }}</span></div>
    <p v-if="event.ocrText" class="vision-event__text">{{ event.ocrText }}</p>
    <dl><div><dt>置信度</dt><dd>{{ confidence }}</dd></div><div><dt>隐私</dt><dd>{{ event.privacyStatus }}</dd></div><div><dt>分析</dt><dd>{{ event.analysisStatus }}</dd></div></dl>
    <p v-if="event.analysisStatus === 'MANUAL_REVIEW' || event.privacyStatus === 'REDACTION_REQUIRED'" class="vision-event__notice">需要人工核对后才能用于故障判断或知识沉淀。</p>
  </article>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ event: { type: Object, required: true } })
const labels = { SCREENSHOT: '截屏', CAMERA: '拍照', CLIPBOARD: '剪贴板', FILE: '文件', DRAG_DROP: '拖拽' }
const sourceLabel = computed(() => labels[props.event.sourceType] || '图片')
const confidence = computed(() => typeof props.event.confidence === 'number' ? `${Math.round(props.event.confidence * 100)}%` : '未评估')
</script>
<style scoped>
.vision-event{display:grid;gap:8px;margin-top:10px;padding:10px;border:1px solid var(--smart-border-strong);border-left:3px solid var(--smart-primary-strong);background:var(--smart-surface);color:var(--smart-text);font-size:11px}.vision-event__head{display:flex;justify-content:space-between;gap:10px}.vision-event__head span{color:var(--smart-primary-strong);font:9px var(--font-mono)}.vision-event__text{margin:0;color:var(--smart-muted);white-space:pre-wrap;overflow-wrap:anywhere}.vision-event dl{display:flex;flex-wrap:wrap;gap:12px;margin:0}.vision-event dl div{display:grid;gap:3px}.vision-event dt{color:var(--smart-muted);font-size:9px}.vision-event dd{margin:0;font-family:var(--font-mono)}.vision-event__notice{margin:0;color: var(--smart-warning);line-height:1.5}
</style>
