<template>
  <section class="achievements" :aria-busy="loading">
    <header class="hall-heading">
      <div>
        <p class="eyebrow">MILESTONE HALL / 里程碑战报</p>
        <h1>里程碑战报</h1>
        <p class="intro">每一项里程碑都来自真实调用账本。这里只庆祝已经发生的事实，不展示收益、回撤等无法诚实产出的指标。</p>
      </div>
      <RouterLink class="outline-button" to="/token-usage">查看用量明细 <span aria-hidden="true">↗</span></RouterLink>
    </header>

    <div v-if="error" class="state-panel error-panel" role="alert">
      <h2>暂时无法读取账本</h2>
      <p>{{ error }}</p>
      <button type="button" class="outline-button" :disabled="loading" @click="loadReport()">重新加载</button>
    </div>
    <div v-else-if="loading" class="state-panel" role="status">正在读取 {{ month }} 的调用账本…</div>

    <template v-else-if="report">
      <div class="hall-layout">
        <article class="analytics-panel vessel-panel">
          <p class="eyebrow">THIS MONTH / 本月进度</p>
          <h2>本月调用里程碑</h2>
          <div ref="stage" class="vessel-stage">
            <MilestoneRain :active="raining" mode="funnel" :count="64" :duration="2600" :fill="callProgress.progress" :ambient="ambientOn" @finished="onFinished" />
          </div>
          <p class="vessel-readout">{{ vesselReadout }}</p>
          <div class="vessel-actions">
            <button type="button" class="outline-button" :disabled="raining" @click="celebrateDemo()">演示庆祝动效（不关联真实数据）</button>
            <button
              type="button"
              class="outline-button ambient-toggle"
              :disabled="raining"
              :aria-pressed="ambientOn ? 'true' : 'false'"
              @click="ambientOn = !ambientOn"
            >{{ ambientOn ? '暂停动态演示' : '恢复动态演示' }}</button>
            <p class="rain-status" role="status">{{ statusText || (ambientOn ? '持续动态演示中。' : '动态演示已暂停。') }}</p>
          </div>
          <div class="tier-ladder" aria-label="袋口档位阶梯">
            <p class="eyebrow">MOUTH TIERS / 袋口档位</p>
            <ul>
              <li v-for="tier in callTiers" :key="tier.threshold" :class="{ reached: tier.reached }">
                <span class="tier-label">{{ tier.thresholdText }}</span>
                <span class="tier-track"><i :style="{ width: `${tier.progress * 100}%` }" /></span>
                <span class="tier-state">{{ tier.reached ? '已达成' : tier.progress > 0 ? `${Math.round(tier.progress * 100)}%` : '未达' }}</span>
              </li>
            </ul>
          </div>
          <p class="source-note">按 UTC 自然月统计，含成功、失败与待确认调用。袋中常驻储量按真实进度渲染；庆祝动效为一次性展示，不计入任何账本。</p>
        </article>

        <div class="achievement-list">
          <article v-for="item in achievements" :key="item.id" class="achievement-card" :class="{ unlocked: item.unlocked, next: item.isNext }">
            <header>
              <h3>{{ item.title }}</h3>
              <span class="status-chip" :data-state="item.unlocked ? 'unlocked' : item.isNext ? 'next' : 'locked'">
                {{ item.unlocked ? '已达成' : item.isNext ? '进行中' : '未解锁' }}
              </span>
            </header>
            <p class="value-line"><strong>{{ item.valueText }}</strong><span>目标 {{ item.thresholdText }}</span></p>
            <div
              class="progress-track"
              role="progressbar"
              :aria-valuenow="Math.round(item.progress * 100)"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="`${item.title} 进度`"
            >
              <div class="progress-bar" :style="{ width: `${item.progress * 100}%` }" />
            </div>
            <p class="basis">{{ item.basis }} · 样本区间 {{ item.window }}</p>
            <button v-if="item.unlocked" type="button" class="outline-button celebrate-button" :disabled="raining" @click="celebrate(item)">庆祝一下</button>
          </article>
          <p class="demo-divider">演示实例 · DEMO — 非真实账本数据，仅用于展示卡片状态与滚动效果</p>
          <article v-for="item in demoAchievements" :key="item.id" class="achievement-card demo">
            <header>
              <h3>{{ item.title }}</h3>
              <span class="status-chip" data-state="demo">演示</span>
            </header>
            <p class="value-line"><strong>{{ item.valueText }}</strong><span>目标 {{ item.thresholdText }}</span></p>
            <div
              class="progress-track"
              role="progressbar"
              :aria-valuenow="Math.round(item.progress * 100)"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="`${item.title} 进度（演示）`"
            >
              <div class="progress-bar" :style="{ width: `${item.progress * 100}%` }" />
            </div>
            <p class="basis">{{ item.basis }} · 样本区间 {{ item.window }}</p>
          </article>
        </div>
      </div>

      <footer class="hall-footer">
        <span>来源：SmartOps 调用账本 · {{ report.month }} · {{ report.timezone || 'UTC' }}</span>
        <span>已达成 {{ unlockedCount }} / {{ achievements.length }} 项；动效只作庆祝，不代表任何服务商承诺。另含 {{ demoAchievements.length }} 项演示实例（非真实数据）。</span>
      </footer>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import MilestoneRain from '../../components/effects/MilestoneRain.vue'
import { buildAchievements, CALL_TIERS, DEMO_ACHIEVEMENTS } from '../../components/celebrate/achievements.js'
import { milestoneProgress } from '../../components/effects/milestoneRain.js'
import { getModelAnalytics } from '../../api/modelAnalytics.ts'

const route = useRoute()
const month = ref(new Date().toISOString().slice(0, 7))
const report = ref(null)
const loading = ref(false)
const error = ref('')
const raining = ref(false)
const statusText = ref('')
// 持续动态演示默认开（动态持续化）；?ambient=0 可关；暂停/恢复由「动态演示」键位控制
const ambientOn = ref(route.query.ambient !== '0')
let disposed = false

const unwrap = response => response?.data ?? response

async function loadReport() {
  error.value = ''
  loading.value = true
  try {
    const data = unwrap(await getModelAnalytics(month.value))
    if (disposed) return
    report.value = data
    // ?preview=1：显式预览请求（分享/演示用），有真实达成项才自动播一次
    if (route.query.preview === '1' && buildAchievements(data).some(item => item.unlocked)) celebrateDemo()
  } catch (err) {
    if (!disposed) error.value = err.message || '账本服务暂不可用，请重试。'
  } finally {
    if (!disposed) loading.value = false
  }
}

const achievements = computed(() => buildAchievements(report.value))
const demoAchievements = DEMO_ACHIEVEMENTS
const unlockedCount = computed(() => achievements.value.filter(item => item.unlocked).length)
const callProgress = computed(() => milestoneProgress(report.value?.summary?.calls, CALL_TIERS))
// 袋口档位阶梯：真实 calls 对五档的达成情况（未知不猜：无数据时全部 0% / 未达）
const callTiers = computed(() => CALL_TIERS.map(threshold => {
  const calls = report.value?.summary?.calls
  const value = typeof calls === 'number' && Number.isFinite(calls) && calls >= 0 ? calls : null
  return {
    threshold,
    thresholdText: threshold >= 10000 ? `${threshold / 10000} 万` : threshold.toLocaleString('zh-CN'),
    reached: value != null && value >= threshold,
    progress: value == null ? 0 : Math.min(1, value / threshold)
  }
}))
const vesselReadout = computed(() => {
  const calls = report.value?.summary?.calls
  if (typeof calls !== 'number' || calls <= 0) return '本月暂无调用记录。接入模型并通过 SmartOps 完成调用后，这里开始累计真实进度。'
  const { next } = callProgress.value
  const head = `本月已调用 ${calls.toLocaleString('zh-CN')} 次`
  return next == null ? `${head} · 已达成全部档位` : `${head} · 下一档 ${next.toLocaleString('zh-CN')} 次（${(callProgress.value.progress * 100).toFixed(0)}%）`
})

function celebrate(item) {
  if (raining.value) return
  raining.value = true
  statusText.value = item ? `正在庆祝：${item.title}` : '正在播放演示庆祝动效（不关联真实数据）'
}
function celebrateDemo() { celebrate(null) }
function onFinished() {
  raining.value = false
  statusText.value = '庆祝动效播放完毕。'
}

onMounted(loadReport)
onBeforeUnmount(() => { disposed = true })
</script>

<style scoped>
.achievements { max-width: 1280px; margin: 0 auto; padding: 12px 0 36px; color: var(--smart-text); font-family: var(--font-cn); }
.hall-heading { display: flex; justify-content: space-between; gap: 24px; align-items: center; }
.eyebrow { margin: 0 0 10px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .13em; }
h1 { margin: 0; font-size: clamp(26px, 3vw, 36px); font-weight: 550; letter-spacing: -.03em; }
.intro { color: var(--smart-muted); font-size: 13px; line-height: 1.8; margin: 12px 0 0; max-width: 640px; }
h2 { margin: 0; font-size: 17px; font-weight: 550; }
.outline-button { display: inline-flex; align-items: center; justify-content: center; gap: 14px; min-height: 40px; padding: 9px 16px; border: 1px solid var(--smart-border); border-radius: 8px; font: inherit; font-size: 12px; color: var(--smart-text); background: var(--smart-surface); text-decoration: none; cursor: pointer; transition: border-color 140ms, background 140ms; white-space: nowrap; }
.outline-button:hover { border-color: var(--smart-primary-strong); }
.outline-button:disabled { opacity: .5; cursor: wait; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--smart-primary-strong); outline-offset: 3px; }
.state-panel { padding: 54px 24px; text-align: center; border: 1px solid var(--smart-border); border-radius: 12px; background: var(--smart-surface); color: var(--smart-muted); font-size: 13px; margin-top: 24px; }
.state-panel h2 { font-size: 15px; color: var(--smart-text); }
.state-panel p { margin: 14px 0 24px; }
.hall-layout { display: grid; grid-template-columns: minmax(300px, 5fr) minmax(0, 7fr); gap: 20px; align-items: start; margin-top: 28px; }
.analytics-panel { border: 1px solid var(--smart-border); border-radius: 12px; background: var(--smart-surface); padding: 24px; min-width: 0; }
/* 宿主契约：position:relative + overflow:visible（画布绝对定位铺满 stage，不能被面板裁掉）；
   桌面端滚动锁下由 @media (min-width:1101px) 覆写为 overflow-y:auto——画布始终在 stage 边界内，不裁切 */
.vessel-panel { overflow: visible; }
.vessel-stage { position: relative; height: clamp(280px, 30vw, 340px); margin: 18px 0 14px; }
.vessel-readout { font-family: var(--font-mono); font-size: 13px; font-variant-numeric: tabular-nums; margin: 0 0 4px; }
.source-note { color: var(--smart-muted); font-size: 11px; line-height: 1.8; margin: 14px 0 0; }
.vessel-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-top: 14px; }
.rain-status { color: var(--smart-muted); font: 11px/1.6 var(--font-mono); margin: 0; }
/* 袋口档位阶梯：左栏真实数据速览（五档达成情况），与右栏成就卡互补不重复 */
.tier-ladder { margin-top: 18px; border-top: 1px solid var(--smart-border); padding-top: 16px; }
.tier-ladder ul { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 8px; }
.tier-ladder li { display: grid; grid-template-columns: 60px minmax(0, 1fr) 52px; align-items: center; gap: 12px; font: 11px/1.4 var(--font-mono); color: var(--smart-muted); font-variant-numeric: tabular-nums; }
.tier-ladder li.reached .tier-state { color: var(--smart-primary-strong); }
.tier-label { text-align: right; }
.tier-track { height: 3px; background: var(--smart-border); border-radius: 2px; overflow: hidden; }
.tier-track i { display: block; height: 100%; background: var(--smart-primary-strong); border-radius: 2px; transition: width 200ms; }
.tier-state { text-align: right; }
.achievement-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; align-items: start; }
.achievement-card { border: 1px solid var(--smart-border); border-radius: 12px; background: var(--smart-surface); padding: 18px; min-width: 0; }
.achievement-card.unlocked { border-left: 2px solid #F5C942; }
.achievement-card header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.achievement-card h3 { margin: 0; font-size: 14px; font-weight: 550; }
.status-chip { font: 10px/1 var(--font-mono); letter-spacing: .06em; padding: 5px 9px; border-radius: 999px; border: 1px solid var(--smart-border); color: var(--smart-muted); white-space: nowrap; }
.status-chip[data-state=unlocked] { color: #F5C942; border-color: rgba(245, 201, 66, .5); }
.status-chip[data-state=next] { color: var(--smart-primary-strong); border-color: var(--smart-primary-strong); }
.value-line { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin: 14px 0 10px; font-size: 12px; color: var(--smart-muted); }
.value-line strong { font-family: var(--font-mono); font-size: 18px; font-weight: 600; color: var(--smart-text); font-variant-numeric: tabular-nums; }
.progress-track { height: 4px; background: var(--smart-border); border-radius: 2px; overflow: hidden; }
.progress-bar { height: 100%; background: var(--smart-primary-strong); border-radius: 2px; transition: width 200ms; }
.achievement-card.unlocked .progress-bar { background: #F5C942; }
.basis { color: var(--smart-muted); font-size: 11px; line-height: 1.7; margin: 12px 0 0; }
.celebrate-button { margin-top: 14px; }
/* 演示实例：虚线框 + 「演示」芯片，与真实账本卡视觉隔离；不挂庆祝按钮 */
.achievement-card.demo { border-style: dashed; }
.achievement-card.demo .status-chip[data-state=demo] { color: var(--smart-muted); border-style: dashed; }
.demo-divider { grid-column: 1 / -1; display: flex; align-items: center; gap: 12px; margin: 10px 0 2px; color: var(--smart-muted); font: 10px/1 var(--font-mono); letter-spacing: .12em; white-space: nowrap; }
.demo-divider::before, .demo-divider::after { content: ''; flex: 1 1 auto; border-top: 1px dashed var(--smart-border); }
.hall-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; margin-top: 20px; color: var(--smart-muted); font-size: 10px; line-height: 1.8; }
@media (max-width: 1100px) { .hall-layout { grid-template-columns: minmax(0, 1fr); } }
/* 桌面端双栏工作台：视口锁定，左右两栏各自独立滚动，页面本身不滚动——
   滚哪栏、另一栏不动，即「红框滑动相互独立」。
   206 = 顶栏 56 + 工作区条 54 + main.content 底部留白 96（global.css .content）；
   两栏均 min-height:0 + overflow-y:auto；画布在 stage 边界内，滚动不裁切。 */
@media (min-width: 1101px) {
  .achievements {
    height: 100vh; /* 旧浏览器回退 */
    height: calc(100dvh - 206px);
    display: flex;
    flex-direction: column;
  }
  .hall-heading, .hall-footer { flex: 0 0 auto; }
  .hall-layout { flex: 1 1 auto; min-height: 0; align-items: stretch; }
  .vessel-panel, .achievement-list {
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
    scrollbar-color: var(--smart-border) transparent;
  }
}
@media (max-width: 767px) {
  .achievements { padding-top: 4px; }
  .hall-heading { align-items: start; flex-direction: column; gap: 16px; }
  .vessel-stage { height: 300px; }
  .achievement-list { grid-template-columns: minmax(0, 1fr); }
  .hall-footer { flex-direction: column; }
}
</style>
