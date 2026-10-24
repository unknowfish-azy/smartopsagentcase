import request from '../utils/request'

export function invokeModelConnection(id, data, timeoutSeconds = 60) {
    return request({
        url: `/api/chat/connections/${id}/invoke`,
        method: 'post',
        data,
        timeout: (Math.min(300, Math.max(5, Number(timeoutSeconds) || 60)) + 5) * 1000
    })
}

export function getModelConnections() {
    return request({
        url: '/api/model-connections',
        method: 'get'
    })
}

export function createModelConnection(data) {
    return request({
        url: '/api/model-connections',
        method: 'post',
        data
    })
}

export function updateModelConnection(id, data) {
    return request({
        url: `/api/model-connections/${id}`,
        method: 'put',
        data
    })
}

export function deleteModelConnection(id) {
    return request({
        url: `/api/model-connections/${id}`,
        method: 'delete'
    })
}

export function listGatewayKeys() {
    return request({ url: '/api/model-gateway/keys', method: 'get' })
}

export function createGatewayKey(data) {
    return request({ url: '/api/model-gateway/keys', method: 'post', data })
}

export function revokeGatewayKey(id) {
    return request({ url: `/api/model-gateway/keys/${id}/revoke`, method: 'post' })
}

export function updateGatewayKeyQuota(id, data) {
    return request({ url: `/api/model-gateway/keys/${id}/quota`, method: 'put', data })
}

export function configureGatewayGroup(data) {
    return request({ url: '/api/model-gateway/groups', method: 'post', data })
}

export function listGatewayGroups() {
    return request({ url: '/api/model-gateway/groups', method: 'get' })
}

export function updateGatewayGroup(slug, data) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}`, method: 'put', data })
}

export function deleteGatewayGroup(slug) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}`, method: 'delete' })
}

export function addGatewayRoute(slug, data) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes`, method: 'post', data })
}

export function updateGatewayRoute(slug, id, data) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes/${id}`, method: 'put', data })
}

export function updateGatewayRouteStatus(slug, id, enabled) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes/${id}/status`, method: 'put', data: { enabled } })
}

export function deleteGatewayRoute(slug, id) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes/${id}`, method: 'delete' })
}

export function getGatewayAnalytics() {
    return request({ url: '/api/model-gateway/analytics', method: 'get' })
}

export function getGatewayRoutes(slug) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes`, method: 'get' })
}

export function updateGatewayGroupQuota(slug, data) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/quota`, method: 'put', data })
}
