<template>
  <AgentSkillGuidance />
  <div class="page">
    <header>
      <div><p class="eyebrow">AI Agent</p><h1>Agent Command Center</h1><p>基于已持久化的真实 Inspector Event 展示任务状态</p></div>
      <button type="button" :disabled="loading" :aria-busy="loading" @click="load">{{ loading ? '刷新中…' : '刷新' }}</button>
    </header>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <template v-if="current.id">
      <div class="cards">
        <article v-for="item in fields" :key="item.label"><span>{{ item.label }}</span><strong v-if="!item.decode">{{ item.value }}</strong><DecodeText v-else :value="item.value" tag="strong" /></article>
      </div>
      <section>
        <div class="section-title"><h2>Execution Lifecycle</h2><button @click="openTrace">查看完整轨迹</button></div>
        <div class="flow"><span v-for="step in steps" :key="step.name" :class="{active:step.active}">{{ step.name }}</span></div>
      </section>
      <section><h2>Recent Tasks</h2><button v-for="event in events" :key="event.id" class="task" @click="select(event)"><span>{{ event.taskId }}</span><span>{{ event.status }}</span><strong>{{ event.severity }}</strong></button></section>
    </template>
    <AppEmpty v-else-if="!loading" description="暂无真实 Agent / Inspector 任务" />
  </div>
    <section class="virtual-agent"><div class="virtual-label">PREVIEW DATA · VIRTUAL</div><h2>演示任务队列</h2><div class="virtual-task" v-for="task in virtualTasks" :key="task.name"><span class="task-state" :class="task.state"></span><div><strong>{{ task.name }}</strong><small>{{ task.detail }}</small></div><b>{{ task.status }}</b></div></section>
</template>
<script setup>
import AgentSkillGuidance from '../../components/agent/AgentSkillGuidance.vue'
import DecodeText from '../../components/common/DecodeText.vue'
import{computed,onMounted,ref}from'vue';import{useRouter}from'vue-router';import{getInspectorEvent,getInspectorEvents}from'../../api/inspector';import AppEmpty from'../../components/common/AppEmpty.vue';
const router=useRouter(),events=ref([]),current=ref({}),loading=ref(true),error=ref('');const virtualTasks=[{name:'Nginx 502 evidence check',detail:'Read-only · evidence collection',status:'QUEUED',state:'queued'},{name:'Model contract preflight',detail:'Structured output · tool calling',status:'READY',state:'ready'},{name:'Database pool inspection',detail:'Verification checkpoint',status:'VERIFY',state:'verify'}];
const fields=computed(()=>[{label:'Task',value:current.value.taskId||'N/A',decode:true},{label:'Target',value:current.value.target||'N/A'},{label:'Model',value:current.value.metadata?.model||'N/A'},{label:'Skill',value:current.value.metadata?.skill||'N/A'},{label:'Tool',value:current.value.metadata?.tool||'N/A'},{label:'Risk',value:current.value.severity||'N/A'},{label:'Phase',value:current.value.status||'N/A'}]);
const lifecycle=['UNDERSTAND','RETRIEVE','EVIDENCE','PLAN','RISK','APPROVAL','EXECUTE','VERIFY','INSPECT'];const steps=computed(()=>lifecycle.map((name,index)=>({name,active:index<=phaseIndex.value})));const phaseIndex=computed(()=>current.value.id?8:-1);
async function load(){loading.value=true;error.value='';try{const r=await getInspectorEvents(20);events.value=r.data||[];if(events.value.length)await select(events.value[0]);else current.value={}}catch(e){error.value=e.message||'任务服务不可用'}finally{loading.value=false}}
async function select(event){try{const r=await getInspectorEvent(event.id);current.value=r.data||{}}catch(e){error.value=e.message}}
function openTrace(){router.push({path:'/agent/trace',query:{inspectionId:current.value.id}})}onMounted(load)
</script>
<style scoped>.page{display:grid;gap:20px}header,.section-title{display:flex;justify-content:space-between;align-items:flex-start}.eyebrow{color:var(--smart-primary);font-weight:700}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.cards article,section{padding:18px;background:var(--smart-surface);color:var(--smart-text);border:1px solid var(--smart-border);border-radius:12px}.cards span,.cards strong{display:block}.cards span{color:var(--smart-muted)}.cards strong{margin-top:8px;font-size:18px;overflow-wrap:anywhere}.flow{display:flex;gap:8px;overflow:auto}.flow span{padding:10px;background:var(--smart-primary-soft);color:var(--smart-muted);border-radius:8px;font-size:12px}.flow .active{background:var(--smart-primary-soft);color:var(--smart-primary-strong)}.task{width:100%;display:grid;grid-template-columns:1fr 120px 100px;text-align:left;padding:12px;border:0;border-top:1px solid var(--smart-border);background:var(--smart-surface);color:var(--smart-text);cursor:pointer}button{min-height:40px;flex-shrink:0;padding:8px 12px;border:1px solid var(--smart-border);background:var(--smart-surface);color:var(--smart-text);border-radius:8px;cursor:pointer}button:hover:not(:disabled){border-color:var(--smart-primary-strong)}button:disabled{cursor:wait}header{gap:16px;flex-wrap:wrap}@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}}
 .virtual-agent{padding:18px;background:linear-gradient(145deg,#172b4d,#0d1a2d);border:1px solid rgba(108,164,225,.25);border-radius:8px}.virtual-agent h2{margin:4px 0 14px}.virtual-label{color:#e7c56d;font-size:10px;letter-spacing:.15em}.virtual-task{display:grid;grid-template-columns:10px 1fr auto;gap:12px;align-items:center;padding:12px 0;border-top:1px solid var(--smart-border)}.virtual-task div{display:grid;gap:3px}.virtual-task small{color:var(--smart-muted)}.task-state{width:7px;height:7px;border-radius:50%;background:#82dce8}.task-state.ready{background:#72d6b0}.task-state.verify{background:#e7c56d}
</style>
