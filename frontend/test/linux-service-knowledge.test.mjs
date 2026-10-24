import test from 'node:test'
import assert from 'node:assert/strict'
import {
  linuxServiceEntries,
  linuxServiceIncidents,
  linuxServiceRunbooks,
  linuxServiceQuestions,
  linuxServiceWrongAnswers,
  linuxServiceRules,
  linuxServiceSchema,
  serviceEvidencePath
} from '../src/views/knowledge/knowledgeCatalog.js'

test('indexes FTP, NFS and SSH service evidence chains', () => {
  for (const [query, id] of [
    ['vsftpd', 'service.ftp.vsftpd'],
    ['passive data channel', 'service.ftp.passive_mode'],
    ['root_squash', 'service.nfs.root_squash'],
    ['showmount -e', 'service.nfs.command.showmount'],
    ['authorized_keys', 'service.ssh.public_key_auth'],
    ['Jump Host', 'service.ssh.bastion']
  ]) {
    assert.ok(linuxServiceEntries.some(entry => entry.id === id && `${entry.title} ${entry.content} ${entry.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase())), id)
  }
})

test('service pack preserves unified schema and safe command boundaries', () => {
  assert.ok(linuxServiceEntries.length >= 35)
  const ids = new Set(linuxServiceEntries.map(entry => entry.id))
  assert.equal(ids.size, linuxServiceEntries.length)
  for (const entry of linuxServiceEntries) {
    assert.equal(entry.packId, 'linux-services')
    assert.equal(entry.executionAllowed, false)
    assert.equal(entry.provenance.attachmentVerified, false)
    assert.ok(entry.relatedIds.every(id => ids.has(id) || id.startsWith('network.') || id.startsWith('service.')))
    for (const command of entry.commands || []) {
      assert.equal(command.executionAllowed, false)
      assert.ok(command.risk_level && command.verification)
      if (!command.read_only) assert.ok(command.requires_preview && command.approval_required)
    }
  }
  assert.deepEqual(Object.keys(linuxServiceSchema), ['service', 'network', 'authentication', 'filesystem', 'security', 'dependencies', 'verification'])
  assert.ok(linuxServiceSchema.service.fields.includes('systemd_unit'))
})

test('service diagnosis chooses evidence by symptom instead of claiming health from systemd', () => {
  assert.deepEqual(serviceEvidencePath('vsftpd', 'client can login but upload fails'), ['service', 'process', 'listener', 'network', 'authentication', 'config', 'filesystem', 'security', 'functional'])
  assert.deepEqual(serviceEvidencePath('sshd', 'connection timeout'), ['service', 'process', 'listener', 'network', 'security', 'functional'])
  assert.deepEqual(serviceEvidencePath('sshd', 'public key authentication fails'), ['service', 'process', 'listener', 'authentication', 'config', 'filesystem', 'security', 'functional'])
})

test('service pack models incidents, runbooks, wrong answers and risk rules', () => {
  for (const id of ['INC-LINUX-SERVICE-001', 'INC-LINUX-SERVICE-004', 'INC-FILE-003', 'INC-NFS-004', 'INC-SSH-003']) assert.ok(linuxServiceIncidents.some(item => item.id === id), id)
  assert.ok(linuxServiceRunbooks.some(item => item.id === 'RB-SERVICE-001' && item.steps.includes('verify functional operation')))
  assert.ok(linuxServiceRunbooks.some(item => item.id === 'RB-SSH-002' && item.steps.includes('test a secondary SSH session')))
  assert.ok(linuxServiceQuestions.some(item => item.category === 'FTP_DATA_CHANNEL'))
  assert.ok(linuxServiceWrongAnswers.some(item => item.wrong_reason_type === 'NFS_SECURITY_ESCALATION'))
  assert.ok(linuxServiceRules.some(item => item.id === 'RULE-SERVICE-001' && item.sequence.includes('functional operation')))
})
