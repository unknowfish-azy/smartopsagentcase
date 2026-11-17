import assert from 'node:assert/strict'
import { describe, test } from 'node:test'

import {
  HAZARD_ROUTES,
  NAVIGATION_INTENTS,
  hazardBubble,
  isHazardRoute,
  normalizeRoutePath,
  resolveNavigationIntent,
} from '../src/components/persona/voiceCommandRegistry.js'

describe('voiceCommandRegistry', () => {
  describe('normalizeRoutePath', () => {
    test('去掉末尾斜杠和 query', () => {
      assert.equal(normalizeRoutePath('/admin/users/'), '/admin/users')
      assert.equal(normalizeRoutePath('/chat?deep=true'), '/chat')
      assert.equal(normalizeRoutePath('/knowledge/space#anchor'), '/knowledge/space')
      assert.equal(normalizeRoutePath('/'), '/')
      assert.equal(normalizeRoutePath(''), '')
      assert.equal(normalizeRoutePath(null), '')
    })
  })

  describe('isHazardRoute', () => {
    test('精确命中 HAZARD_ROUTES 的 key', () => {
      assert.ok(isHazardRoute('/admin'))
      assert.ok(isHazardRoute('/admin/users'))
      assert.ok(isHazardRoute('/sentinel/scripts'))
      assert.ok(isHazardRoute('/robot'))
    })

    test('归一化路径也能命中', () => {
      assert.ok(isHazardRoute('/admin/users/'))
      assert.ok(isHazardRoute('/admin/users?role=admin'))
    })

    test('普通路由返回 false', () => {
      assert.equal(isHazardRoute('/chat'), false)
      assert.equal(isHazardRoute('/knowledge/space'), false)
      assert.equal(isHazardRoute('/servers'), false)
      assert.equal(isHazardRoute('/knowledge/review/thread'), false)
    })

    test('不存在的路由返回 false', () => {
      assert.equal(isHazardRoute('/totally/made/up'), false)
    })
  })

  describe('resolveNavigationIntent', () => {
    test('导航前缀 + 关键词命中 → 安全跳转', () => {
      const hit = resolveNavigationIntent('帮我打开知识空间')
      assert.equal(hit.matched, true)
      assert.equal(hit.path, '/knowledge/space')
      assert.equal(hit.label, '知识空间')
      assert.equal(hit.blocked, false)
      assert.equal(hit.hazard, undefined)
    })

    test('导航前缀 + 高危关键词命中 → blocked=true 且带 hazard', () => {
      const blocked = resolveNavigationIntent('打开管理控制台')
      assert.equal(blocked.matched, true)
      assert.equal(blocked.blocked, true)
      assert.equal(blocked.path, '/admin')
      assert.ok(blocked.hazard)
      assert.ok(blocked.hazard.reason.length > 0)
    })

    test('只有关键词、没有导航前缀 → 不命中（避免业务查询误判）', () => {
      const no = resolveNavigationIntent('告警率很高')
      assert.equal(no.matched, false)
      assert.equal(no.reason, 'no-nav-intent')
    })

    test('只有导航前缀、没有关键词 → 不命中', () => {
      const no = resolveNavigationIntent('帮我看一下')
      assert.equal(no.matched, false)
    })

    test('混合意图："去告警中心看看 cpu 多少" → 命中（取导航意图优先）', () => {
      const hit = resolveNavigationIntent('去告警中心看看cpu多少')
      assert.equal(hit.matched, true)
      assert.equal(hit.path, '/sentinel/alerts')
    })

    test('空字符串 → 不命中', () => {
      const no = resolveNavigationIntent('')
      assert.equal(no.matched, false)
    })

    test('null/undefined → 不命中', () => {
      assert.equal(resolveNavigationIntent(null).matched, false)
      assert.equal(resolveNavigationIntent(undefined).matched, false)
    })

    test('英文导航前缀 + 关键词 → 命中', () => {
      const hit = resolveNavigationIntent('open the alerts')
      assert.equal(hit.matched, true)
      assert.equal(hit.path, '/sentinel/alerts')
    })

    test('多意图取第一个（词典顺序决定优先级）', () => {
      // "帮我打开对话" → 先匹配 chat，再匹配不到 admin（没导航前缀的关键词不触发）
      const hit = resolveNavigationIntent('帮我打开对话，再看看模型网关')
      assert.equal(hit.matched, true)
      assert.equal(hit.path, '/chat')
    })

    test('所有 critical 高危 level 都有 reason', () => {
      for (const [path, info] of Object.entries(HAZARD_ROUTES)) {
        assert.ok(info.reason, `${path} 缺 reason`)
        assert.ok(['critical', 'high', 'medium'].includes(info.level), `${path} level 非法`)
      }
    })
  })

  describe('hazardBubble', () => {
    test('包含标签、原因和"手动打开"提示', () => {
      const bubble = hazardBubble({
        label: '管理控制台',
        hazard: { level: 'critical', reason: '涉及用户、安全与审批' },
      })
      assert.ok(bubble.includes('管理控制台'))
      assert.ok(bubble.includes('涉及用户、安全与审批'))
      assert.ok(bubble.includes('手动打开'))
    })
  })
})
