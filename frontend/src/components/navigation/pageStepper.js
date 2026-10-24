import { resolvePageStep } from '../../navigation/pageFlow.js'

function buttonView(step, direction) {
  return {
    direction,
    routeName: step?.routeName || null,
    label: step?.label || null,
    disabled: step === null
  }
}

export function stepperView(routeName) {
  const resolved = resolvePageStep(routeName)
  if (!resolved) return null
  return {
    flowId: resolved.flow.id,
    current: resolved.current,
    previous: buttonView(resolved.previous, 'previous'),
    next: buttonView(resolved.next, 'next')
  }
}
