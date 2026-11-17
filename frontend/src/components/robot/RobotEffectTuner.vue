<template>
  <section class="fx-panel" aria-labelledby="fx-tuner-title">
    <header class="fx-head">
      <div class="fx-head-left">
        <h2 id="fx-tuner-title">动效参数</h2>
        <span class="fx-pill" :class="{ 'fx-pill-active': dirtyCount > 0 }">
          {{ dirtyCount > 0 ? `已调整 ${dirtyCount} 项` : '默认参数' }}
        </span>
      </div>
      <div class="fx-actions">
        <button type="button" class="fx-btn" :disabled="dirtyCount === 0" @click="reset">恢复默认</button>
        <button type="button" class="fx-btn" :aria-expanded="open" @click="open = !open">
          {{ open ? '收起' : '展开' }}
        </button>
      </div>
    </header>

    <p class="fx-note">状态灯与 LiDAR 扫描的可视化参数，拖动实时作用于上方 3D 场景；仅四足 / 人形形态生效。</p>

    <div v-show="open" class="fx-grid">
      <label v-for="item in FIELDS" :key="item.key" class="fx-row" :title="item.hint">
        <span class="fx-label">
          {{ item.label }}<em v-if="item.unit">（{{ item.unit }}）</em>
        </span>
        <input
          type="range"
          class="fx-range"
          :min="item.min"
          :max="item.max"
          :step="item.step"
          :value="values[item.key]"
          :aria-label="item.label"
          @input="update(item.key, $event.target.value)"
        />
        <output class="fx-value">{{ values[item.key].toFixed(item.decimals) }}</output>
      </label>
    </div>
  </section>
</template>

<script setup>
/**
 * 3D 机器人动效参数调节面板。
 *
 * 参数定义与校验集中在 rigs/effects.js（DEFAULT_EFFECT_CONFIG / resolveEffectConfig），
 * 本组件只负责渲染滑杆并把完整配置回传给父级；父级持久化后可经 RobotScene3D 的
 * `effects` prop 下发，rig 内部热更新，无需重建几何。
 */
import { computed, ref } from 'vue'
import { DEFAULT_EFFECT_CONFIG, resolveEffectConfig } from './rigs/effects.js'

const props = defineProps({
  modelValue: { type: Object, default: null }
})
const emit = defineEmits(['update:modelValue'])

const open = ref(true)

/** 滑杆元信息：范围与步长按「有效但不极端」的观感区间取；顺序决定双列排布的配对。 */
const FIELDS = [
  { key: 'beaconIdleHz', label: '状态灯呼吸', unit: 'Hz', min: 0, max: 3, step: 0.1, decimals: 1, hint: '常态下状态灯的呼吸频率' },
  { key: 'beaconAlarmHz', label: '告警闪烁', unit: 'Hz', min: 0.5, max: 8, step: 0.5, decimals: 1, hint: '障碍过近时的闪烁频率' },
  { key: 'lidarSpeed', label: 'LiDAR 转速', unit: 'rad/s', min: 0, max: 12, step: 0.5, decimals: 1, hint: '常态下 LiDAR 扫描扇面的旋转速度' },
  { key: 'lidarAlarmSpeed', label: '告警转速', unit: 'rad/s', min: 0, max: 20, step: 0.5, decimals: 1, hint: '告警态下 LiDAR 的旋转速度' },
  { key: 'ringMaxOpacity', label: '扫描环亮度', unit: '', min: 0, max: 1, step: 0.02, decimals: 2, hint: '扫描环刚出现时的不透明度' },
  { key: 'ringStaleOpacity', label: '超时环亮度', unit: '', min: 0, max: 1, step: 0.02, decimals: 2, hint: '心跳超时后扫描环的不透明度' },
  { key: 'scanPeriod', label: '扫描环周期', unit: 's', min: 0.6, max: 6, step: 0.2, decimals: 1, hint: '地面扫描环从内到外扩散一圈的耗时' }
]

const values = computed(() => resolveEffectConfig(props.modelValue))

const dirtyCount = computed(() => FIELDS.filter((item) => values.value[item.key] !== DEFAULT_EFFECT_CONFIG[item.key]).length)

function update(key, raw) {
  emit('update:modelValue', { ...values.value, [key]: Number(raw) })
}

function reset() {
  emit('update:modelValue', { ...DEFAULT_EFFECT_CONFIG })
}
</script>

<style scoped>
.fx-panel {
  padding: var(--ds-card-padding, var(--ds-space-4));
  border: 1px solid var(--ds-color-border);
  border-radius: var(--ds-radius-lg);
  background: var(--ds-color-surface);
}

.fx-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space-2);
}

.fx-head-left {
  display: flex;
  align-items: center;
  gap: var(--ds-space-2);
}

.fx-head h2 {
  margin: 0;
  font-size: var(--ds-font-md);
}

.fx-pill {
  padding: 2px var(--ds-space-2);
  border-radius: var(--ds-radius-pill);
  background: var(--ds-pill-neutral-bg, rgba(159, 190, 207, 0.12));
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  white-space: nowrap;
}

.fx-pill-active {
  background: rgba(36, 150, 237, 0.16);
  color: var(--ds-color-primary);
}

.fx-actions {
  display: flex;
  gap: var(--ds-space-2);
}

.fx-btn {
  height: calc(var(--ds-control-height, 36px) - 8px);
  padding: 0 var(--ds-space-3);
  border: 1px solid var(--ds-color-border-strong);
  border-radius: var(--ds-radius-md);
  background: transparent;
  color: var(--ds-color-text);
  font-size: var(--ds-font-xs);
  cursor: pointer;
}

.fx-btn:hover:not(:disabled) {
  border-color: var(--ds-color-primary);
}

.fx-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.fx-note {
  margin: var(--ds-space-2) 0 0;
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  line-height: var(--ds-line-base);
}

.fx-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--ds-space-2) var(--ds-space-4);
  margin-top: var(--ds-space-3);
}

.fx-row {
  display: grid;
  grid-template-columns: 116px minmax(0, 1fr) 44px;
  align-items: center;
  gap: var(--ds-space-2);
}

.fx-label {
  color: var(--ds-color-muted);
  font-size: var(--ds-font-xs);
  white-space: nowrap;
}

.fx-label em {
  font-style: normal;
  opacity: 0.75;
}

.fx-range {
  width: 100%;
  accent-color: var(--ds-color-primary);
  cursor: pointer;
}

.fx-value {
  font-family: var(--ds-font-mono);
  font-size: var(--ds-font-xs);
  text-align: right;
  color: var(--ds-color-text);
}
</style>
