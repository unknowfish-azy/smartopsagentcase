<template>
  <div class="rewb-page">
    <header class="rewb-head">
      <p class="rewb-eyebrow">RE WORKBENCH / 逆向研究工作台</p>
      <h1>本地逆向研究工作台</h1>
      <p class="rewb-lede">
        把「15 套开源工具」的策展清单按<strong>逆向研究流水线</strong>组织：侦察识别 → 静态分析 → 动态调试 →
        网络观测 → 记忆/移动 → 证据沉淀。按目标类型看推荐管线，或按阶段浏览全部工具。
        诚实声明：本清单<strong>基于参考内容标题语义与公开常识策展，未与原文逐条核对</strong>；
        链接全部指向官方仓库，本页只做导览，不打包、不执行任何工具。
      </p>
    </header>

    <section class="rewb-panel" aria-label="目标类型管线">
      <div class="rewb-panel__head">
        <h2>按目标选管线</h2>
        <span class="rewb-muted">选定目标类型，流水线上的推荐工具依次点亮</span>
      </div>
      <div class="rewb-targets" role="tablist">
        <button
          v-for="target in targets"
          :key="target.id"
          type="button"
          role="tab"
          class="rewb-target"
          :class="{ 'rewb-target--on': selectedTarget === target.id }"
          :aria-selected="selectedTarget === target.id"
          @click="selectedTarget = selectedTarget === target.id ? null : target.id"
        >
          <strong>{{ target.label }}</strong>
          <small>{{ target.cn }}</small>
        </button>
      </div>

      <!-- REA 辐射图：流线绑定真实管线命中（activeIds），未选目标时全部静默 -->
      <ReWorkbenchRadiation
        :tools="tools"
        :stages="stages"
        :active-ids="pipelineIds"
        :active-order="activeTarget?.pipeline ?? []"
        :active-label="activeTarget?.label ?? ''"
      />

      <div v-if="activeTarget" class="rewb-pipeline">
        <p class="rewb-note">{{ activeTarget.note }}</p>
        <div class="rewb-flow">
          <template v-for="(group, gi) in pipelineGroups" :key="group.stage">
            <span v-if="gi > 0" class="rewb-arrow" aria-hidden="true">→</span>
            <span class="rewb-flow-group">
              <span class="rewb-stage-tag" :class="`rewb-stage-tag--${group.stage}`">{{ stageCn(group.stage) }}</span>
              <code v-for="tool in group.tools" :key="tool.id" class="rewb-flow-tool" :title="tool.blurb">{{ tool.name }}</code>
            </span>
          </template>
        </div>
      </div>
      <p v-else class="rewb-muted rewb-hint">点击上方目标类型查看推荐管线；再点一次收起。</p>
    </section>

    <section aria-label="工具目录">
      <div class="rewb-panel__head rewb-catalog-head">
        <h2>工具目录 · {{ tools.length }} 套</h2>
        <span class="rewb-muted">全部为开源项目，链接指向官方仓库</span>
      </div>
      <section v-for="group in catalog" :key="group.stage.id" class="rewb-stage-block">
        <header class="rewb-stage-head">
          <strong>{{ group.stage.cn }}</strong>
          <span class="rewb-stage-en">{{ group.stage.label }}</span>
          <span class="rewb-muted">{{ group.stage.hint }}</span>
        </header>
        <div class="rewb-grid">
          <article
            v-for="tool in group.tools"
            :key="tool.id"
            class="rewb-card"
            :class="{ 'rewb-card--dim': selectedTarget && !inPipeline(tool.id) }"
          >
            <div class="rewb-card__head">
              <strong>{{ tool.name }}</strong>
              <a class="rewb-repo" :href="tool.repo" target="_blank" rel="noopener noreferrer">仓库 ↗</a>
            </div>
            <p class="rewb-card__blurb">{{ tool.blurb }}</p>
            <p class="rewb-card__use"><span>何时用</span>{{ tool.useWhen }}</p>
          </article>
        </div>
      </section>
    </section>

    <footer class="rewb-foot">
      策展快照：15 套工具 · 6 个阶段 · 5 类目标管线，来源为参考内容标题语义与公开常识（未逐条核对原文）。
      深度逆向任务可在本工作区配合 <strong>REA（reverse-engineer-anything）技能</strong>执行——本页是地图，REA 是向导。
    </footer>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import ReWorkbenchRadiation from '../../components/research/ReWorkbenchRadiation.vue'
import {
  RE_STAGES,
  RE_TARGETS,
  RE_TOOLS,
  pipelineForTarget,
  toolsByStage
} from '../../domain/research/reWorkbenchCatalog.js'

const targets = RE_TARGETS
const tools = RE_TOOLS
const stages = RE_STAGES
const catalog = toolsByStage()

const selectedTarget = ref(null)
const activeTarget = computed(() => targets.find(target => target.id === selectedTarget.value) ?? null)
const pipelineGroups = computed(() => pipelineForTarget(selectedTarget.value))
const pipelineIds = computed(() => new Set(activeTarget.value?.pipeline ?? []))
const inPipeline = toolId => pipelineIds.value.has(toolId)

const stageCn = id => RE_STAGES.find(stage => stage.id === id)?.cn ?? id
</script>

<style scoped>
.rewb-page { display: grid; gap: 16px; color: var(--smart-text, #1f2937); padding-bottom: 32px; }
.rewb-eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--smart-primary-strong, #2563eb); }
.rewb-head h1 { margin: 0 0 8px; font-size: 22px; }
.rewb-lede { margin: 0; max-width: 900px; font-size: 13.5px; line-height: 1.8; color: var(--smart-muted, #6b7280); }
.rewb-muted { color: var(--smart-muted, #6b7280); font-size: 12.5px; }

.rewb-panel { border: 1px solid var(--smart-border, #e5e7eb); border-radius: 12px; background: var(--smart-surface, #fff); padding: 14px 16px; display: grid; gap: 10px; }
.rewb-panel__head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.rewb-panel__head h2, .rewb-catalog-head h2 { margin: 0; font-size: 15px; }

.rewb-targets { display: flex; gap: 8px; flex-wrap: wrap; }
.rewb-target { display: grid; gap: 2px; padding: 8px 14px; border: 1px solid var(--smart-border, #e5e7eb); border-radius: 10px; background: none; cursor: pointer; text-align: left; color: inherit; }
.rewb-target strong { font-size: 13.5px; }
.rewb-target small { font-size: 11px; color: var(--smart-muted, #6b7280); }
.rewb-target--on { border-color: var(--smart-primary-strong, #2563eb); background: rgba(37, 99, 235, .07); }
.rewb-target:focus-visible { outline: 2px solid var(--smart-primary-strong, #2563eb); outline-offset: 2px; }

.rewb-pipeline { display: grid; gap: 10px; }
.rewb-note { margin: 0; font-size: 13px; line-height: 1.7; }
.rewb-flow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rewb-flow-group { display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.rewb-arrow { color: var(--smart-muted, #6b7280); }
.rewb-stage-tag { font: 700 10px var(--font-mono, Consolas, monospace); letter-spacing: .06em; color: var(--smart-primary-strong, #2563eb); background: rgba(37, 99, 235, .08); padding: 2px 8px; border-radius: 999px; }
.rewb-flow-tool { font: 12px var(--font-mono, Consolas, monospace); border: 1px solid var(--smart-border, #e5e7eb); border-radius: 6px; padding: 3px 8px; background: var(--smart-surface, #fff); }
.rewb-hint { margin: 0; }

.rewb-catalog-head { margin-bottom: 2px; }
.rewb-stage-block { margin-bottom: 14px; }
.rewb-stage-head { display: flex; align-items: baseline; gap: 10px; margin: 0 2px 8px; }
.rewb-stage-head strong { font-size: 14px; }
.rewb-stage-en { font: 700 10.5px var(--font-mono, Consolas, monospace); letter-spacing: .08em; color: var(--smart-primary-strong, #2563eb); }

.rewb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.rewb-card { border: 1px solid var(--smart-border, #e5e7eb); border-radius: 12px; background: var(--smart-surface, #fff); padding: 12px 14px; display: grid; gap: 8px; align-content: start; transition: border-color .2s ease, background-color .2s ease; }
/* 未命中工具：用虚线边框 + 透明背景弱化，不再用 opacity。
   opacity:.45 会把标题/仓库链接一起压到 4.5:1 以下（axe 50 处 color-contrast serious）。
   弱化的是「卡片是否属于当前管线」这一视觉线索，不是文字本身的可读性。 */
.rewb-card--dim { border-style: dashed; border-color: var(--smart-border, #e5e7eb); background: transparent; }
.rewb-card__head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.rewb-card__head strong { font-size: 14px; }
.rewb-repo { font-size: 12px; color: var(--smart-primary-strong, #2563eb); text-decoration: none; white-space: nowrap; }
.rewb-repo:hover { text-decoration: underline; }
.rewb-card__blurb { margin: 0; font-size: 12.5px; line-height: 1.7; }
.rewb-card__use { margin: 0; font-size: 12px; line-height: 1.7; color: var(--smart-muted, #6b7280); }
.rewb-card__use span { display: inline-block; margin-right: 6px; font: 700 10px var(--font-mono, Consolas, monospace); letter-spacing: .06em; color: var(--smart-primary-strong, #2563eb); }

.rewb-foot { border-top: 1px solid var(--smart-border, #e5e7eb); padding-top: 12px; font-size: 12px; color: var(--smart-muted, #6b7280); line-height: 1.8; }

@media (prefers-reduced-motion: reduce) {
  .rewb-card { transition: none; }
}
</style>
