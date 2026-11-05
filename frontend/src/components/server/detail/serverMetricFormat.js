/* ===================================
   服务器详情/指标 纯格式化函数
   =================================== */

export function normalizePercentage(value) {
  if (value === null || value === undefined) {
    return 0
  }
  const number = Number(value)
  if (Number.isNaN(number)) {
    return 0
  }
  return Math.min(100, Math.max(0, number))
}

export function getProgressStatus(value) {
  if (value === null || value === undefined) {
    return undefined
  }
  const number = Number(value)
  if (number >= 90) {
    return 'exception'
  }
  if (number >= 80) {
    return 'warning'
  }
  return 'success'
}

export function getMetricLevel(value) {
  if (value === null || value === undefined) {
    return '暂无数据'
  }
  const number = Number(value)
  if (number >= 90) {
    return '严重异常'
  }
  if (number >= 80) {
    return '需要关注'
  }
  return '运行正常'
}

export function formatPercent(value) {
  if (value === null || value === undefined) {
    return '-'
  }
  return `${Number(value).toFixed(1)}%`
}

export function formatNumber(value) {
  if (value === null || value === undefined) {
    return '-'
  }
  return Number(value).toFixed(2)
}

export function formatDate(value) {
  if (!value) {
    return '-'
  }
  return new Date(value).toLocaleString('zh-CN')
}

export function metricNumberClass(value) {
  if (value === null || value === undefined) {
    return ''
  }
  const number = Number(value)
  if (number >= 90) {
    return 'metric-critical'
  }
  if (number >= 80) {
    return 'metric-warning'
  }
  return 'metric-normal'
}

export function metricStatusLabel(status) {
  switch (status) {
    case 'NORMAL':
      return '正常'
    case 'WARNING':
      return '告警'
    case 'CRITICAL':
      return '严重'
    default:
      return '未知'
  }
}
