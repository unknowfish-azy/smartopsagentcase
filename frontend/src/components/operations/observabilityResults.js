export function summarizePrometheusResult(response, unit = '') {
  if (response?.status !== 'success' || !Array.isArray(response.data?.result)) return []
  return response.data.result.flatMap(series => {
    const sample = series.values?.at(-1) ?? series.value
    if (!Array.isArray(sample) || sample.length < 2 || !Number.isFinite(Number(sample[0])) || !Number.isFinite(Number(sample[1]))) return []
    const labels = Object.entries(series.metric ?? {}).sort(([left], [right]) => left.localeCompare(right))
      .map(([key, value]) => `${key}=${value}`).join(', ')
    return [{ labels: labels || '无标签', value: `${sample[1]}${unit ? ` ${unit}` : ''}`, timestamp: Number(sample[0]) }]
  })
}
