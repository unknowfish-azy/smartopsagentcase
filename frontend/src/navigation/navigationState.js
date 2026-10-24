import { findPersonalSystemGroup } from './personalSystemNavigation.js'

export function sanitizeExpandedGroupIds(value, groups) {
  const expandableIds = new Set(
    groups.filter(group => group.children.length > 0).map(group => group.id)
  )
  const ids = Array.isArray(value) ? value : []
  return [...new Set(ids.filter(id => typeof id === 'string' && expandableIds.has(id)))]
}

export function resolveExpandedGroupIds(routeName, persistedIds, groups) {
  const expandedIds = sanitizeExpandedGroupIds(persistedIds, groups)
  const activeGroup = findPersonalSystemGroup(routeName, groups)
  if (!activeGroup || activeGroup.children.length === 0 || expandedIds.includes(activeGroup.id)) {
    return expandedIds
  }
  return [...expandedIds, activeGroup.id]
}

export function toggleExpandedGroupId(groupId, expandedIds, groups, routeName) {
  const sanitized = sanitizeExpandedGroupIds(expandedIds, groups)
  const group = groups.find(item => item.id === groupId)
  const activeGroup = findPersonalSystemGroup(routeName, groups)
  if (!group || group.children.length === 0) return sanitized
  if (activeGroup?.id === groupId && sanitized.includes(groupId)) return sanitized
  return sanitized.includes(groupId)
    ? sanitized.filter(id => id !== groupId)
    : [...sanitized, groupId]
}
