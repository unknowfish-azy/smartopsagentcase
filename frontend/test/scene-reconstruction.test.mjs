// 实景还原数据层单测：类型识别、大小上限、覆盖度判定、不伪造进度。
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  MAX_ASSET_BYTES,
  RECONSTRUCTION_STAGES,
  classifyScanAsset,
  createReconstructionJob,
  fileExtension,
  formatBytes,
  startReconstruction,
  summariseCoverage
} from '../src/domain/reconstruction/sceneReconstruction.js'

test('fileExtension：大小写归一，无扩展名返回空串', () => {
  assert.equal(fileExtension('hall.PLY'), 'ply')
  assert.equal(fileExtension('a.b.glb'), 'glb')
  assert.equal(fileExtension('noext'), '')
  assert.equal(fileExtension('trailing.'), '')
  assert.equal(fileExtension(''), '')
})

test('classifyScanAsset：识别点云/网格/影像/压缩包', () => {
  assert.equal(classifyScanAsset('hall.ply').kind, 'point-cloud')
  assert.equal(classifyScanAsset('hall.las').ok, true)
  assert.equal(classifyScanAsset('rack.glb').kind, 'mesh')
  assert.equal(classifyScanAsset('photo.JPG').kind, 'image-set')
  assert.equal(classifyScanAsset('batch.zip').kind, 'archive')
})

test('classifyScanAsset：不支持或无扩展名时给出原因', () => {
  const txt = classifyScanAsset('notes.txt')
  assert.equal(txt.ok, false)
  assert.equal(txt.kind, 'unknown')
  assert.ok(txt.reason.includes('.txt'))

  const noExt = classifyScanAsset('scanfile')
  assert.equal(noExt.ok, false)
  assert.ok(noExt.reason.length > 0)
})

test('formatBytes：B/KB/MB/GB 进位', () => {
  assert.equal(formatBytes(0), '0 B')
  assert.equal(formatBytes(512), '512 B')
  assert.equal(formatBytes(2048), '2.0 KB')
  assert.equal(formatBytes(5 * 1024 * 1024), '5.0 MB')
  assert.equal(formatBytes(Number.NaN), '0 B')
})

test('summariseCoverage：有几何才可还原，只有影像要提示补点云', () => {
  assert.equal(summariseCoverage([]).ready, false)
  assert.equal(summariseCoverage([{ kind: 'point-cloud' }]).ready, true)
  assert.equal(summariseCoverage([{ kind: 'mesh' }]).ready, true)

  const imageryOnly = summariseCoverage([{ kind: 'image-set' }])
  assert.equal(imageryOnly.ready, false)
  assert.ok(imageryOnly.reason.includes('缺少几何来源'))
})

test('createReconstructionJob：过滤不支持文件与超大文件', () => {
  const job = createReconstructionJob([
    { name: 'hall.ply', size: 1024 },
    { name: 'rack.glb', size: 2048 },
    { name: 'notes.txt', size: 10 },
    { name: 'huge.las', size: MAX_ASSET_BYTES + 1 }
  ])

  assert.equal(job.assets.length, 2)
  assert.equal(job.rejected.length, 2)
  assert.equal(job.totalBytes, 3072)
  assert.equal(job.status, 'READY')
  assert.equal(job.coverage.ready, true)
  assert.ok(job.stages.every(stage => stage.status === 'pending'))
  assert.equal(job.stages.length, RECONSTRUCTION_STAGES.length)
})

test('createReconstructionJob：空列表为 EMPTY', () => {
  const job = createReconstructionJob([])
  assert.equal(job.status, 'EMPTY')
  assert.equal(job.assets.length, 0)
  assert.deepEqual(job.rejected, [])
})

test('startReconstruction：引擎未接入时如实 BLOCKED，不伪造已完成', () => {
  const job = createReconstructionJob([{ name: 'hall.ply', size: 1024 }])
  const started = startReconstruction(job)

  assert.equal(started.status, 'BLOCKED')
  assert.ok(started.notice.includes('尚未接入'))
  assert.equal(started.stages[0].status, 'blocked')
  assert.ok(started.stages.slice(1).every(stage => stage.status === 'pending'))
  assert.ok(!started.stages.some(stage => stage.status === 'done'))

  const empty = startReconstruction(createReconstructionJob([]))
  assert.equal(empty.status, 'EMPTY')

  const imageryOnly = startReconstruction(createReconstructionJob([{ name: 'a.jpg', size: 10 }]))
  assert.equal(imageryOnly.status, 'BLOCKED')
  assert.ok(imageryOnly.notice.includes('几何来源'))
})
