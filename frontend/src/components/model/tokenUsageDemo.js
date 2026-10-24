// Explicitly fictional fixture. Never submit this report to the analytics API.
export function createTokenUsageDemo() {
  const calls = [20, 25, 30, 40, 35, 50, 50]
  const successes = [19, 24, 29, 38, 34, 49, 49]
  const latency = [2400, 2100, 1900, 2200, 1700, 1500, 1400]
  const totals = [12000, 15000, 18000, 24000, 21000, 30000, 30000]
  const daily = totals.map((total, index) => ({
    date: `2026-09-${19 + index}`, calls: calls[index], successes: successes[index],
    failures: calls[index] - successes[index], pendingCalls: 0, unknownUsageCalls: 0,
    knownTokens: total, inputTokens: total * 2 / 3, outputTokens: total / 3,
    successRate: successes[index] / calls[index] * 100, averageLatencyMs: latency[index]
  }))
  const summary = {
    calls: 250, successes: 242, failures: 8, pendingCalls: 0, unknownUsageCalls: 0,
    knownTokens: 150000, inputTokens: 100000, outputTokens: 50000, successRate: 96.8,
    averageLatencyMs: daily.reduce((sum, day) => sum + day.averageLatencyMs * day.successes, 0) / 242
  }
  return {
    month: '2026-09', timezone: 'UTC', summary, daily,
    // 三个模型分区之和必须等于 summary（150,000 / 100,000 / 50,000；250 次调用、242 成功）
    models: [
      { connectionId: 'demo-nginx', modelName: 'Nginx 排障助手（虚构）', calls: 150, successes: 145, failures: 5, pendingCalls: 0, unknownUsageCalls: 0, knownTokens: 90000, inputTokens: 60000, outputTokens: 30000, successRate: 96.7, averageLatencyMs: 1720 },
      { connectionId: 'demo-vector', modelName: '向量检索服务（虚构）', calls: 70, successes: 67, failures: 3, pendingCalls: 0, unknownUsageCalls: 0, knownTokens: 45000, inputTokens: 30000, outputTokens: 15000, successRate: 95.7, averageLatencyMs: 320 },
      { connectionId: 'demo-log', modelName: '日志解析器（虚构）', calls: 30, successes: 30, failures: 0, pendingCalls: 0, unknownUsageCalls: 0, knownTokens: 15000, inputTokens: 10000, outputTokens: 5000, successRate: 100, averageLatencyMs: 180 }
    ],
    budget: 500000, budgetUsedTokens: 150000, budgetUnknownCalls: 0
  }
}
