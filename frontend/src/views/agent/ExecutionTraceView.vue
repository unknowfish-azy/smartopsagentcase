<template>
  <div class="page">
    <header><div><h1>Execution Trace</h1><p>只展示可审计 Reasoning Summary，不展示隐藏 Chain-of-Thought</p></div><RouterLink to="/agent">返回控制中心</RouterLink></header>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <section class="virtual-trace"><div class="virtual-label">PREVIEW DATA · VIRTUAL TRACE</div><h2>演示执行轨迹</h2><div class="trace-steps"><div v-for="step in virtualSteps" :key="step.name" class="trace-step"><span class="trace-index">{{ step.index }}</span><div><strong>{{ step.name }}</strong><small>{{ step.detail }}</small></div><b>{{ step.status }}</b></div></div></section>
    <template v-if="event.id">
      <InspectorTrace :event="event" />
      <section><h2>Reasoning Summary</h2><p>{{ event.metadata?.reasoningSummary || event.reason || 'N/A' }}</p></section>
      <div class="grid">
        <article><span>Tool</span><strong>{{ event.metadata?.tool || 'N/A' }}</strong></article>
        <article><span>Evidence</span><strong>{{ event.evidence?.length ?? 0 }}</strong></article>
        <article><span>Risk</span><strong>{{ event.severity || 'N/A' }}</strong></article>
        <article><span>Approval</span><strong>{{ event.metadata?.approval || 'N/A' }}</strong></article>
        <article><span>Execution</span><strong>{{ event.metadata?.execution || 'N/A' }}</strong></article>
        <article><span>Verification</span><strong>{{ event.verification?.status || 'NOT RUN' }}</strong></article>
        <article><span>Inspector</span><strong>{{ event.status || 'N/A' }}</strong></article>
        <article><span>Human Review</span><strong>{{ event.requiresHuman ? 'REQUIRED' : 'NO' }}</strong></article>
      </div>
      <div class="columns"><section><h2>Evidence</h2><InspectorEvidence :evidence="event.evidence" /></section><section><h2>Issues</h2><InspectorIssueList :issues="event.issues" /></section></div>
    </template>
    <AppEmpty v-else-if="!loading" description="未找到可展示的真实执行轨迹" />
  </div>
</template>
<script setup>
const virtualSteps=[{index:'01',name:'Understand request',detail:'Task intent parsed',status:'DONE'},{index:'02',name:'Collect evidence',detail:'Read-only sources queried',status:'DONE'},{index:'03',name:'Risk gate',detail:'Approval requirement evaluated',status:'CHECK'},{index:'04',name:'Verification',detail:'Awaiting real execution result',status:'NOT RUN'}]
import{onMounted,ref}from'vue';import{useRoute}from'vue-router';import{getInspectorEvent,getInspectorEvents}from'../../api/inspector';import AppEmpty from'../../components/common/AppEmpty.vue';import InspectorTrace from'../../components/inspector/InspectorTrace.vue';import InspectorEvidence from'../../components/inspector/InspectorEvidence.vue';import InspectorIssueList from'../../components/inspector/InspectorIssueList.vue';
const route=useRoute(),event=ref({}),loading=ref(true),error=ref('');onMounted(async()=>{try{let id=route.query.inspectionId;if(!id){const list=await getInspectorEvents(1);id=list.data?.[0]?.id}if(id){const detail=await getInspectorEvent(id);event.value=detail.data||{}}}catch(e){error.value=e.message||'轨迹加载失败'}finally{loading.value=false}})
</script>
<style scoped>.page{display:grid;gap:18px}header{display:flex;justify-content:space-between;align-items:flex-start}header p{color:var(--smart-muted)}section,.grid article{padding:18px;background:white;border:1px solid var(--smart-border);border-radius:12px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.grid span,.grid strong{display:block}.grid strong{margin-top:10px;overflow-wrap:anywhere}.columns{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:800px){.grid{grid-template-columns:repeat(2,1fr)}.columns{grid-template-columns:1fr}}
 .virtual-trace{background:linear-gradient(145deg,#172b4d,#0d1a2d);border-color:rgba(108,164,225,.3);color:var(--smart-text)}.virtual-label{color:#e7c56d;font-size:10px;letter-spacing:.15em}.virtual-trace h2{margin:5px 0 14px}.trace-steps{display:grid;gap:0}.trace-step{display:grid;grid-template-columns:42px 1fr auto;gap:12px;align-items:center;padding:13px 0;border-top:1px solid var(--smart-border)}.trace-index{color:#82dce8;font-size:12px}.trace-step div{display:grid;gap:3px}.trace-step small{color:var(--smart-muted)}.trace-step b{color:#9bd9b3;font-size:11px;letter-spacing:.08em}.trace-step:last-child b{color:#e7c56d}
</style>
