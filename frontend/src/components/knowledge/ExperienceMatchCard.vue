<script setup>
/**
 * 经验库匹配卡片（公共组件）。
 *
 * 展示 POST /api/knowledge/recommendations 的匹配结果：建议动作、来源、
 * 置信度与验证要点。两个使用方：
 *  - 日志诊断页（LogDiagnosisView）：回灌侧，展示历史处理经验；
 *  - 工单详情页（IncidentDetailView）：推荐处理动作，可一键"记录为已执行"。
 *
 * 空结果是有效结论：如实展示 emptyText，不编造建议——与诊断页的诚实原则一致。
 */

defineProps({
  matches: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  /** 检索失败标记：失败时展示提示，不当作"无匹配" */
  error: { type: Boolean, default: false },
  /** true 时每条建议带「已执行该动作」按钮（工单场景） */
  actionable: { type: Boolean, default: false },
  emptyText: { type: String, default: '经验库暂无匹配的历史处理动作。' },
  busy: { type: Boolean, default: false }
})

defineEmits(['execute'])

function sourceLabel(source) {
  if (source === 'OPERATOR_MEMORY') return '运维经验'
  return source || '经验库'
}
</script>

<template>
  <div class="exp-card" role="status">
    <p v-if="loading" class="exp-card__note">正在检索经验库…</p>
    <template v-else>
      <ul v-if="matches.length" class="exp-card__list">
        <li v-for="(m, i) in matches" :key="i" class="exp-card__item">
          <p class="exp-card__action">{{ m.action }}</p>
          <p class="exp-card__meta">
            <span class="exp-card__source">{{ sourceLabel(m.source) }}</span>
            <span class="exp-card__conf">置信度 {{ Math.round((m.confidence || 0) * 100) }}%</span>
            <span v-if="m.sourceRefs" class="exp-card__refs" :title="m.sourceRefs">来源 {{ m.sourceRefs }}</span>
          </p>
          <p v-if="m.verification" class="exp-card__verify">{{ m.verification }}</p>
          <div v-if="actionable" class="exp-card__actions">
            <button type="button" :disabled="busy" @click="$emit('execute', m)">已执行该动作</button>
            <span class="exp-card__hint">点击会以评论形式记入工单时间线</span>
          </div>
        </li>
      </ul>
      <p v-else-if="error" class="exp-card__note">经验库检索失败，已跳过（不影响当前结论）。</p>
      <p v-else class="exp-card__note">{{ emptyText }}</p>
    </template>
  </div>
</template>

<style scoped>
.exp-card__note {
  margin: 0;
  font-size: var(--ds-type-body-caption-size, 12px);
  color: var(--ds-color-muted, #6b7280);
  line-height: var(--ds-line-height-base, 1.6);
}

.exp-card__list {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space-3, 12px);
  margin: 0;
  padding: 0;
  list-style: none;
}

.exp-card__item {
  padding: var(--ds-space-3, 12px);
  border: 1px solid var(--ds-color-border, #d1d5db);
  border-radius: var(--ds-radius-sm, 8px);
  background: var(--ds-surface-raised, rgba(255, 255, 255, 0.6));
}

.exp-card__action {
  margin: 0 0 var(--ds-space-1, 4px);
  font-size: var(--ds-type-body-size, 14px);
  font-weight: 600;
  line-height: var(--ds-line-height-base, 1.6);
}

.exp-card__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--ds-space-2, 8px);
  margin: 0 0 var(--ds-space-1, 4px);
  font-size: var(--ds-type-caption-size, 12px);
  color: var(--ds-color-muted, #6b7280);
  font-variant-numeric: var(--ds-type-num);
}

.exp-card__source {
  padding: 1px var(--ds-space-2, 8px);
  border-radius: var(--ds-radius-pill, 999px);
  background: var(--ds-pill-info-bg, rgba(36, 150, 237, 0.12));
  color: var(--ds-pill-info-fg, #1d7fd1);
}

.exp-card__refs {
  overflow: hidden;
  max-width: 100%;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.exp-card__verify {
  margin: 0;
  font-size: var(--ds-type-caption-size, 12px);
  color: var(--ds-color-muted, #6b7280);
}

.exp-card__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--ds-space-2, 8px);
  margin-top: var(--ds-space-2, 8px);
}

.exp-card__hint {
  font-size: var(--ds-type-caption-size, 12px);
  color: var(--ds-color-muted, #6b7280);
}
</style>
