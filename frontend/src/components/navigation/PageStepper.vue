<template>
  <nav v-if="view" class="page-stepper" :aria-label="`${view.flowId} page navigation`">
    <button
      type="button"
      class="page-stepper__button"
      :disabled="view.previous.disabled"
      :aria-label="previousAriaLabel"
      :title="previousAriaLabel"
      @click="move(view.previous)"
    ><ArrowLeft aria-hidden="true" /><span>上一步</span></button>
    <p><span>{{ view.flowId.toUpperCase() }}</span>{{ view.current.label }}</p>
    <button
      type="button"
      class="page-stepper__button page-stepper__button--next"
      :disabled="view.next.disabled"
      :aria-label="nextAriaLabel"
      :title="nextAriaLabel"
      @click="move(view.next)"
    ><span>下一步</span><ArrowRight aria-hidden="true" /></button>
  </nav>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { isPageStepperKeyEligible } from '../../navigation/pageFlow.js'
import { stepperView } from './pageStepper.js'

const props = defineProps({ routeName: { type: String, default: '' } })
const router = useRouter()
const view = computed(() => stepperView(props.routeName))
const previousAriaLabel = computed(() => view.value?.previous.disabled ? 'Previous page unavailable' : `Previous page: ${view.value.previous.label}`)
const nextAriaLabel = computed(() => view.value?.next.disabled ? 'Next page unavailable' : `Next page: ${view.value.next.label}`)

function move(step) {
  if (!step || step.disabled) return
  router.push({ name: step.routeName })
}

function canHandleKey(target) {
  if (!isPageStepperKeyEligible(target)) return false
  return !target?.closest?.('input, textarea, select, dialog, iframe, [role="dialog"], [contenteditable="true"]')
}

function onKeydown(event) {
  if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || !canHandleKey(event.target)) return
  if (event.key === 'ArrowLeft' && !view.value?.previous.disabled) {
    event.preventDefault()
    move(view.value.previous)
  }
  if (event.key === 'ArrowRight' && !view.value?.next.disabled) {
    event.preventDefault()
    move(view.value.next)
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.page-stepper { display: grid; grid-template-columns: minmax(110px, 1fr) auto minmax(110px, 1fr); align-items: center; gap: 16px; margin: 22px 0 0; padding: 12px 0; border-top: 1px solid var(--smart-border); border-bottom: 1px solid var(--smart-border); }.page-stepper p { display: grid; gap: 3px; margin: 0; color: var(--smart-text); font: 10px var(--font-mono); letter-spacing: .08em; text-align: center; }.page-stepper p span { color: var(--smart-muted); font-size: 8px; }.page-stepper__button { display: inline-flex; align-items: center; gap: 8px; width: max-content; min-height: 32px; padding: 0; border: 0; background: transparent; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .08em; cursor: pointer; }.page-stepper__button--next { justify-self: end; }.page-stepper__button svg { width: 14px; height: 14px; }.page-stepper__button:disabled { color: var(--smart-muted); cursor: default; opacity: .5; }.page-stepper__button:not(:disabled):hover, .page-stepper__button:not(:disabled):focus-visible { color: var(--smart-text); outline: 1px solid var(--smart-primary-strong); outline-offset: 4px; }
@media (max-width: 767px) { .page-stepper { grid-template-columns: 1fr auto 1fr; gap: 8px; }.page-stepper__button { min-height: 40px; }.page-stepper__button span { display: none; } }
</style>
