import assert from 'node:assert/strict'
import test from 'node:test'

import { searchKnowledgeEntries, knowledgeDomains } from '../src/views/knowledge/knowledgeCatalog.js'
import {
  buildMosaic, sizeForK, colsForStage, BASE_TILE, TILE_GAP, SIZE_STEPS,
} from '../src/views/knowledge/space/mosaic/mosaicLayout.js'

const all = searchKnowledgeEntries({})
const orderOf = new Map(knowledgeDomains.map((d, i) => [d.id, i]))

test('buildMosaic 的 tile 数 === 运行时条目数（全量同屏，无截断）', () => {
  const field = buildMosaic(all, knowledgeDomains, 1440)
  assert.equal(field.tiles.length, all.length)
  assert.equal(field.total, all.length)
})

test('id 唯一，无重复 tile', () => {
  const field = buildMosaic(all, knowledgeDomains, 1440)
  assert.equal(new Set(field.tiles.map(t => t.id)).size, field.tiles.length)
})

test('排序稳定：两次构建坐标逐项相等，域顺序与 knowledgeDomains 一致', () => {
  const a = buildMosaic(all, knowledgeDomains, 1440)
  const b = buildMosaic(all, knowledgeDomains, 1440)
  assert.deepEqual(a.tiles.map(t => [t.id, t.x, t.y]), b.tiles.map(t => [t.id, t.x, t.y]))

  // 域顺序单调不降（按登记顺序）
  let prev = -1
  for (const t of a.tiles) {
    const o = orderOf.get(t.entry.directory.domainId) ?? 99
    assert.ok(o >= prev, `域顺序乱序：${t.entry.directory.domainId} 出现在 ${prev} 之后`)
    prev = o
  }
})

test('cols 公式与 S0 档首屏可放下（1440 视口）', () => {
  assert.equal(colsForStage(1440), Math.floor(1440 / (BASE_TILE * SIZE_STEPS[0].k)))
  const cols = colsForStage(1440)
  const rows = Math.ceil(all.length / cols)
  // S0 档格子 28px + 1px 间隙 ≈ 29px/行，首屏高度需 <= 900
  assert.ok(rows * (SIZE_STEPS[0].px + TILE_GAP) <= 900, `S0 首屏高度 ${rows * (SIZE_STEPS[0].px + TILE_GAP)}px 超出 900`)
})

test('worldW/worldH 与 cols/rows 自洽，所有坐标非负且无重叠', () => {
  const f = buildMosaic(all, knowledgeDomains, 1440)
  assert.equal(f.worldW, f.cols * BASE_TILE + (f.cols - 1) * TILE_GAP)
  assert.equal(f.worldH, f.rows * BASE_TILE + (f.rows - 1) * TILE_GAP)
  const seen = new Set()
  for (const t of f.tiles) {
    assert.ok(t.x >= 0 && t.y >= 0)
    assert.ok(!seen.has(`${t.x},${t.y}`), `坐标重叠：${t.x},${t.y}`)
    seen.add(`${t.x},${t.y}`)
  }
})

test('小域折叠：docker/ubuntu/centos 标签统一为「其他域 · 4 条」，但 4 个 tile 仍在且域色各自独立', () => {
  const f = buildMosaic(all, knowledgeDomains, 1440)
  const smallTiles = f.tiles.filter(t => ['docker', 'ubuntu', 'centos'].includes(t.entry.directory.domainId))
  assert.equal(smallTiles.length, 4)
  const colors = new Set(smallTiles.map(t => t.domainColor))
  assert.equal(colors.size, 3, 'docker/ubuntu/centos 域色应各自独立')

  const smallTags = f.tags.filter(t => ['docker', 'ubuntu', 'centos'].includes(t.domainId))
  assert.equal(smallTags.length, 3)
  assert.deepEqual([...new Set(smallTags.map(t => t.label))], ['其他域 · 4 条'])
})

test('布局与 k 无关：sizeForK 只返回档位；buildMosaic 不接收 k，不同 stageWidth 仅改变 cols/坐标', () => {
  assert.equal(sizeForK(0.1).id, 's0')
  assert.equal(sizeForK(0.5).id, 's1')
  assert.equal(sizeForK(1.0).id, 's2')
  assert.equal(sizeForK(2.0).id, 's3')

  const wide = buildMosaic(all, knowledgeDomains, 1920)
  const narrow = buildMosaic(all, knowledgeDomains, 1024)
  assert.equal(wide.tiles.length, narrow.tiles.length)
  // 同序同 id（坐标不同但顺序一致）
  assert.deepEqual(wide.tiles.map(t => t.id), narrow.tiles.map(t => t.id))
})

test('service 小标签：连续同 serviceId 段 ≥4 才生成', () => {
  const f = buildMosaic(all, knowledgeDomains, 1440)
  // 不抛错；serviceTags 为数组；数量与全量一致时不越界
  assert.ok(Array.isArray(f.serviceTags))
  for (const s of f.serviceTags) assert.ok(s.count >= 4)
})
