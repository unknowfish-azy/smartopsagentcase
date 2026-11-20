/**
 * 流式分句：切句规则 + askAssistant 边收边回调。
 */
import test from 'node:test'
import assert from 'node:assert/strict'
import { createSentenceSplitter, splitSentences } from '../src/components/persona/sentenceStream.js'
import { askAssistant } from '../src/components/persona/personaVoice.js'

test('句末标点立即成句，半句留在缓冲区', () => {
  const splitter = createSentenceSplitter()
  assert.deepEqual(splitter.push('你好'), [])
  assert.deepEqual(splitter.push('，欢迎来到景区。'), ['你好，欢迎来到景区。'])
  assert.deepEqual(splitter.push('下一'), [])
  assert.deepEqual(splitter.flush(), ['下一'])
})

test('长句在逗号处提前切，避免首句过长', () => {
  const splitter = createSentenceSplitter({ softChars: 8 })
  assert.deepEqual(splitter.push('这道题的答案其实是这样的，'), ['这道题的答案其实是这样的，'])
  assert.deepEqual(splitter.push('请跟我来。'), ['请跟我来。'])
})

test('超过 maxChars 无标点也强制切，不把超长句闷在缓冲区', () => {
  const splitter = createSentenceSplitter({ maxChars: 6 })
  assert.deepEqual(splitter.push('一二三四五六七'), ['一二三四五六'])
  assert.deepEqual(splitter.flush(), ['七'])
})

test('不按小数点切分，数字与编号保持完整', () => {
  assert.deepEqual(splitSplit('海拔3.5米，温度A-07。'), ['海拔3.5米，温度A-07。'])
})

test('纯标点 token 不会变成空气句子', () => {
  const splitter = createSentenceSplitter()
  assert.deepEqual(splitter.push('你好'), [])
  assert.deepEqual(splitter.push('。'), ['你好。'])
  // 上一句已经发出后，流式 token 单独补来的标点直接丢弃
  assert.deepEqual(splitter.push('。'), [])
  assert.deepEqual(splitter.push('——！'), [])
  assert.deepEqual(splitter.flush(), [])
})

test('整段文本切句：无标点尾巴通过 flush 补出', () => {
  assert.deepEqual(splitSentences('你好。今天天气不错！还有'), ['你好。', '今天天气不错！', '还有'])
  assert.deepEqual(splitSentences('   '), [])
})

test('askAssistant 边收 token 边回调完整句子，并保留整段文本', async () => {
  const sentences = []
  const streamChat = async (prompt, handlers) => {
    handlers.onToken('你好。')
    handlers.onToken('今天')
    handlers.onToken('天气不错！')
    handlers.onToken('还有')
    handlers.onDone({})
  }
  const result = await askAssistant('问一句', {
    streamChat,
    fetchToken: async () => ({ runToken: 'run-1' }),
    onSentence: (sentence) => sentences.push(sentence)
  })
  assert.equal(result.ok, true)
  assert.equal(result.text, '你好。今天天气不错！还有')
  assert.deepEqual(sentences, ['你好。', '今天天气不错！', '还有'])
})

test('onSentence 抛错不影响回复聚合', async () => {
  const streamChat = async (prompt, handlers) => {
    handlers.onToken('你好。')
    handlers.onDone({})
  }
  const result = await askAssistant('问一句', {
    streamChat,
    fetchToken: async () => ({ runToken: 'run-1' }),
    onSentence: () => {
      throw new Error('播放器崩了')
    }
  })
  assert.equal(result.ok, true)
  assert.equal(result.text, '你好。')
})

// 用 softChars 调大确保不会把 3.5 前后的逗号之外再切
function splitSplit(text) {
  return splitSentences(text)
}
