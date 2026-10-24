<script setup>
import { computed, useId } from 'vue'
import { Cpu, Connection, Plus } from '@element-plus/icons-vue'

const props = defineProps({ connections: { type: Array, default: () => [] }, loading: Boolean, unavailable: Boolean })
const emit = defineEmits(['create', 'select'])
const uid = useId()
const positions = [
  { x: 110, y: 90, path: 'M270 205 V105 Q270 90 255 90 H158' },
  { x: 390, y: 75, path: 'M294 205 V90 Q294 75 309 75 H342' },
  { x: 85, y: 205, path: 'M250 205 H132' },
  { x: 480, y: 205, path: 'M314 205 H433' },
  { x: 180, y: 335, path: 'M270 205 V320 Q270 335 255 335 H228' },
  { x: 430, y: 335, path: 'M314 215 V320 Q314 335 329 335 H382' },
]
const nodes = computed(() => positions.map((position, index) => ({ ...position, connection: props.connections[index], index })))
const enabled = computed(() => props.connections.filter(item => item.enabled).length)
</script>

<template>
  <section class="integration-card" aria-labelledby="integration-title">
    <div class="integration-visual">
      <svg class="integration-lines" viewBox="0 0 564 410" preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient :id="`${uid}-flow`" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="564" y2="410"><stop offset="0" stop-color="var(--smart-primary)" stop-opacity="0" /><stop offset=".5" stop-color="var(--smart-primary-strong)" /><stop offset="1" stop-color="var(--smart-primary)" stop-opacity="0" /></linearGradient><marker :id="`${uid}-arrow`" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="4.5" markerHeight="4.5" orient="auto"><path d="M0 0L8 4L0 8z" fill="var(--smart-primary-strong)"/></marker></defs>
        <g v-for="node in nodes" :key="node.index">
          <path :d="node.path" class="connection-line" />
          <path v-if="node.connection?.enabled" :d="node.path" :stroke="`url(#${uid}-flow)`" class="connection-flow" :marker-end="`url(#${uid}-arrow)`" :style="{ animationDelay: `${node.index * -.55}s` }" />
        </g>
      </svg>
      <div class="integration-hub"><Cpu aria-hidden="true" /><span>SmartOps</span></div>
      <button v-for="node in nodes" :key="node.index" type="button" class="integration-node" :class="{ 'integration-node--connected': node.connection?.enabled }" :style="{ left: `${node.x / 564 * 100}%`, top: `${node.y / 410 * 100}%` }" :aria-label="node.connection ? `配置 ${node.connection.name}` : '添加模型连接'" :title="node.connection?.name || '添加模型连接'" :disabled="loading || unavailable" @click="node.connection ? emit('select', node.connection) : emit('create')">
        <Connection v-if="node.connection" aria-hidden="true" /><Plus v-else aria-hidden="true" />
        <span>{{ node.connection?.provider || '接入模型' }}</span>
      </button>
      <span class="visual-caption">{{ unavailable ? '服务暂不可用' : loading ? '正在读取连接' : `${connections.length} 个连接 · ${enabled} 个启用` }}</span>
    </div>
    <div class="integration-copy">
      <span class="eyebrow">MODEL INTEGRATIONS</span>
      <h2 id="integration-title">连接模型，让运维多一种能力</h2>
      <p>统一管理模型服务和访问凭据，用一次文本测试确认模型是否可用。</p>
      <p class="protocol-note">当前支持兼容 Chat Completions 的接口。连线表示配置已启用，不代表已通过测试。{{ connections.length > 6 ? '图中展示前 6 个连接，完整列表见下方。' : '' }}</p>
      <div class="integration-actions"><button type="button" class="add-button" @click="emit('create')"><Plus aria-hidden="true" />添加模型</button><a href="#model-connections">查看已接入模型 ↓</a></div>
    </div>
  </section>
</template>

<style scoped>
.integration-card{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);overflow:hidden;border:1px solid var(--smart-border);border-radius:18px;background:var(--smart-surface)}
.integration-visual{position:relative;aspect-ratio:564/410;min-width:0;background-image:radial-gradient(circle,var(--smart-border) 1px,transparent 1px);background-size:28px 28px;background-color:var(--smart-surface)}
.integration-lines{position:absolute;inset:0;width:100%;height:100%}.connection-line{stroke:var(--smart-border);stroke-width:1;fill:none}.connection-flow{stroke-width:2;fill:none;stroke-dasharray:40 160;animation:integration-flow 4s linear infinite}
.integration-hub{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:grid;justify-items:center;gap:4px;padding:12px;border:1px solid var(--smart-primary);border-radius:16px;background:var(--smart-surface);color:var(--smart-primary-strong);box-shadow:0 0 36px rgba(122,215,245,.12);font:10px var(--font-mono)}.integration-hub svg{width:30px;height:30px}
.integration-node{position:absolute;transform:translate(-50%,-50%);display:grid;place-items:center;gap:5px;width:76px;min-height:62px;padding:9px 4px;border:1px solid var(--smart-border);border-radius:12px;background:var(--smart-surface);color:var(--smart-muted);cursor:pointer;transition:border-color 150ms,box-shadow 150ms}.integration-node svg{width:22px;height:22px}.integration-node span{max-width:70px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.integration-node--connected{color:var(--smart-primary-strong);border-color:var(--smart-border)}.integration-node:hover{border-color:var(--smart-primary);box-shadow:0 0 18px rgba(122,215,245,.12)}.integration-node:disabled{opacity:.5;cursor:default}.visual-caption{position:absolute;bottom:14px;left:0;right:0;text-align:center;font-size:12px;color:var(--smart-muted)}
.integration-copy{display:flex;flex-direction:column;justify-content:center;padding:clamp(22px,3vw,44px);gap:16px}.eyebrow{font:10px var(--font-mono);letter-spacing:.18em;color:var(--smart-primary-strong)}h2{margin:0;font-size:clamp(24px,2.3vw,34px);line-height:1.35;font-weight:500}p{margin:0;line-height:1.75;color:var(--smart-muted);font-size:14px}.protocol-note{font-size:12px}.integration-actions{display:flex;align-items:center;flex-wrap:wrap;gap:18px;margin-top:6px}.add-button{display:inline-flex;align-items:center;gap:8px;border:0;border-radius:24px;background:var(--smart-primary);color:var(--smart-primary-foreground,#041018);padding:12px 20px;cursor:pointer;font-weight:600}.add-button svg{width:16px;height:16px}a{font-size:13px;color:var(--smart-primary-strong)}button:focus-visible,a:focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:4px}
@keyframes integration-flow{from{stroke-dashoffset:200}to{stroke-dashoffset:-200}}@media(prefers-reduced-motion:reduce){.connection-flow{animation:none}.integration-node{transition:none}}@media(max-width:900px){.integration-card{grid-template-columns:1fr}.integration-visual{max-height:350px;aspect-ratio:auto;height:310px}.integration-copy{padding:24px}}@media(max-width:480px){.integration-visual{height:auto;aspect-ratio:564/410}.integration-node{width:50px;min-height:46px;padding:5px 2px}.integration-node svg{width:18px;height:18px}.integration-node span{max-width:46px;font-size:9px}.integration-hub{padding:8px}.integration-hub svg{width:22px;height:22px}.visual-caption{bottom:5px;font-size:10px}}
</style>
