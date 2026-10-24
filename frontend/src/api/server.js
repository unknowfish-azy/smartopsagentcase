import http from './http'


/**
 * 获取服务器列表
 */
export function getServers() {

    return http.get(
        '/api/servers'
    )
}


/**
 * 获取服务器详情
 */
export function getServer(id) {

    return http.get(
        `/api/servers/${id}`
    )
}


/**
 * 创建服务器
 */
export function createServer(data) {

    return http.post(
        '/api/servers',
        data
    )
}


/**
 * 修改服务器
 */
export function updateServer(
    id,
    data
) {

    return http.put(
        `/api/servers/${id}`,
        data
    )
}


/**
 * 删除服务器
 */
export function deleteServer(id) {

    return http.delete(
        `/api/servers/${id}`
    )
}