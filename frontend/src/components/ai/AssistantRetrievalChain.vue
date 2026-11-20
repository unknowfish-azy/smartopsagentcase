<template>
  <div v-if="visible" class="retrieval-chain" role="group" aria-label="检索链">
    <span class="retrieval-chain__sweep" aria-hidden="true" />
    <p class="retrieval-chain__title">
      <span class="retrieval-chain__dot" aria-hidden="true" />
      检索链
      <span class="retrieval-chain__hint">{{ hintText }}</span>
    </p>
    <ol class="retrieval-chain__track">
      <template v-for="(stage, index) in stages" :key="stage.key">
        <li class="retrieval-chain__node" :style="{ '--chain-delay': `${index * 0.16}s` }">
          <span class="retrieval-chain__label">{{ stage.label }}</span>
          <span class="retrieval-chain__value">{{ displayValues[stage.key] ?? stage.value }}</span>
          <span class="retrieval-chain__note">{{ stage.note }}</span>
        </li>
        <li
          v-if="index < stages.length - 1"
          class="retrieval-chain__link"
          :style="{ '--spark-delay': `${index * 0.3}s` }"
          aria-hidden="true"
        >
          <i class="retrieval-chain__spark" />
        </li>
      </template>
    </ol>
    <div v-if="coveragePercent !== null" class="retrieval-chain__meter">
      <span class="retrieval-chain__meter-label">词项覆盖</span>
      <span class="retrieval-chain__meter-track">
        <span class="retrieval-chain__meter-fill" :style="{ '--coverage': `${coveragePercent}%` }" />
      </span>
      <span class="retrieval-chain__meter-value">{{ coveragePercent }}%</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  // 通用聊天面板传入整条消息，组件从 metadata 推断链路。
  message: { type: Object, default: null },
  // 本地 Mini 助手没有 attention 统计，直接传入基于真实引用构造的阶段。
  stages: { type: Array, default: null },
  hint: { type: String, default: '' }
})

const attention = computed(() => props.message?.metadata?.attention || null)
const budget = computed(() => props.message?.metadata?.context_budget || null)

// 外部阶段优先；否则只有真实带有重排统计的消息才展示，老消息保持隐藏。
const visible = computed(() => (
  Array.isArray(props.stages) && props.stages.length > 0
) || Boolean(attention.value && Number(attention.value.candidates) > 0))

const coveragePercent = computed(() => {
  const value = Number(attention.value?.avg_coverage)
  return Number.isFinite(value) ? Math.round(value * 100) : null
})

const hintText = computed(() => {
  if (props.hint) return props.hint
  return attention.value?.reranked ? '语义头 + 词项头' : '仅语义头'
})

const stages = computed(() => {
  if (Array.isArray(props.stages) && props.stages.length) return props.stages
  const att = attention.value || {}
  const bud = budget.value || {}
  const list = [
    { key: 'recall', label: '召回', value: `${Number(att.candidates) || 0} 条`, note: '知识服务返回' },
    { key: 'dedupe', label: '去冗余', value: `${Number(att.dropped_duplicates) || 0} 条`, note: '近似重复剔除' },
    {
      key: 'rerank',
      label: '重排',
      value: att.reranked ? '双头加权' : '按分数',
      note: `覆盖 ${coveragePercent.value === null ? '—' : `${coveragePercent.value}%`}`
    }
  ]
  if (bud.kept !== undefined || bud.used_chars !== undefined) {
    const used = Number(bud.used_chars)
    const total = Number(bud.budget_chars)
    list.push({
      key: 'budget',
      label: '预算装填',
      value: `${Number(bud.kept) || 0} 条`,
      note: Number.isFinite(used) && Number.isFinite(total) && total > 0
        ? `${used} / ${total} 字符`
        : '已按预算裁剪'
    })
  }
  return list
})

/* ---------------- 数字滚动：从 0 计数到真实值 ---------------- */
const displayValues = ref({})
let rafId = 0

function parseValue(value) {
  const match = String(value ?? '').match(/^(\d+(?:\.\d+)?)(.*)$/)
  if (!match) return null
  const decimals = match[1].includes('.') ? match[1].split('.')[1].length : 0
  return { number: Number(match[1]), suffix: match[2], decimals }
}

function stopAnimation() {
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = 0
  }
}

function playCountUp() {
  stopAnimation()
  const jobs = stages.value
    .map((stage, index) => ({ key: stage.key, raw: stage.value, parsed: parseValue(stage.value), index }))
    .filter(job => job.parsed)
  if (!jobs.length) return

  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduced) {
    displayValues.value = Object.fromEntries(jobs.map(job => [job.key, job.raw]))
    return
  }

  const startedAt = performance.now()
  const step = (now) => {
    const next = { ...displayValues.value }
    let running = false
    jobs.forEach((job) => {
      const local = Math.min(Math.max((now - startedAt - job.index * 110) / 680, 0), 1)
      const eased = 1 - (1 - local) ** 3
      next[job.key] = `${(job.parsed.number * eased).toFixed(job.parsed.decimals)}${job.parsed.suffix}`
      if (local < 1) running = true
    })
    displayValues.value = next
    rafId = running ? requestAnimationFrame(step) : 0
  }
  rafId = requestAnimationFrame(step)
}

onMounted(playCountUp)
onBeforeUnmount(stopAnimation)
</script>

<style scoped>
.retrieval-chain {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  margin: 6px 0 8px;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 22%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--smart-primary-strong) 6%, transparent);
  font-size: 10px;
  line-height: 1.5;
  color: var(--smart-muted);
}

/* 背景数据网格：极低透明度缓慢流动，制造「正在计算」的底噪 */
.retrieval-chain::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background-image:
    linear-gradient(color-mix(in srgb, var(--smart-primary-strong) 10%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in srgb, var(--smart-primary-strong) 10%, transparent) 1px, transparent 1px);
  background-size: 14px 14px;
  opacity: 0.35;
  animation: chain-grid 9s linear infinite;
}

/* 周期性扫过整条链路的高光，暗示数据在被读取 */
.retrieval-chain__sweep {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -45%;
  width: 42%;
  pointer-events: none;
  background: linear-gradient(
    100deg,
    transparent 0%,
    color-mix(in srgb, var(--smart-primary-strong) 16%, transparent) 50%,
    transparent 100%
  );
  transform: skewX(-12deg);
  animation: chain-sweep 4.8s ease-in-out infinite;
}

.retrieval-chain__title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 7px;
  font-weight: 600;
  color: var(--smart-primary-strong);
}

.retrieval-chain__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--smart-primary-strong) 55%, transparent);
  animation: chain-pulse 1.8s ease-out infinite;
}

.retrieval-chain__hint {
  margin-left: auto;
  font-weight: 400;
  color: var(--smart-muted);
}

.retrieval-chain__track {
  display: flex;
  align-items: stretch;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-x: auto;
}

.retrieval-chain__node {
  flex: 1 1 0;
  min-width: 62px;
  padding: 5px 6px;
  border-radius: 7px;
  border: 1px solid color-mix(in srgb, var(--smart-primary-strong) 20%, transparent);
  background: color-mix(in srgb, var(--smart-primary-strong) 8%, transparent);
  text-align: center;
  animation: chain-rise 0.5s ease-out both;
  animation-delay: var(--chain-delay, 0s);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.retrieval-chain__node:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--smart-primary-strong) 45%, transparent);
  box-shadow: 0 0 10px color-mix(in srgb, var(--smart-primary-strong) 18%, transparent);
}

.retrieval-chain__label { display: block; font-weight: 600; color: var(--smart-primary-strong); }
.retrieval-chain__value { display: block; font: 11px/1.4 var(--font-mono); color: var(--smart-text, inherit); }
.retrieval-chain__note { display: block; opacity: 0.75; }

/* 连接线：光带沿水平方向流动，示意证据在链路中推进 */
.retrieval-chain__link {
  position: relative;
  flex: 0 0 14px;
  align-self: center;
  height: 2px;
  border-radius: 1px;
  background-image: linear-gradient(90deg,
    color-mix(in srgb, var(--smart-primary-strong) 15%, transparent) 0%,
    var(--smart-primary-strong) 50%,
    color-mix(in srgb, var(--smart-primary-strong) 15%, transparent) 100%);
  background-size: 220% 100%;
  animation: chain-flow 1.6s linear infinite;
}

/* 穿梭光点：从上一节点飞向下一节点 */
.retrieval-chain__spark {
  position: absolute;
  top: 50%;
  left: 0;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--smart-primary-strong);
  box-shadow: 0 0 6px color-mix(in srgb, var(--smart-primary-strong) 75%, transparent);
  transform: translate(0, -50%);
  opacity: 0;
  animation: chain-spark 1.9s linear infinite;
  animation-delay: var(--spark-delay, 0s);
}

.retrieval-chain__meter {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 7px;
}

.retrieval-chain__meter-track {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--smart-primary-strong) 14%, transparent);
  overflow: hidden;
}

.retrieval-chain__meter-fill {
  display: block;
  height: 100%;
  width: var(--coverage, 0%);
  border-radius: 2px;
  background: linear-gradient(90deg,
    color-mix(in srgb, var(--smart-primary-strong) 70%, transparent),
    var(--smart-primary-strong));
  background-size: 200% 100%;
  transform-origin: left center;
  animation:
    chain-grow 0.9s cubic-bezier(0.22, 1, 0.36, 1) both,
    chain-meter-shine 2.6s linear 0.9s infinite;
}

.retrieval-chain__meter-value { font-family: var(--font-mono); color: var(--smart-primary-strong); }

@keyframes chain-pulse {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--smart-primary-strong) 55%, transparent); }
  70%, 100% { box-shadow: 0 0 0 6px transparent; }
}

@keyframes chain-flow {
  from { background-position: 180% 0; }
  to { background-position: -80% 0; }
}

@keyframes chain-spark {
  0% { opacity: 0; transform: translate(0, -50%); }
  18% { opacity: 1; }
  82% { opacity: 1; }
  100% { opacity: 0; transform: translate(11px, -50%); }
}

@keyframes chain-grid {
  from { background-position: 0 0, 0 0; }
  to { background-position: 14px 14px, 14px 14px; }
}

@keyframes chain-sweep {
  0% { left: -45%; opacity: 0; }
  12% { opacity: 1; }
  88% { opacity: 1; }
  100% { left: 105%; opacity: 0; }
}

@keyframes chain-meter-shine {
  from { background-position: 200% 0; }
  to { background-position: -100% 0; }
}

@keyframes chain-rise {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes chain-grow {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}

@media (prefers-reduced-motion: reduce) {
  .retrieval-chain::before,
  .retrieval-chain__sweep,
  .retrieval-chain__spark,
  .retrieval-chain__dot,
  .retrieval-chain__node,
  .retrieval-chain__link,
  .retrieval-chain__meter-fill { animation: none; }
  .retrieval-chain__node { transition: none; }
  .retrieval-chain__node:hover { transform: none; }
}
</style>
