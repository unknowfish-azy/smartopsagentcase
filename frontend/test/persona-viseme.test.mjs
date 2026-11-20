/**
 * 中文 viseme 表 + 音频主时钟时间线的纯逻辑测试。
 * 只测可单测部分：拼音 → 韵母/口型、时间线的精度标注、按毫秒取口型。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { stripTone, finalOf, visemeFromPinyin } from '../src/components/persona/chineseViseme.js'
import { visemeTimeline, timelineWeightsAt, hasCoarseRun } from '../src/components/persona/useLipSync.js'

test('拼音去声调：带调符号、数字声调、ü 都归一', () => {
  assert.equal(stripTone('hǎo'), 'hao')
  assert.equal(stripTone('zhī'), 'zhi')
  assert.equal(stripTone('lǜ'), 'lv')
  assert.equal(stripTone('nǚ'), 'nv')
  assert.equal(stripTone('nu:3'), 'nv')
  assert.equal(stripTone('  Ni-Hao  '), 'nihao')
})

test('韵母切分：零声母、j/q/x 省略 ü、最长声母优先', () => {
  assert.equal(finalOf('yi'), 'i')
  assert.equal(finalOf('wu'), 'u')
  assert.equal(finalOf('yu'), 'v')
  assert.equal(finalOf('yun'), 'vn')
  assert.equal(finalOf('juan'), 'van')
  assert.equal(finalOf('zhuan'), 'uan')
  assert.equal(finalOf('shuang'), 'uang')
  assert.equal(finalOf('er'), 'er')
})

test('韵母 → 五元音口型，鼻音韵尾单独标记', () => {
  assert.equal(visemeFromPinyin('a').viseme, 'aa')
  assert.equal(visemeFromPinyin('hao').viseme, 'aa')
  assert.equal(visemeFromPinyin('ni').viseme, 'ih')
  assert.equal(visemeFromPinyin('zhi').viseme, 'ih')
  assert.equal(visemeFromPinyin('ong').viseme, 'ou')
  assert.equal(visemeFromPinyin('jun').viseme, 'ou')
  assert.equal(visemeFromPinyin('er').viseme, 'ee')
  assert.equal(visemeFromPinyin('a').nasal, false)
  assert.equal(visemeFromPinyin('ang').nasal, true)
  assert.equal(visemeFromPinyin('ian').nasal, true)
  assert.equal(visemeFromPinyin('jun').nasal, true)
  // 纯声母/数字无法成韵，如实返回 null，由调用方退回字符近似
  assert.equal(visemeFromPinyin('q'), null)
  assert.equal(visemeFromPinyin('3'), null)
})

test('带拼音的时间线：逐字对口型，精度标为 pinyin', () => {
  const planned = visemeTimeline('你好', [
    { text: '你好', offset_ms: 0, duration_ms: 600, pinyin: 'ni hao' }
  ])
  assert.ok(planned)
  assert.equal(planned.precision, 'pinyin')
  assert.equal(planned.duration, 600)
  assert.equal(planned.entries.length, 2)
  assert.equal(planned.entries[0].primary, 'ih')
  assert.equal(planned.entries[1].primary, 'aa')
  assert.equal(planned.entries[0].start, 0)
  assert.equal(planned.entries[0].end, 300)
  assert.equal(planned.entries[1].start, 300)
})

test('拼音也接受数组，音节数不匹配时退回字符近似', () => {
  const arrayed = visemeTimeline('你好', [
    { text: '你好', offset_ms: 100, duration_ms: 400, pinyin: ['ni', 'hao'] }
  ])
  assert.equal(arrayed.precision, 'pinyin')

  const mismatch = visemeTimeline('你好呀', [
    { text: '你好呀', offset_ms: 0, duration_ms: 300, pinyin: 'ni hao' }
  ])
  assert.equal(mismatch.precision, 'char')
})

test('真实韵母优先于拼音，精度标为 phoneme', () => {
  const planned = visemeTimeline('你好', [
    { text: '你好', offset_ms: 0, duration_ms: 400, viseme: 'oh', pinyin: 'ni hao' }
  ])
  assert.equal(planned.precision, 'phoneme')
  assert.deepEqual(
    planned.entries.map((entry) => entry.primary),
    ['oh', 'oh']
  )
})

test('既无 viseme 也无 pinyin 时按字符近似，并正确跳过标点与空格', () => {
  const planned = visemeTimeline('你好，世界', [
    { text: '你好，世界', offset_ms: 0, duration_ms: 600 }
  ])
  assert.equal(planned.precision, 'char')
  assert.equal(planned.entries.length, 4)
  assert.ok(planned.entries.every((entry) => entry.precision === 'char'))
})

test('空/非法时间戳返回 null，绝不伪造', () => {
  assert.equal(visemeTimeline('你好', []), null)
  assert.equal(visemeTimeline('你好', null), null)
  assert.equal(visemeTimeline('你好', [{ text: '', offset_ms: 0, duration_ms: 100 }]), null)
  assert.equal(visemeTimeline('你好', [{ text: '你好', offset_ms: 0, duration_ms: 0 }]), null)
})

test('按毫秒取口型：命中返回音段，越界/停顿返回 null', () => {
  const planned = visemeTimeline('你好', [
    { text: '你好', offset_ms: 0, duration_ms: 600, pinyin: 'ni hao' }
  ])
  assert.equal(timelineWeightsAt(planned, 0).primary, 'ih')
  assert.equal(timelineWeightsAt(planned, 299).primary, 'ih')
  assert.equal(timelineWeightsAt(planned, 300).primary, 'aa')
  assert.equal(timelineWeightsAt(planned, 600), null)
  assert.equal(timelineWeightsAt(planned, -1), null)
  assert.equal(timelineWeightsAt(null, 0), null)
})

test('字母数字串仍被识别为需要如实说明的粗粒度片段', () => {
  assert.equal(hasCoarseRun([{ text: 'QPS', offset_ms: 0, duration_ms: 200 }]), true)
  assert.equal(hasCoarseRun([{ text: '你好', offset_ms: 0, duration_ms: 200 }]), false)
})
