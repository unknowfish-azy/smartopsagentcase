const step = (routeName, to, label) => Object.freeze({ routeName, to, label })

export const pageFlows = Object.freeze([
  Object.freeze({
    id: 'agent',
    steps: Object.freeze([
      step('AgentCommandCenter', '/agent', 'COMMAND CENTER'),
      step('ExecutionTrace', '/agent/trace', 'EXECUTION TRACE'),
      step('AgentModule', '/agent/module', 'AGENT MODULE')
    ])
  }),
  Object.freeze({
    id: 'memory',
    steps: Object.freeze([
      step('InspectorCenter', '/inspector', 'INSPECTOR CENTER'),
      step('InspectorStatistics', '/inspector/statistics', 'STATISTICS')
    ])
  })
])

export function resolvePageStep(routeName, flows = pageFlows) {
  for (const flow of flows) {
    const index = flow.steps.findIndex(step => step.routeName === routeName)
    if (index >= 0) {
      return {
        flow,
        index,
        current: flow.steps[index],
        previous: flow.steps[index - 1] || null,
        next: flow.steps[index + 1] || null
      }
    }
  }
  return null
}

export function previousPageStep(routeName, flows = pageFlows) {
  return resolvePageStep(routeName, flows)?.previous || null
}

export function nextPageStep(routeName, flows = pageFlows) {
  return resolvePageStep(routeName, flows)?.next || null
}

export function isPageStepperKeyEligible(target) {
  const tagName = target?.tagName?.toLowerCase()
  return !target?.isContentEditable && !['input', 'textarea', 'select', 'dialog', 'iframe'].includes(tagName)
}
