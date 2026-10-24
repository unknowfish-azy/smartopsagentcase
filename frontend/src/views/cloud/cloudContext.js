export const cloudEnvironments = { unspecified: '未指定环境', development: '开发环境', staging: '预发布环境', production: '生产环境' }
const clusterPattern = /^[a-zA-Z0-9][a-zA-Z0-9_.:/@-]{0,127}$/
const namespacePattern = /^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$/
const ranges = ['15m', '1h', '6h']
const scalar = value => typeof value === 'string' ? value : ''

export function readCloudContext(query = {}) {
  const environment = scalar(query.cloudEnvironment)
  const cluster = scalar(query.cloudCluster), namespace = scalar(query.cloudNamespace)
  return {
    environment: Object.hasOwn(cloudEnvironments, environment) ? environment : 'unspecified',
    cluster: clusterPattern.test(cluster) ? cluster : '',
    namespace: namespacePattern.test(namespace) ? namespace : '',
    timeRange: ranges.includes(query.cloudRange) ? query.cloudRange : '1h'
  }
}

export function validateCloudContext(context) {
  const errors = []
  if (!Object.hasOwn(cloudEnvironments, context.environment)) errors.push('请选择有效环境。')
  if (context.cluster && !clusterPattern.test(context.cluster)) errors.push('Context 仅允许字母、数字及 . _ : / @ -，最多 128 字符。')
  if (context.namespace && !namespacePattern.test(context.namespace)) errors.push('Namespace 必须为有效的小写 DNS 标签，最多 63 字符。')
  if (!ranges.includes(context.timeRange)) errors.push('请选择有效时间范围。')
  return errors
}

export function cloudContextQuery(context) {
  if (validateCloudContext(context).length) throw new Error('Invalid cloud context')
  return { source: 'cloud-native', cloudEnvironment: context.environment, cloudCluster: context.cluster, cloudNamespace: context.namespace, cloudRange: context.timeRange }
}

export function cloudResourceRoute(destination, context) {
  if (!/^\/(tools\/[-a-z0-9]+|knowledge)(\?|$)/.test(destination)) throw new Error('Unsupported cloud destination')
  const target = new URL(destination, 'http://local.invalid')
  return { path: target.pathname, query: { ...Object.fromEntries(target.searchParams), ...cloudContextQuery(context) } }
}
