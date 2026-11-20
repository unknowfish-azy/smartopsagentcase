<template>
  <div class="fc-preventive">
    <!-- 无越界：友好提示，与越界预测卡同口径 -->
    <p v-if="!items.length" class="fc-preventive__empty">
      {{ horizon }}s 视野内没有达到预防阈值的越界预测；可把视野拉长再看，或保持现况。
    </p>

    <div
      v-for="item in items"
      :key="item.key"
      class="fc-preventive__item"
      :class="{ 'fc-preventive__item--crit': item.kind === 'crit' }"
    >
      <p class="fc-preventive__head">
        <b>{{ item.sensorCn }} {{ item.sensorEn }}</b>
        <span class="fc-preventive__when" :class="{ 'fc-preventive__when--crit': item.kind === 'crit' }">
          +{{ item.h }}s · 置信 {{ item.confidence.toFixed(2) }}
        </span>
      </p>
      <small class="fc-preventive__action">{{ item.action }}</small>

      <div class="fc-preventive__row">
        <button type="button" :disabled="busy" @click="generate(item)">
          {{ busy ? '生成中…' : '生成契约草案' }}
        </button>
        <span v-if="error" class="fc-preventive__error">{{ error }}</span>
      </div>

      <div v-if="draft" class="fc-preventive__draft">
        <p class="fc-preventive__summary">{{ draft.summary }}</p>
        <details class="fc-preventive__json">
          <summary>展开草案 JSON（交 Agent 运行手册签发）</summary>
          <pre>{{ draftJson }}</pre>
        </details>
        <div class="fc-preventive__row">
          <button type="button" :disabled="busy" @click="copyDraft">复制草案 JSON</button>
          <span v-if="copyHint" class="fc-preventive__hint">{{ copyHint }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { SENSORS, crossingEvents } from '../../domain/forecast/syntheticSeries.js'
import { createForecastContractDraft } from '../../api/sentinelForecast.ts'

/**
 * 预防动作建议（P1-4）：越界预测置信度达阈值时给出"建议提前准备的动作"，
 * 可一键生成预防性恢复契约草案（digest 空、不自动执行——人在环上）。
 * 数据源与「越界预测」卡同源：优先 payload.crossings，离线回退合成事件。
 */
const props = defineProps({
  primaryKey: { type: String, required: true },
  generatedAt: { type: Number, default: 0 },
  now: { type: Number, default: 0 },
  horizon: { type: Number, default: 30 },
  crossings: { type: Array, default: () => [] }
})

/** warn 级只有置信度达到该阈值才进入建议；crit 全收 */
const WARN_CONFIDENCE_MIN = 0.62

/** 传感器语义 → 预防动作文案（占位：接入真实资产后按资产类型替换） */
const PREVENTIVE_ACTIONS = {
  ect: '检查散热回路与冷却液余量，提前降载错峰。',
  rpm: '下调负载曲线，错峰高转速任务窗口。',
  egt: '排查排温上升来源，预备限流与散热冗余。',
  oilp: '检查润滑供压链路，预备低载荷停机窗口。'
}
const DEFAULT_ACTION = '按该传感器语义制定预防动作；当前以服务健康观察契约兜底。'

const draft = ref(null)
const draftJson = computed(() => (draft.value ? JSON.stringify(draft.value.draft, null, 2) : ''))
const busy = ref(false)
const error = ref('')
const copyHint = ref('')

function actionFor(sensorKey) {
  return PREVENTIVE_ACTIONS[sensorKey] || DEFAULT_ACTION
}

const candidates = computed(() => {
  const nowSec = props.generatedAt + props.now
  const list = []
  if (props.crossings?.length) {
    const primary = SENSORS.find((s) => s.key === props.primaryKey) || SENSORS[0]
    props.crossings.forEach((c) => {
      list.push({ sensor: primary, ...c, confidence: Number(c.confidence) || 0 })
    })
  } else {
    for (const sensor of SENSORS) {
      for (const c of crossingEvents(sensor, nowSec, props.horizon, 2)) {
        list.push({ sensor, ...c })
      }
    }
  }
  return list
    .filter((c) => c.kind === 'crit' || (c.confidence || 0) >= WARN_CONFIDENCE_MIN)
    .sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'crit' ? -1 : 1
      return a.h - b.h
    })
    .slice(0, 3)
})

const items = computed(() =>
  candidates.value.map((c) => ({
    key: `${c.sensor.key}-${c.kind}-${c.h}`,
    sensorKey: c.sensor.key,
    sensorCn: c.sensor.cn,
    sensorEn: c.sensor.en,
    kind: c.kind,
    h: c.h,
    confidence: c.confidence,
    action: actionFor(c.sensor.key)
  }))
)

async function generate(item) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  copyHint.value = ''
  try {
    const res = await createForecastContractDraft({
      sensor: item.sensorKey,
      kind: item.kind,
      horizonSec: item.h,
      confidence: Number(item.confidence.toFixed(2))
    })
    draft.value = res?.data?.data ?? res?.data ?? null
    if (!draft.value?.draft) {
      error.value = '后端返回了空草案，请稍后重试'
      draft.value = null
    }
  } catch (e) {
    // 如实展示失败，不编造草案——与平台"不修饰结论"原则一致
    error.value = e?.response?.data?.message || e?.message || '草案生成失败，请检查后端服务'
  } finally {
    busy.value = false
  }
}

async function copyDraft() {
  if (!draftJson.value) return
  try {
    await navigator.clipboard.writeText(draftJson.value)
    copyHint.value = '已复制，粘贴给 Agent 运行手册签发'
  } catch {
    copyHint.value = '复制失败：请展开 JSON 手动复制'
  }
}
</script>

<style scoped>
.fc-preventive {
  display: grid;
  gap: 1px;
  background: var(--forecast-line, rgba(255, 255, 255, .06));
}

.fc-preventive__item {
  display: grid;
  gap: 6px;
  padding: 11px 15px;
  background: var(--forecast-card, #151A21);
}

.fc-preventive__item--crit {
  box-shadow: inset 2px 0 0 var(--forecast-bad, #F85149);
}

.fc-preventive__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 0;
}

.fc-preventive__head b {
  font-size: 12px;
  font-weight: 500;
  color: var(--forecast-text, #E8F2F7);
}

.fc-preventive__when {
  color: var(--forecast-warn, #D29922);
  font: 10px var(--forecast-font-mono);
  font-weight: 500;
}

.fc-preventive__when--crit {
  color: var(--forecast-bad, #F85149);
}

.fc-preventive__action {
  color: var(--forecast-muted, #92A6B5);
  font-size: 11px;
  line-height: 1.6;
}

.fc-preventive__row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fc-preventive__row button {
  padding: 4px 10px;
  font-size: 11px;
  color: var(--forecast-text, #E8F2F7);
  background: var(--forecast-overlay, #1B212A);
  border: 1px solid var(--forecast-line, rgba(255, 255, 255, .12));
  border-radius: 4px;
  cursor: pointer;
}

.fc-preventive__row button:disabled {
  opacity: .55;
  cursor: not-allowed;
}

.fc-preventive__error {
  color: var(--forecast-bad, #F85149);
  font-size: 11px;
}

.fc-preventive__hint {
  color: var(--forecast-muted, #92A6B5);
  font-size: 10.5px;
}

.fc-preventive__draft {
  display: grid;
  gap: 6px;
  padding: 8px 10px;
  background: var(--forecast-overlay, #1B212A);
  border-radius: 4px;
}

.fc-preventive__summary {
  margin: 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--forecast-text, #E8F2F7);
}

.fc-preventive__json summary {
  font-size: 11px;
  color: var(--forecast-muted, #92A6B5);
  cursor: pointer;
}

.fc-preventive__json pre {
  margin: 6px 0 0;
  padding: 8px;
  max-height: 220px;
  overflow: auto;
  font: 10px var(--forecast-font-mono);
  color: var(--forecast-text, #E8F2F7);
  background: rgba(0, 0, 0, .25);
  border-radius: 4px;
}

.fc-preventive__empty {
  padding: 16px 15px;
  margin: 0;
  color: var(--forecast-muted, #92A6B5);
  font-size: 12px;
  line-height: 1.7;
  background: var(--forecast-card, #151A21);
}
</style>
