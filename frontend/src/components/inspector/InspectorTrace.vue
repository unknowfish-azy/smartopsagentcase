<template>
  <div class="trace">
    <div v-for="step in steps" :key="step.name" :class="{active:step.active,error:step.error}">
      <b>{{ step.name }}</b>
      <span>{{ step.value }}</span>
    </div>
  </div>
</template>

<script setup>
import {computed} from 'vue'; const props=defineProps({event:{type:Object,default:()=>({})}})
const steps=computed(()=>[['User Request',props.event.metadata?.userRequest],['Agent Plan',props.event.metadata?.reasoningSummary],['Skill',props.event.metadata?.skill],['Tool',props.event.metadata?.tool],['Evidence',props.event.evidence?.length?`${props.event.evidence.length} item(s)`:null],['Risk',props.event.severity],['Approval',props.event.metadata?.approval],['Execution',props.event.metadata?.execution],['Verification',props.event.verification?.status],['Inspector',props.event.status]].map(([name,value])=>({name,value:value||'N/A',active:Boolean(value),error:['VIOLATION','REJECTED','CRITICAL'].includes(value)})))
</script>

<style scoped>
/* 执行管线：10 个步骤是一条有方向的讯息流（User Request → Inspector），
   步骤间用 Chevron 标明流向；填充过的步骤 Chevron 点亮，读出"走到哪儿了"。 */
.trace{display:grid;grid-template-columns:repeat(10,minmax(100px,1fr));overflow:auto;gap:16px}
.trace div{position:relative;padding:12px;background:var(--smart-bg);border:1px solid var(--smart-border);border-radius:6px}
.trace div:not(:last-child)::after{content:'›';position:absolute;top:50%;right:-11px;transform:translateY(-50%);color:var(--smart-border-strong);font:13px var(--font-mono);line-height:1;pointer-events:none}
.trace div.active:not(:last-child)::after{color:var(--smart-primary-strong)}
.trace b,.trace span{display:block}
.trace b{font:10px var(--font-mono);letter-spacing:.08em;text-transform:uppercase;color:var(--smart-muted)}
.trace span{margin-top:6px;font-size:12px;color:var(--smart-muted);overflow-wrap:anywhere}
.trace div.active{border-top:2px solid var(--smart-primary-strong)}
.trace div.active span{color:var(--smart-text)}
.trace div.error{background:color-mix(in srgb,var(--smart-danger) 12%,var(--smart-surface));border-color:var(--smart-danger)}
</style>
