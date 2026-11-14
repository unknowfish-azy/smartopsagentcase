<template>
  <section class="hc-card hc-policy" aria-labelledby="hc-policy-title">
    <header class="hc-card-head">
      <h2 id="hc-policy-title">探测能力边界</h2>
      <span class="hc-overline">POLICY</span>
    </header>

    <dl class="hc-policy-kv">
      <dt>并发</dt>
      <dd>{{ policy.perUserConcurrency }} <small>（全局 {{ policy.globalConcurrency }}）</small></dd>

      <dt>超时</dt>
      <dd>连接 {{ connectSec }}s / 读取 {{ readSec }}s</dd>

      <dt>响应上限</dt>
      <dd>{{ responseKb }} KB</dd>

      <dt>授权目标</dt>
      <dd>{{ policy.targetCount }} 个</dd>
    </dl>

    <div class="hc-policy-flags">
      <span
        v-for="flag in configFlags"
        :key="flag.label"
        class="hc-flag"
        :class="{ 'hc-flag--on': flag.on }"
      >
        {{ flag.on ? '●' : '○' }} {{ flag.label }}{{ flag.on ? ' 已配置' : ' 未配置' }}
      </span>
    </div>

    <p class="hc-policy-note">
      每次探测受上面的限额约束；超时或权限不足会显示在结果里，
      <b style="color: var(--ds-color-text)">不代表目标服务不健康</b>。
    </p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  policy: { type: Object, default: null }
})

const connectSec = computed(() =>
  props.policy ? (props.policy.connectTimeoutMs / 1000) : 0
)
const readSec = computed(() =>
  props.policy ? (props.policy.readTimeoutMs / 1000) : 0
)
const responseKb = computed(() =>
  props.policy ? Math.round(props.policy.maxResponseBytes / 1024) : 0
)

const configFlags = computed(() => [
  { label: 'Mini 运行时', on: Boolean(props.policy?.miniConfigured) },
  { label: '观测数据源', on: Boolean(props.policy?.observabilityConfigured) },
  { label: 'Harbor',      on: Boolean(props.policy?.harborConfigured) }
])
</script>

<style scoped>
.hc-policy { margin-top: 14px; }
.hc-policy-kv {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 9px 12px;
  padding: 14px 16px;
  margin: 0;
  font-size: 12.5px;
}
.hc-policy-kv dt {
  color: var(--ds-semantic-neutral);
  white-space: nowrap;
}
.hc-policy-kv dd {
  margin: 0;
  color: var(--ds-color-text);
  font-variant-numeric: tabular-nums;
}
.hc-policy-kv dd small { color: var(--ds-semantic-neutral); }

.hc-policy-flags {
  display: flex; gap: 6px; flex-wrap: wrap;
  padding: 0 16px 14px;
}
.hc-flag {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 8px;
  border-radius: var(--ds-radius-pill);
  font-size: 11px;
  border: 1px solid var(--ds-hairline);
  color: var(--ds-color-muted);
  transition: border-color var(--ds-duration-micro) var(--ds-ease-out),
              background var(--ds-duration-micro) var(--ds-ease-out),
              color var(--ds-duration-micro) var(--ds-ease-out);
}
.hc-flag--on {
  border-color: color-mix(in srgb, var(--ds-semantic-success) 38%, transparent);
  background: var(--ds-pill-success-bg);
  color: var(--ds-semantic-success);
}

.hc-policy-note {
  padding: 0 16px 14px;
  margin: 0;
  color: var(--ds-semantic-neutral);
  font-size: 11.5px;
  line-height: 1.55;
}
</style>
