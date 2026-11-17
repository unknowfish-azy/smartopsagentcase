<template>
  <div class="twin-page">
    <header class="twin-head">
      <div>
        <p class="eyebrow">SENTINEL · DATACENTER DIGITAL TWIN</p>
        <h1>云服务器厂房 3D 孪生</h1>
        <p class="lede">
          虚拟场景演示：机柜排布、冷通道、机器人巡逻轨迹与温度/湿度/功率采样在同一个 3D 空间里对齐。
          端到端同步延迟（采集 → 传输 → 上屏）硬预算 <b>2.5 秒</b>，超限即告警。
        </p>
      </div>
      <div class="twin-head__right">
        <span class="twin-badge twin-badge--demo">演示数据 · 未接入真实扫描</span>
        <span class="twin-badge" :class="`twin-badge--${latency.level}`">
          同步延迟 {{ latencyMs }} ms · {{ latency.label }}
        </span>
        <button type="button" class="twin-btn" @click="running ? pause() : resume()">
          {{ running ? '暂停模拟' : '继续模拟' }}
        </button>
        <button type="button" class="twin-btn" @click="reset">重置</button>
      </div>
    </header>

    <div class="twin-grid">
      <section class="twin-stage" aria-label="机房三维场景">
        <DataCenterTwin3D
          :layout="layout"
          :telemetry="telemetry"
          :robot="robot"
          :waypoints="waypoints"
          :selected-id="selectedId"
          @select="select"
        />
        <div class="twin-stage__legend">
          <span><i class="dot dot--ok"></i>正常</span>
          <span><i class="dot dot--warn"></i>预警</span>
          <span><i class="dot dot--critical"></i>严重</span>
          <span class="twin-stage__hint">点击机柜查看详情</span>
        </div>
      </section>

      <aside class="twin-side">
        <article class="twin-card">
          <h2>同步延迟</h2>
          <p class="twin-metric" :class="`is-${latency.level}`">
            {{ latencyMs }}<span>ms</span>
          </p>
          <div class="twin-bar">
            <i :class="`is-${latency.level}`" :style="{ width: latencyPercent + '%' }"></i>
            <b class="twin-bar__budget" :style="{ left: budgetPercent + '%' }"></b>
          </div>
          <p class="twin-card__note">
            预算 {{ LATENCY_BUDGET_MS }} ms（竖线位置）。当前口径：采集时间戳 → 画面更新完成。
          </p>
        </article>

        <article class="twin-card">
          <h2>温度排行</h2>
          <ul class="twin-rank">
            <li v-for="rack in hottest" :key="rack.id" :class="{ 'is-selected': rack.id === selectedId }">
              <button type="button" class="twin-rank__row" @click="select(rack.id)">
                <span class="twin-rank__id">{{ rack.label }}</span>
                <span class="twin-rank__val" :class="`is-${rack.level}`">{{ rack.temperature }}°C</span>
              </button>
            </li>
            <li v-if="!hottest.length" class="twin-empty">暂无采样</li>
          </ul>
        </article>

        <article class="twin-card">
          <h2>机器人巡逻</h2>
          <p class="twin-robot">
            <span class="twin-robot__dot"></span>
            {{ running ? '巡航中' : '已暂停' }} · 第 {{ Math.round(patrolRatio * 100) }}% 圈
          </p>
          <p class="twin-card__note">
            坐标 x {{ robot.x.toFixed(2) }} / z {{ robot.z.toFixed(2) }} · 单圈 {{ heartbeat.lapSeconds }}s ·
            路点 {{ heartbeat.waypoints }} 个
          </p>
        </article>

        <article class="twin-card">
          <h2>实时预警 <em>{{ alarms.length }}</em></h2>
          <ul class="twin-alarm">
            <li v-for="alarm in alarms.slice(0, 6)" :key="alarm.id" :class="`is-${alarm.level}`">
              <span class="twin-alarm__level">{{ alarm.level === 'critical' ? '严重' : '预警' }}</span>
              <span class="twin-alarm__text">{{ alarm.text }}</span>
            </li>
            <li v-if="!alarms.length" class="twin-empty">所有机柜指标在阈值内</li>
          </ul>
          <p v-if="alarms.length > 6" class="twin-card__note">另有 {{ alarms.length - 6 }} 条未展开</p>
        </article>
      </aside>
    </div>

    <section v-if="selected" class="twin-detail" aria-label="选中机柜详情">
      <span class="twin-detail__id">{{ selected.label }}</span>
      <span>温度 <b :class="`is-${selected.level}`">{{ selected.temperature }}°C</b></span>
      <span>湿度 <b>{{ selected.humidity }}%RH</b></span>
      <span>功率 <b>{{ selected.power }} kW</b></span>
      <span class="twin-detail__level" :class="`is-${selected.level}`">{{ levelText(selected.level) }}</span>
      <button type="button" class="twin-btn" @click="select(selected.id)">关闭</button>
    </section>

    <footer class="twin-foot">
      <span>机柜 <b>{{ summary.racks }}</b></span>
      <span>平均温度 <b>{{ summary.avgTemperature ?? '—' }}°C</b></span>
      <span>总功率 <b>{{ summary.totalPower }} kW</b></span>
      <span>告警 <b :class="{ 'is-critical': summary.alarms > 0 }">{{ summary.alarms }}</b></span>
      <span>延迟 <b :class="`is-${summary.latencyLevel}`">{{ summary.latencyMs }} ms</b></span>
      <span class="twin-foot__note">
        真实场景接入路径：扫描点云 → 配准建模 → 传感器绑定 → 发布孪生。
      </span>
    </footer>

    <details class="twin-degrade">
      <summary>机柜清单（无 WebGL 时的降级视图）</summary>
      <table>
        <thead>
          <tr><th>机柜</th><th>温度</th><th>湿度</th><th>功率</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="rack in telemetry" :key="rack.id">
            <td>{{ rack.label }}</td>
            <td>{{ rack.temperature }}°C</td>
            <td>{{ rack.humidity }}%RH</td>
            <td>{{ rack.power }} kW</td>
            <td :class="`is-${rack.level}`">{{ levelText(rack.level) }}</td>
          </tr>
        </tbody>
      </table>
    </details>
  </div>
</template>

<script setup>
/**
 * DataCenterTwinView — 云服务器厂房 3D 孪生（演示态）
 *
 * 三态口径：演示态徽标常驻（未接入真实扫描）；WebGL 不可用时降级为机柜清单；
 * 延迟徽标是 2.5 秒预算的唯一展示出口，超限立刻转红。
 */
import { computed } from 'vue'
import DataCenterTwin3D from '../../components/sentinel/DataCenterTwin3D.vue'
import { useDataCenterTwin } from '../../composables/useDataCenterTwin.js'
import { LATENCY_BUDGET_MS } from '../../domain/sentinel/dataCenterTwin.js'

const {
  layout,
  path,
  running,
  selectedId,
  telemetry,
  latencyMs,
  latency,
  alarms,
  hottest,
  robot,
  patrolRatio,
  summary,
  heartbeat,
  pause,
  resume,
  reset,
  select
} = useDataCenterTwin({ tickMs: 1000, lapSeconds: 45 })

const waypoints = path

const selected = computed(() => telemetry.value.find(rack => rack.id === selectedId.value) || null)
const latencyPercent = computed(() => Math.min(100, (latencyMs.value / (LATENCY_BUDGET_MS * 1.2)) * 100))
const budgetPercent = computed(() => (LATENCY_BUDGET_MS / (LATENCY_BUDGET_MS * 1.2)) * 100)

const LEVEL_TEXT = { ok: '正常', warn: '预警', critical: '严重', unknown: '未知' }
function levelText(level) {
  return LEVEL_TEXT[level] || '未知'
}
</script>

<style scoped>
.twin-page {
  display: grid;
  gap: 16px;
  padding: 22px;
  color: var(--smart-text, #e8f2f7);
  background: var(--smart-bg, #071018);
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 12px;
}
.twin-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 14px; }
.eyebrow { margin: 0 0 6px; color: var(--smart-primary-strong, #7ad7f5); font: 11px ui-monospace, monospace; letter-spacing: .1em; }
.twin-head h1 { margin: 0; font-size: 26px; font-weight: 500; }
.lede { margin: 6px 0 0; max-width: 660px; color: var(--smart-muted, #92a6b5); font-size: 13px; line-height: 1.65; }
.lede b { color: var(--smart-text, #e8f2f7); font-weight: 600; }
.twin-head__right { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.twin-badge {
  padding: 6px 11px;
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 999px;
  font-size: 11px;
  color: var(--smart-muted, #92a6b5);
}
.twin-badge--demo { color: #8bcfb4; border-color: rgba(139, 207, 180, .35); }
.twin-badge--ok { color: #8bcfb4; border-color: rgba(139, 207, 180, .35); }
.twin-badge--warn { color: #d9b96d; border-color: rgba(217, 185, 109, .35); }
.twin-badge--breach { color: #e5787a; border-color: rgba(229, 72, 77, .45); }
.twin-btn {
  padding: 6px 12px;
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 8px;
  background: transparent;
  color: var(--smart-text, #e8f2f7);
  font-size: 12px;
  cursor: pointer;
}
.twin-btn:hover { border-color: var(--smart-primary-strong, #7ad7f5); color: var(--smart-primary-strong, #7ad7f5); }
.twin-grid { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 14px; }
.twin-stage { position: relative; min-width: 0; }
.twin-stage__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 8px 4px 0;
  color: var(--smart-muted, #92a6b5);
  font-size: 11px;
}
.twin-stage__legend span { display: inline-flex; align-items: center; gap: 6px; }
.twin-stage__hint { margin-left: auto; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot--ok { background: #4f9fbf; }
.dot--warn { background: #d9b96d; }
.dot--critical { background: #e5484d; }
.twin-side { display: grid; gap: 12px; align-content: start; }
.twin-card {
  padding: 12px 14px;
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 10px;
  background: rgba(122, 215, 245, .03);
}
.twin-card h2 {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: .06em;
  color: var(--smart-muted, #92a6b5);
}
.twin-card h2 em { font-style: normal; color: #e5787a; }
.twin-metric { margin: 0 0 8px; font: 26px ui-monospace, monospace; }
.twin-metric span { margin-left: 3px; font-size: 11px; color: var(--smart-muted, #92a6b5); }
.twin-metric.is-ok { color: #8bcfb4; }
.twin-metric.is-warn { color: #d9b96d; }
.twin-metric.is-breach { color: #e5787a; }
.twin-bar { position: relative; height: 6px; border-radius: 999px; background: rgba(255, 255, 255, .07); }
.twin-bar i { display: block; height: 100%; border-radius: 999px; transition: width .35s ease; }
.twin-bar i.is-ok { background: #4f9fbf; }
.twin-bar i.is-warn { background: #d9b96d; }
.twin-bar i.is-breach { background: #e5484d; }
.twin-bar__budget { position: absolute; top: -3px; width: 1px; height: 12px; background: rgba(232, 242, 247, .55); }
.twin-card__note { margin: 8px 0 0; color: var(--smart-muted, #92a6b5); font-size: 11px; line-height: 1.6; }
.twin-rank, .twin-alarm { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.twin-rank__row {
  display: flex;
  justify-content: space-between;
  width: 100%;
  padding: 5px 6px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--smart-text, #e8f2f7);
  font-size: 12px;
  cursor: pointer;
}
.twin-rank__row:hover { background: rgba(122, 215, 245, .08); }
.twin-rank li.is-selected .twin-rank__row { background: rgba(122, 215, 245, .14); }
.twin-rank__id { font-family: ui-monospace, monospace; color: var(--smart-muted, #92a6b5); }
.twin-rank__val.is-ok { color: #8bcfb4; }
.twin-rank__val.is-warn { color: #d9b96d; }
.twin-rank__val.is-critical { color: #e5787a; }
.twin-robot { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 13px; }
.twin-robot__dot { width: 8px; height: 8px; border-radius: 50%; background: #7ad7f5; box-shadow: 0 0 8px #7ad7f5; }
.twin-alarm li {
  display: flex;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.5;
  background: rgba(255, 255, 255, .02);
}
.twin-alarm li.is-critical { background: rgba(229, 72, 77, .1); }
.twin-alarm li.is-warn { background: rgba(217, 185, 109, .08); }
.twin-alarm__level { flex: 0 0 auto; color: var(--smart-muted, #92a6b5); }
.twin-alarm li.is-critical .twin-alarm__level { color: #e5787a; }
.twin-alarm li.is-warn .twin-alarm__level { color: #d9b96d; }
.twin-alarm__text { min-width: 0; }
.twin-empty { padding: 6px; color: var(--smart-muted, #92a6b5); font-size: 11px; }
.twin-detail {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  padding: 10px 14px;
  border: 1px solid rgba(122, 215, 245, .28);
  border-radius: 10px;
  background: rgba(122, 215, 245, .05);
  font-size: 12px;
}
.twin-detail__id { font-family: ui-monospace, monospace; color: var(--smart-primary-strong, #7ad7f5); }
.twin-detail__level { margin-left: auto; }
.twin-detail .twin-btn { padding: 3px 9px; }
.twin-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  padding: 10px 14px;
  border-top: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  color: var(--smart-muted, #92a6b5);
  font-size: 11px;
}
.twin-foot b { color: var(--smart-text, #e8f2f7); font-family: ui-monospace, monospace; font-weight: 500; }
.twin-foot__note { margin-left: auto; }
.is-ok { color: #8bcfb4; }
.is-warn { color: #d9b96d; }
.is-critical { color: #e5787a; }
.twin-degrade { color: var(--smart-muted, #92a6b5); font-size: 11px; }
.twin-degrade summary { cursor: pointer; padding: 6px 0; }
.twin-degrade table { width: 100%; margin-top: 8px; border-collapse: collapse; }
.twin-degrade th, .twin-degrade td { padding: 5px 8px; border-bottom: 1px solid rgba(159, 190, 207, .12); text-align: left; }
.twin-degrade th { font-weight: 500; color: var(--smart-muted, #92a6b5); }
@media (max-width: 1100px) {
  .twin-grid { grid-template-columns: minmax(0, 1fr); }
  .twin-side { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
}
</style>
