import assert from 'node:assert/strict'
import test from 'node:test'

import { createSpeechInput, speechErrorMessage, speechRecognitionCtor } from '../src/domain/chat/speechInput.ts'

class FakeRecognition {
  constructor() { FakeRecognition.last = this }
  start() { this.onstart?.() }
  stop() { this.onend?.() }
  abort() { this.aborted = true }
  emit(results, resultIndex = 0) {
    this.onresult?.({
      resultIndex,
      results: results.map(({ transcript, isFinal }) => Object.assign([{ transcript }], { isFinal })),
    })
  }
}

function recognitionFactory() { return new FakeRecognition() }

test('unsupported browsers degrade to a no-op input', () => {
  const speech = createSpeechInput({ scope: {} })
  assert.equal(speech.supported, false)
  assert.equal(speech.start('排查'), false)
  assert.equal(speechRecognitionCtor({}), null)
  assert.equal(typeof speechRecognitionCtor({ webkitSpeechRecognition: function () {} }), 'function')
})

test('final and interim results append to the existing draft', () => {
  const states = []
  const speech = createSpeechInput({
    recognitionFactory,
    onTranscript: text => states.push(text),
    onStateChange: listening => states.push(`listening:${listening}`),
  })
  assert.equal(speech.supported, true)
  assert.equal(speech.start('排查：'), true)

  const recognition = FakeRecognition.last
  assert.equal(recognition.lang, 'zh-CN')
  assert.equal(recognition.interimResults, true)

  recognition.emit([{ transcript: 'CPU', isFinal: false }])
  recognition.emit([{ transcript: 'CPU 过载', isFinal: true }])
  recognition.emit([{ transcript: 'CPU 过载', isFinal: true }, { transcript: '，请检查', isFinal: false }], 1)
  speech.stop()

  assert.deepEqual(states, [
    'listening:true',
    '排查：CPU',
    '排查：CPU 过载',
    '排查：CPU 过载，请检查',
    '排查：CPU 过载，请检查',
    'listening:false',
  ])
})

test('pending interim text is committed when recognition ends', () => {
  const transcripts = []
  const speech = createSpeechInput({ recognitionFactory, onTranscript: text => transcripts.push(text) })
  speech.start('')
  FakeRecognition.last.emit([{ transcript: '生成巡检计划', isFinal: false }])
  speech.stop()
  assert.deepEqual(transcripts, ['生成巡检计划', '生成巡检计划'])
})

test('microphone errors surface a readable message and stop listening', () => {
  const errors = []
  const states = []
  const speech = createSpeechInput({
    recognitionFactory,
    onError: message => errors.push(message),
    onStateChange: listening => states.push(listening),
  })
  speech.start('')
  FakeRecognition.last.onerror?.({ error: 'not-allowed' })

  assert.deepEqual(states, [true, false])
  assert.match(errors[0], /麦克风权限/)
  assert.equal(speechErrorMessage('aborted'), '')
  assert.equal(speechErrorMessage('unknown-code'), '语音识别失败，请重试。')
})

test('dispose aborts recognition and ignores later events', () => {
  const transcripts = []
  const speech = createSpeechInput({ recognitionFactory, onTranscript: text => transcripts.push(text) })
  speech.start('')
  const recognition = FakeRecognition.last
  speech.dispose()
  assert.equal(recognition.aborted, true)
  recognition.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript: '迟到结果' }], { isFinal: true })] })
  assert.deepEqual(transcripts, [])
})
