import assert from 'node:assert/strict'
import test from 'node:test'

import {
  findPersonalSystemGroup,
  personalSystemGroups,
  visiblePersonalSystemGroups
} from '../src/navigation/personalSystemNavigation.js'

test('maps Inspector statistics to the existing Memory parent group', () => {
  const group = findPersonalSystemGroup('InspectorStatistics')

  assert.equal(group.id, 'memory')
  assert.equal(group.label, 'MEMORY')
  assert.deepEqual(group.children.map(item => item.routeName), [
    'InspectorCenter',
    'InspectorStatistics',
    'OperationRunHistory',
    'RecoveryContracts',
    'KnowledgeCandidateReview'
  ])
})

test('exposes persisted remote operation runs under Memory', () => {
  const group = findPersonalSystemGroup('OperationRunHistory')
  const item = group.children.find(child => child.routeName === 'OperationRunHistory')

  assert.equal(group.id, 'memory')
  assert.equal(item.to, '/operations/runs')
  assert.equal(item.cn, '运行记录')
})

test('keeps Harbor as an independent workbench route', () => {
  const group = findPersonalSystemGroup('HarborWorkbench')
  assert.equal(group.id, 'harbor')
  assert.equal(group.to, '/harbor')
})

test('keeps cloud-native resources inside its workbench route', () => {
  const group = findPersonalSystemGroup('CloudNativeWorkbench')
  assert.equal(group.id, 'cloud-native')
  assert.equal(group.to, '/cloud-native')
  assert.equal(group.children.length, 0)
})

test('contains only groups with existing direct routes', () => {
  assert.deepEqual(visiblePersonalSystemGroups(personalSystemGroups).map(group => group.id), [
    'home', 'ai-chat', 'team-space', 'knowledge', 'cloud-native', 'plugins', 'skills', 'connections', 'harbor', 'operations', 'health', 'milestones', 'models', 'agent', 'memory', 'sentinel'
  ])
})

test('milestone hall is a first-class destination beside health center', () => {
  const group = findPersonalSystemGroup('MilestoneHall')

  assert.equal(group.id, 'milestones')
  assert.equal(group.to, '/milestones')
  assert.equal(group.label, 'MILESTONES')
  assert.equal(group.cn, '里程碑战报')
  // 所有角色可见（庆祝动效不设权限门槛，数据仍按本人账本）
  assert.ok(visiblePersonalSystemGroups(personalSystemGroups, 'operator').includes(group))
})

test('sentinel groups dashboard, scripts, alerts and Guardian under one menu', () => {
  const group = findPersonalSystemGroup('SentinelDashboard')

  assert.equal(group.id, 'sentinel')
  assert.equal(group.to, '/sentinel')
  assert.equal(group.cn, '哨兵与自动化')
  assert.deepEqual(group.children.map(item => item.routeName), ['SentinelDashboard', 'ScriptLibrary', 'AlertCenter', 'SentinelGuardian'])
  assert.deepEqual(group.children.map(item => item.to), ['/sentinel', '/sentinel/scripts', '/sentinel/alerts', '/sentinel/guardian'])
  assert.equal(findPersonalSystemGroup('SentinelGuardian'), group)
  // 普通运维用户也要能用（不是管理员专属）。
  assert.ok(visiblePersonalSystemGroups(personalSystemGroups, 'operator').includes(group))
})

test('exposes AI chat as a first-class personal system destination', () => {
  const group = findPersonalSystemGroup('Chat')

  assert.equal(group.id, 'ai-chat')
  assert.equal(group.to, '/chat')
  assert.equal(group.label, 'AI CHAT')
})

test('model menu keeps the Astra6 group and exposes the gateway inside it', () => {
  assert.deepEqual(findPersonalSystemGroup('TokenUsage').children.map(item => item.routeName), ['ModelSettings', 'ModelGateway', 'ModelStrength', 'TokenUsage'])
  assert.equal(findPersonalSystemGroup('ModelGateway').id, 'models')
  assert.equal(findPersonalSystemGroup('ModelStrength').id, 'models')
})

test('uses concise Chinese for the Knowledge navigation label', () => {
  const group = findPersonalSystemGroup('Knowledge')

  assert.equal(group.label, '知识库')
  assert.equal(group.cn, '知识库')
})

test('team collaboration has a real main-menu destination for ordinary users', () => {
  const group = findPersonalSystemGroup('TeamSpaces')
  assert.ok(group, 'team space must be reachable from the main menu, not just the top switcher')
  assert.equal(group.to, '/teams')
  assert.equal(group.cn, '团队协作')
  assert.equal(group.children.length, 0, 'do not add links for unimplemented shared agents or tasks')
  assert.ok(visiblePersonalSystemGroups(personalSystemGroups, 'operator').includes(group))
  assert.ok(visiblePersonalSystemGroups(personalSystemGroups, 'admin').includes(group))
})
