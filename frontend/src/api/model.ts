import request from '../utils/request'

export function invokeModelConnection(id: any, data: any,  timeoutSeconds = 60) {
    return request({
        url: `/api/chat/connections/${id}/invoke`,
        method: 'post',
        data,
        timeout: (Math.min(300, Math.max(5, Number(timeoutSeconds) || 60)) + 5) * 1000
    })
}

export function getModelConnections() : any {
    return request({
        url: '/api/model-connections',
        method: 'get'
    })
}

export function createModelConnection(data: any) {
    return request({
        url: '/api/model-connections',
        method: 'post',
        data
    })
}

export function updateModelConnection(id: any, data: any) {
    return request({
        url: `/api/model-connections/${id}`,
        method: 'put',
        data
    })
}

export function deleteModelConnection(id: any) {
    return request({
        url: `/api/model-connections/${id}`,
        method: 'delete'
    })
}

export function listGatewayKeys() : any {
    return request({ url: '/api/model-gateway/keys', method: 'get' })
}

export function createGatewayKey(data: any) {
    return request({ url: '/api/model-gateway/keys', method: 'post', data })
}

export function revokeGatewayKey(id: any) {
    return request({ url: `/api/model-gateway/keys/${id}/revoke`, method: 'post' })
}

export function updateGatewayKeyQuota(id: any, data: any) {
    return request({ url: `/api/model-gateway/keys/${id}/quota`, method: 'put', data })
}

export function configureGatewayGroup(data: any) {
    return request({ url: '/api/model-gateway/groups', method: 'post', data })
}

export function listGatewayGroups() : any {
    return request({ url: '/api/model-gateway/groups', method: 'get' })
}

export function updateGatewayGroup(slug: any, data: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}`, method: 'put', data })
}

export function deleteGatewayGroup(slug: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}`, method: 'delete' })
}

export function addGatewayRoute(slug: any, data: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes`, method: 'post', data })
}

export function updateGatewayRoute(slug: any, id: any, data: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes/${id}`, method: 'put', data })
}

export function updateGatewayRouteStatus(slug: any, id: any, enabled: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes/${id}/status`, method: 'put', data: { enabled } })
}

export function deleteGatewayRoute(slug: any, id: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes/${id}`, method: 'delete' })
}

export function getGatewayAnalytics() : any {
    return request({ url: '/api/model-gateway/analytics', method: 'get' })
}

export function getGatewayRoutes(slug: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/routes`, method: 'get' })
}

export function updateGatewayGroupQuota(slug: any, data: any) {
    return request({ url: `/api/model-gateway/groups/${encodeURIComponent(slug)}/quota`, method: 'put', data })
}

export function getGatewayCurrentConfig() : any {
    return request({ url: '/api/model-gateway/config', method: 'get' })
}

export function listGatewayConfigVersions(limit = 50) : any {
    return request({ url: '/api/admin/model-gateway/config/versions', method: 'get', params: { limit } })
}

export function getGatewayConfigVersion(id: any) : any {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}`, method: 'get' })
}

export function createGatewayConfigDraft(data: any) {
    return request({ url: '/api/admin/model-gateway/config/versions', method: 'post', data })
}

export function activateGatewayConfigVersion(id: any, percent = 100) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}/activate`, method: 'post', data: { percent } })
}

export function submitGatewayConfigVersion(id: any, data: any) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}/submit`, method: 'post', data })
}

export function approveGatewayConfigVersion(id: any, data: any) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}/approve`, method: 'post', data })
}

export function rejectGatewayConfigVersion(id: any, data: any) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}/reject`, method: 'post', data })
}

export function promoteGatewayConfigVersion(id: any) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}/promote`, method: 'post' })
}

export function compareGatewayConfigVersion(id: any, minutes = 60) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}/compare`, method: 'get', params: { minutes } })
}

export function rollbackGatewayConfigVersion(id: any, data: any) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}/rollback`, method: 'post', data })
}

export function deleteGatewayConfigVersion(id: any) {
    return request({ url: `/api/admin/model-gateway/config/versions/${id}`, method: 'delete' })
}
