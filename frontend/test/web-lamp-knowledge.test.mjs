import assert from 'node:assert/strict'
import test from 'node:test'

import {
  webLampEntries,
  webLampIncidents,
  webLampRunbooks,
  webLampQuestions,
  webLampWrongAnswers,
  webLampRules,
  webLampSchema,
  parseServiceUrl,
  webEvidencePath,
  verificationLevelForEvidence
} from '../src/views/knowledge/knowledgeCatalog.js'

test('parses HTTP and FTP service URLs without confusing URL with protocol', () => {
  assert.deepEqual(parseServiceUrl('http://www.example.test:8080/a/index.php'), {
    scheme: 'http', host: 'www.example.test', port: 8080, path: '/a/index.php'
  })
  assert.deepEqual(parseServiceUrl('ftp://192.0.2.10/1.txt'), {
    scheme: 'ftp', host: '192.0.2.10', port: 21, path: '/1.txt'
  })
})

test('selects web evidence paths from symptom layer instead of prescribing restart', () => {
  assert.deepEqual(webEvidencePath('dns failure'), ['name_resolution'])
  assert.deepEqual(webEvidencePath('tcp timeout'), ['name_resolution', 'route', 'firewall', 'listener'])
  assert.deepEqual(webEvidencePath(403), ['virtual_host', 'directory_authorization', 'filesystem_permission', 'ownership', 'selinux'])
  assert.deepEqual(webEvidencePath(404), ['host_header', 'virtual_host', 'uri', 'document_root', 'file', 'rewrite', 'application_routing'])
  assert.deepEqual(webEvidencePath(500), ['apache_log', 'php_log', 'application_log', 'php_runtime', 'php_extension', 'filesystem_permission', 'database'])
  assert.deepEqual(webEvidencePath(504), ['upstream', 'timeout', 'proxy_or_gateway', 'application'])
  assert.deepEqual(webEvidencePath('static works dynamic fails'), ['php_runtime', 'application', 'database'])
})

test('models verification levels from process through business transaction', () => {
  assert.equal(verificationLevelForEvidence('process'), 'L0')
  assert.equal(verificationLevelForEvidence('listener'), 'L1')
  assert.equal(verificationLevelForEvidence('http status'), 'L2')
  assert.equal(verificationLevelForEvidence('expected content'), 'L3')
  assert.equal(verificationLevelForEvidence('application health'), 'L4')
  assert.equal(verificationLevelForEvidence('business transaction'), 'L5')
})

test('indexes the Web/LAMP pack and preserves safe execution boundaries', () => {
  assert.ok(webLampEntries.length >= 55)
  const ids = new Set(webLampEntries.map(entry => entry.id))
  assert.equal(ids.size, webLampEntries.length)
  for (const entry of webLampEntries) {
    assert.equal(entry.packId, 'web-lamp')
    assert.equal(entry.executionAllowed, false)
    assert.equal(entry.provenance.attachmentVerified, false)
    for (const command of entry.commands || []) {
      assert.equal(command.executionAllowed, false)
      assert.ok(command.risk_level)
      assert.ok(command.verification)
      if (command.read_only !== true) {
        assert.equal(command.requires_preview, true)
        assert.equal(command.approval_required, true)
      }
    }
  }
  assert.ok(webLampEntries.some(entry => entry.id === 'web.apache.httpd'))
  assert.ok(webLampEntries.some(entry => entry.id === 'web.apache.virtual_host'))
  assert.ok(webLampEntries.some(entry => entry.id === 'web.php.runtime'))
  assert.ok(webLampEntries.some(entry => entry.id === 'web.database.application_connectivity'))
  assert.ok(webLampEntries.some(entry => entry.id === 'web.application.large_upload'))
  assert.ok(webLampEntries.some(entry => entry.id === 'web.security.chmod_777' && entry.risk === 'HIGH'))
  assert.ok(webLampEntries.some(entry => entry.id === 'web.security.selinux' && entry.tags.includes('LAB_SHORTCUT')))
  assert.equal(webLampSchema.verification.fields.includes('business_result'), true)
})

test('contains required Web incidents, runbooks, questions, wrong answers and rules', () => {
  for (let index = 1; index <= 16; index += 1) {
    assert.ok(webLampIncidents.some(item => item.id === `INC-WEB-${String(index).padStart(3, '0')}`))
  }
  for (const id of ['RUNBOOK-WEB-STATIC-001', 'RUNBOOK-WEB-VHOST-001', 'RUNBOOK-WEB-403-001', 'RUNBOOK-WEB-404-001', 'RUNBOOK-WEB-500-001', 'RUNBOOK-LAMP-001']) {
    assert.ok(webLampRunbooks.some(item => item.id === id), id)
  }
  assert.ok(webLampQuestions.some(item => item.category === 'HTTP_500'))
  assert.ok(webLampWrongAnswers.some(item => item.id === 'WA-WEB-001'))
  assert.ok(webLampWrongAnswers.some(item => item.id === 'WA-WEB-013' && item.risk === 'HIGH'))
  assert.ok(webLampRules.some(item => item.id === 'RULE-WEB-001'))
  assert.ok(webLampRules.some(item => item.id === 'RULE-WEB-013' && item.rule.includes('chmod 777')))
})

test('global catalog IDs remain unique and Web content is searchable', () => {
  const allIds = webLampEntries.map(entry => entry.id)
  assert.equal(new Set(allIds).size, allIds.length)
  assert.ok(webLampEntries.some(entry => `${entry.title} ${entry.content} ${entry.tags.join(' ')}`.toLowerCase().includes('httpd -t')))
  assert.ok(webLampEntries.some(entry => `${entry.title} ${entry.content}`.toLowerCase().includes('root cause')))
})
