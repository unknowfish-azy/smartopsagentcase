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
    'InspectorDesk',
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

test('harbor and cloud-native workbenches fold into the smart repository 3D space', () => {
  /* 2026-11-16：Harbor 工作台与云原生工程并入智能仓库 3D 空间，侧栏不再单列（路由保留）。 */
  assert.equal(findPersonalSystemGroup('HarborWorkbench'), null)
  assert.equal(findPersonalSystemGroup('CloudNativeWorkbench'), null)
  const repository = findPersonalSystemGroup('SmartRepository')
  assert.equal(repository.id, 'repository')
  assert.equal(repository.to, '/repository')
})

test('contains only groups with existing direct routes', () => {
  assert.deepEqual(visiblePersonalSystemGroups(personalSystemGroups).map(group => group.id), [
    'home', 'ai-chat', 'repository', 'knowledge', 'research', 'extensions', 'operations', 'models', 'agent', 'memory', 'sentinel'
  ])
})

test('milestone hall is folded into token usage, no longer a sidebar item', () => {
  /* 战报已并入 /token-usage?view=milestones：侧栏不留独立项，避免一级菜单冗余。
     洞察组随后也并入智能仓库（2026-11-16 并行整合），两组入口均不再单列。 */
  assert.equal(findPersonalSystemGroup('MilestoneHall'), null)
  assert.equal(findPersonalSystemGroup('Insights'), null)
  // 全部导航树里不得再有 /milestones 菜单项（redirect 兼容除外，属路由层）
  const sidebarRefs = personalSystemGroups.flatMap(group => [group, ...(group.children || [])])
    .filter(item => item.to === '/milestones')
  assert.deepEqual(sidebarRefs, [])
})

test('scholar tools live inside the knowledge center group', () => {
  const group = findPersonalSystemGroup('ScholarQa')

  assert.equal(group.id, 'knowledge')
  assert.equal(group.cn, '知识中心')
  assert.equal(group.to, '/knowledge/space')
  assert.deepEqual(group.children.map(item => item.routeName), ['KnowledgeSpace', 'KnowledgeSciverse', 'KnowledgeAtlas', 'ScholarQa', 'ScholarCards', 'ScholarReview', 'ScholarPipeline', 'SharedKnowledge'])
  const atlas = group.children.find(child => child.routeName === 'KnowledgeAtlas')
  assert.equal(atlas.to, '/atlas')
  const pipeline = group.children.find(child => child.routeName === 'ScholarPipeline')
  assert.equal(pipeline.to, '/scholar/pipeline')
  assert.ok(visiblePersonalSystemGroups(personalSystemGroups, 'operator').includes(group))
})

test('re workbench joins the neural research group as a third destination', () => {
  const group = findPersonalSystemGroup('ReWorkbench')

  assert.equal(group.id, 'research')
  assert.equal(group.cn, '联网研究')
  assert.deepEqual(group.children.map(item => item.routeName), ['WebResearch', 'Radar', 'ReWorkbench'])
  const item = group.children.find(child => child.routeName === 'ReWorkbench')
  assert.equal(item.to, '/re-workbench')
  assert.ok(visiblePersonalSystemGroups(personalSystemGroups, 'operator').includes(group))
})

test('sentinel groups dashboard, scripts, alerts and Guardian under one menu', () => {
  const group = findPersonalSystemGroup('SentinelDashboard')

  assert.equal(group.id, 'sentinel')
  assert.equal(group.to, '/sentinel')
  assert.equal(group.cn, '哨兵与自动化')
  assert.deepEqual(group.children.map(item => item.routeName), ['SentinelDashboard', 'ScriptLibrary', 'AlertCenter', 'IncidentCenter', 'SentinelGuardian', 'ForecastPlane', 'SectionAnalysis', 'EngineObservability', 'DataCenterTwin'])
  assert.deepEqual(group.children.map(item => item.to), ['/sentinel', '/sentinel/scripts', '/sentinel/alerts', '/incidents', '/sentinel/guardian', '/sentinel/forecast', '/sentinel/sections', '/sentinel/observability', '/sentinel/twin'])
  assert.equal(findPersonalSystemGroup('SentinelGuardian'), group)
  assert.equal(findPersonalSystemGroup('ForecastPlane'), group)
  assert.equal(findPersonalSystemGroup('SectionAnalysis'), group)
  assert.equal(findPersonalSystemGroup('EngineObservability'), group)
  assert.equal(findPersonalSystemGroup('DataCenterTwin'), group)
  // 普通运维用户也要能用（不是管理员专属）。
  assert.ok(visiblePersonalSystemGroups(personalSystemGroups, 'operator').includes(group))
})

test('scene reconstruction tool lives inside the extensions group', () => {
  const group = findPersonalSystemGroup('SceneReconstruction')

  assert.equal(group.id, 'extensions')
  assert.equal(group.cn, '扩展能力')
  assert.deepEqual(group.children.map(item => item.routeName), ['PluginCenter', 'SkillCenter', 'SceneReconstruction'])
  const item = group.children.find(child => child.routeName === 'SceneReconstruction')
  assert.equal(item.to, '/reconstruction')
  assert.equal(item.cn, '实景还原')
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
  // 侧栏知识入口已指向 KnowledgeSpace（/knowledge/space）；兼容两种 routeName，
  // 断言的仍是「中文标签保持简洁」这一语义，不随入口改名而失效。
  const group = findPersonalSystemGroup('KnowledgeSpace') || findPersonalSystemGroup('Knowledge')

  assert.equal(group.label, 'KNOWLEDGE')
  assert.equal(group.cn, '知识中心')
})

test('team collaboration entry lives in the top space switcher, not the sidebar', () => {
  /* 2026-11-16：侧栏不再单列「团队协作」，顶部 SpaceSwitcher 的「团队空间」为唯一固定入口。 */
  assert.equal(findPersonalSystemGroup('TeamSpaces'), null)
  for (const role of ['operator', 'admin']) {
    assert.ok(!visiblePersonalSystemGroups(personalSystemGroups, role).some(group => group.to === '/teams'), `${role} sidebar must not contain a /teams entry`)
  }
})
