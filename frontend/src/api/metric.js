import http from './http'


/**
 * 获取最新监控指标
 */
export function getLatestMetric(
    serverId
) {

    return http.get(
        `/api/servers/${serverId}/metrics/latest`
    )
}


/**
 * 获取历史监控指标
 */
export function getMetricList(
    serverId
) {

    return http.get(
        `/api/servers/${serverId}/metrics`
    )
}


/**
 * 上报监控指标
 */
export function createMetric(
    serverId,
    data
) {

    return http.post(
        `/api/servers/${serverId}/metrics`,
        data
    )
}