import test from 'node:test'
import assert from 'node:assert/strict'
import { SCRAMBLE_CHARS, decodeDurationFor, frameText, nextScrambleChar } from '../src/components/common/decodeText.js'

// 固定随机源：总是取字符池第一个字符 'A'，让断言可重现。
const fixedRandom = () => 0

test('frameText: progress 0 全乱码，progress 1 完全等于原文', () => {
  const target = 'TRACE-8F3K2Q'
  const scrambled = frameText(target, 0, fixedRandom)
  assert.notEqual(scrambled, target)
  assert.equal([...scrambled].length, [...target].length)
  assert.equal(frameText(target, 1, fixedRandom), target)
})

test('frameText: 分隔符与空格在落定前保持稳定，宽度不跳', () => {
  const frame = frameText('ab-cd ef', 0.2, fixedRandom)
  assert.equal(frame[2], '-')
  assert.equal(frame[5], ' ')
  // 非分隔符位确实被乱码化
  assert.notEqual(frame[1], 'b')
})

test('frameText: 已落定前缀是原文，未落定后缀是乱码', () => {
  const frame = frameText('ABCDEFGH', 0.5, fixedRandom)
  assert.equal(frame.slice(0, 4), 'ABCD')
  assert.equal(frame.slice(4), 'AAAA')
})

test('frameText: 多字节字符按码点展开，不产生代理对残片', () => {
  const target = '任务-trace🎯ok'
  const frame = frameText(target, 0.4)
  assert.equal([...frame].length, [...target].length)
  assert.ok(!frame.includes('\uFFFD'))
  assert.equal(frameText(target, 1), target)
})

test('frameText: null / undefined / 空串安全返回空串', () => {
  assert.equal(frameText(null, 0.5), '')
  assert.equal(frameText(undefined, 0.5), '')
  assert.equal(frameText('', 0.5), '')
  assert.equal(frameText('', 1), '')
})

test('frameText: progress 越界夹取到 [0,1]', () => {
  assert.equal(frameText('ABC', 5), 'ABC')
  assert.notEqual(frameText('ABC', -1, fixedRandom), 'ABC')
  // NaN 视作 0（全乱码），不抛异常
  assert.notEqual(frameText('ABC', NaN, fixedRandom), 'ABC')
})

test('nextScrambleChar: 只产出字符池内字符', () => {
  for (let i = 0; i < 300; i += 1) {
    assert.ok(SCRAMBLE_CHARS.includes(nextScrambleChar()), `越界字符: ${nextScrambleChar()}`)
  }
})

test('decodeDurationFor: 夹在 240–400ms 且随长度单调不减', () => {
  assert.equal(decodeDurationFor(0), 240)
  assert.equal(decodeDurationFor(1), 240) // 160+12=172 → 被下限夹到 240
  assert.equal(decodeDurationFor(8), 256)
  assert.equal(decodeDurationFor(20), 400)
  assert.equal(decodeDurationFor(50), 400)
  assert.ok(decodeDurationFor(10) <= decodeDurationFor(20))
  assert.equal(decodeDurationFor(NaN), 240)
  assert.equal(decodeDurationFor(-5), 240)
})
