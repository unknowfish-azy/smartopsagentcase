import test from 'node:test'
import assert from 'node:assert/strict'
import { readCloudContext, validateCloudContext, cloudContextQuery, cloudResourceRoute } from '../src/views/cloud/cloudContext.js'

test('URL context is an allowlisted intent, never an executable command', () => {
  const result = readCloudContext({ cloudEnvironment: 'production', cloudCluster: 'prod-east', cloudNamespace: 'orders', cloudRange: '15m', command: 'rm -rf /' })
  assert.deepEqual(result, { environment: 'production', cluster: 'prod-east', namespace: 'orders', timeRange: '15m' })
  assert.equal(readCloudContext({ cloudCluster: 'prod;id', cloudNamespace: '../secret', cloudEnvironment: ['production'] }).cluster, '')
  assert.equal(readCloudContext({ cloudNamespace: '../secret' }).namespace, '')
  assert.equal(validateCloudContext({ ...result, namespace: 'default;id' }).length, 1)
})

test('tool and knowledge links preserve safe context without filling execution parameters', () => {
  const context = { environment: 'staging', cluster: 'team/staging', namespace: 'orders', timeRange: '1h' }
  const route = cloudResourceRoute('/tools/k8s-resources', context)
  assert.equal(route.path, '/tools/k8s-resources')
  assert.equal(route.query.namespace, undefined)
  assert.equal(route.query.cloudNamespace, 'orders')
  assert.equal(route.query.source, 'cloud-native')
  assert.equal(cloudResourceRoute('/knowledge?query=GitOps', context).query.query, 'GitOps')
  assert.equal(cloudContextQuery(context).cloudEnvironment, 'staging')
  assert.throws(() => cloudResourceRoute('https://example.com/', context))
})
