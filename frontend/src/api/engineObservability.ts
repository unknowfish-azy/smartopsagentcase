/**
 * 引擎可观测大屏 API（T39）。
 * 只读真实聚合端点；不接任何 demo/mock 数据源。
 */
import { get } from '../utils/request'

export interface EngineState {
  id: string
  name: string
  status: 'NO_DATA' | 'RUNNING' | 'STALLED' | 'ERROR' | 'NOT_RUN'
  lastEventAtEpochSec: number | null
  lastEventAtText: string
  ageSec: number
  expectedPeriodSec: number
  eventCount: number
  lastEventSummary: string
  detail: string
}

export interface EngineSnapshot {
  generatedAt: number
  engines: EngineState[]
}

export interface EngineEvent {
  at: number | null
  kind: string
  summary: string
}

/** 全部引擎运行时快照。响应体为 ApiResponse<EngineSnapshot>。 */
export function getEngineSnapshot(): Promise<{ data?: { code: number; data: EngineSnapshot } }> {
  return get('/api/engine-observability/snapshot')
}

/** 指定引擎最近 N 条真实事件。 */
export function getEngineEventStream(engine: string, limit = 50) {
  return get(`/api/engine-observability/event-stream?engine=${encodeURIComponent(engine)}&limit=${limit}`)
}
