import assert from 'node:assert/strict'
import test from 'node:test'
import { linuxCoreNodes } from '../../knowledge/linux/coreKnowledge.js'
import { linuxStorageNodes } from '../../knowledge/linux/storageKnowledge.js'
import { linuxFileNetworkRemoteNodes, linuxFileNetworkRemoteIncidents, linuxFileNetworkRemoteDecisionRules } from '../../knowledge/linux/fileNetworkRemoteKnowledge.js'
import { linuxSchedulerNodes, linuxSchedulerIncidents, linuxSchedulerWrongAnswers, linuxSchedulerDecisionRules } from '../../knowledge/linux/schedulerKnowledge.js'
import { searchKnowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'
import { knowledgeEntryView } from '../src/views/knowledge/knowledgeLibrary.js'

test('retrieves FD failure guidance and opens the full engineering card', () => {
  const results = searchKnowledgeEntries({ domain: 'linux', query: 'Too many open files' })
  assert.equal(results.length, 1)
  const { current } = knowledgeEntryView(results[0].id)
  assert.equal(current.id, 'LINUX-FD-002')
  assert.ok(current.content.includes('/proc/<PID>/limits'))
  assert.ok(current.content.includes('ulimit -n 只反映当前 shell'))
})

test('retrieves pipeline and service guidance through existing search', () => {
  for (const [query, id] of [['pipefail', 'LINUX-IO-002'], ['nginx启动了吗', 'LINUX-SERVICE-001'], ['xargs', 'LINUX-IO-003']]) {
    assert.ok(searchKnowledgeEntries({ query }).some(entry => entry.id === id))
  }
})

test('Linux cards have unique IDs, resolvable relations and command safety context', () => {
  const ids = new Set(linuxCoreNodes.map(node => node.id))
  assert.equal(ids.size, linuxCoreNodes.length)
  for (const node of linuxCoreNodes) {
    assert.ok(node.relatedIds.every(id => ids.has(id)))
    assert.ok(node.diagnosis.length && node.verification && node.experience)
    assert.ok(node.commands.every(command => command.risk && command.parameters && command.purpose))
  }
})

test('Linux storage pack is searchable and keeps destructive commands explicit', () => {
  const ids = new Set(linuxStorageNodes.map(node => node.id))
  assert.equal(ids.size, linuxStorageNodes.length)
  for (const node of linuxStorageNodes) {
    assert.ok(node.commands.length)
    assert.ok(node.relatedIds.every(id => ids.has(id) || linuxCoreNodes.some(core => core.id === id)))
    assert.ok(node.diagnosis.length && node.verification)
  }
  assert.ok(searchKnowledgeEntries({ service: 'storage', query: 'fstab' }).some(entry => entry.id === 'LINUX-STORAGE-002'))
  assert.ok(searchKnowledgeEntries({ query: 'df du lsof' }).some(entry => entry.id === 'LINUX-STORAGE-005'))
})

test('file, network and remote operations pack exposes linked engineering cards', () => {
  const ids = new Set([...linuxCoreNodes, ...linuxStorageNodes, ...linuxFileNetworkRemoteNodes].map(node => node.id))
  assert.equal(new Set(linuxFileNetworkRemoteNodes.map(node => node.id)).size, linuxFileNetworkRemoteNodes.length)
  for (const node of linuxFileNetworkRemoteNodes) {
    assert.ok(node.commands.every(command => command.purpose && command.parameters && command.risk))
    assert.ok(node.relatedIds.every(id => ids.has(id)))
    assert.ok(node.diagnosis.length && node.verification)
  }
  assert.ok(linuxFileNetworkRemoteIncidents.every(incident => incident.runbook.length && incident.relatedKnowledge.every(id => ids.has(id))))
  assert.ok(linuxFileNetworkRemoteDecisionRules.every(rule => rule.sequence.length && rule.defaultRisk))
  assert.ok(searchKnowledgeEntries({ service: 'file-network-remote', query: 'sshd' }).some(entry => entry.id === 'LINUX-REMOTE-001'))
  assert.ok(searchKnowledgeEntries({ query: 'rsync dry-run' }).some(entry => entry.id === 'LINUX-REMOTE-002'))
})

test('scheduler pack models jobs, contexts, overlap and verification', () => {
  const allIds = new Set([...linuxCoreNodes, ...linuxStorageNodes, ...linuxFileNetworkRemoteNodes, ...linuxSchedulerNodes].map(node => node.id))
  assert.equal(new Set(linuxSchedulerNodes.map(node => node.id)).size, linuxSchedulerNodes.length)
  for (const node of linuxSchedulerNodes) {
    assert.ok(node.commands.every(command => command.purpose && command.risk && command.parameters))
    assert.ok(node.relatedIds.every(id => allIds.has(id)))
    assert.ok(node.diagnosis.length && node.verification)
  }
  assert.ok(linuxSchedulerIncidents.length >= 5)
  assert.ok(linuxSchedulerWrongAnswers.some(item => item.id === 'WRONG-CRON-DAEMON'))
  assert.ok(linuxSchedulerDecisionRules[0].sequence.includes('evaluate overlap'))
  assert.ok(searchKnowledgeEntries({ service: 'scheduler', query: 'flock' }).some(entry => entry.id === 'LINUX-SCHED-004'))
  assert.ok(searchKnowledgeEntries({ query: 'systemd timer' }).some(entry => entry.id === 'LINUX-SCHED-005'))
})
