import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('migration runner processes the original ledger and the incremental admin migration', async () => {
  const source = await readFile(new URL('../migrate-local.ps1', import.meta.url), 'utf8')
  assert.ok(source.includes("'V20261002__operations_and_accounts'"))
  assert.ok(source.includes("'V002__admin_foundation'"))
  assert.ok(source.includes("'V003__registration_policy'"))
  assert.ok(source.includes("'V004__assistant_preference'"))
  assert.ok(source.includes("'V005__admin_mfa'"))
  assert.ok(source.includes("'V006__team_workspace'"))
  assert.match(source, /foreach \(\$version in \$versions\)/)
  assert.match(source, /Write-Output[^\n]*matching checksum[^\n]*\n\s*continue/)
  assert.ok(source.indexOf('& $dump') < source.indexOf('--execute=source'))
  assert.ok(source.includes('Applied migration checksum differs'))
})

test('admin migration creates only additive security tables', async () => {
  const source = await readFile(new URL('../../../backend/src/main/resources/db/migration/V002__admin_foundation.sql', import.meta.url), 'utf8')
  assert.match(source, /CREATE TABLE IF NOT EXISTS account_security/)
  assert.match(source, /CREATE TABLE IF NOT EXISTS security_audit_event/)
  assert.doesNotMatch(source, /\b(DROP|TRUNCATE|DELETE|UPDATE|ALTER)\b/i)
})

test('registration migration preserves an existing registration switch and accounts', async () => {
  const source = await readFile(new URL('../../../backend/src/main/resources/db/migration/V003__registration_policy.sql', import.meta.url), 'utf8')
  assert.match(source, /CREATE TABLE IF NOT EXISTS registration_policy/)
  assert.match(source, /INSERT INTO registration_policy[\s\S]+WHERE NOT EXISTS/)
  assert.doesNotMatch(source, /\b(DROP|TRUNCATE|DELETE|UPDATE|ALTER)\b/i)
  assert.doesNotMatch(source, /INSERT INTO app_user/)
})

test('assistant preference migration is additive and account scoped', async () => {
  const source = await readFile(new URL('../../../backend/src/main/resources/db/migration/V004__assistant_preference.sql', import.meta.url), 'utf8')
  assert.match(source, /CREATE TABLE IF NOT EXISTS assistant_preference/)
  assert.match(source, /user_id BIGINT PRIMARY KEY/)
  assert.match(source, /DEFAULT 'mini'/)
  assert.doesNotMatch(source, /\b(DROP|TRUNCATE|DELETE|UPDATE|ALTER)\b/i)
})

test('MFA migration adds only empty security tables without enrolling accounts', async () => {
  const source = await readFile(new URL('../../../backend/src/main/resources/db/migration/V005__admin_mfa.sql', import.meta.url), 'utf8')
  const tables = [...source.matchAll(/CREATE TABLE IF NOT EXISTS (\w+)/g)].map(match => match[1])
  assert.deepEqual(tables, ['account_mfa', 'account_mfa_recovery', 'account_security_notice'])
  assert.doesNotMatch(source, /\b(DROP|TRUNCATE|DELETE|UPDATE|ALTER|INSERT)\b/i)
  assert.match(source, /enabled BOOLEAN NOT NULL DEFAULT FALSE/)
  assert.match(source, /PRIMARY KEY \(user_id, code_hash\)/)
})

test('team migration starts with empty isolated tables and preserves personal resources', async () => {
  const source = await readFile(new URL('../../../backend/src/main/resources/db/migration/V006__team_workspace.sql', import.meta.url), 'utf8')
  assert.deepEqual([...source.matchAll(/CREATE TABLE IF NOT EXISTS (\w+)/g)].map(match => match[1]), ['team_workspace', 'team_member', 'team_invitation'])
  assert.doesNotMatch(source, /\b(DROP|TRUNCATE|DELETE|UPDATE|ALTER|INSERT)\b/i)
  assert.match(source, /PRIMARY KEY \(team_id, user_id\)/)
  assert.match(source, /UNIQUE KEY uq_team_invitee \(team_id, invitee_id\)/)
})
