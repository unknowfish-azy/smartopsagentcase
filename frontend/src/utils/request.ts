import axios from 'axios'

/**
 * =========================================================
 * SmartOpsAgent 统一 HTTP 请求工具
 * =========================================================
 *
 * 负责：
 * 1. Axios 实例
 * 2. 请求拦截
 * 3. 响应拦截
 * 4. Token 预留
 * 5. 统一错误处理
 * 6. 统一超时处理
 *
 */


/**
 * API 基础地址
 *
 * 生产环境：
 * 通过 .env.production 配置
 */
const baseURL =
    import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL || '')


/**
 * Axios 实例
 */
const request = axios.create({

    baseURL,

    withCredentials: true,

    timeout: 15000,

    headers: {
        'Content-Type': 'application/json'
    }
})


/**
 * =========================================================
 * 请求拦截器
 * =========================================================
 */
request.interceptors.request.use(

    config => {

        /**
         * 关联 ID：让浏览器、Java MDC 与服务日志使用同一个请求编号。
         * 仅作为标签，不携带身份或凭据。
         */
        if (!config.headers['X-Request-ID']) {
            config.headers['X-Request-ID'] = crypto.randomUUID()
        }

        /**
         * 后续 JWT 接入位置
         *
         * 例如：
         *
         * const token =
         *   localStorage.getItem('smartops_token')
         *
         * if (token) {
         *   config.headers.Authorization =
         *     `Bearer ${token}`
         * }
         */

        return config
    },

    error => {
        return Promise.reject(error)
    }
)


/**
 * =========================================================
 * 响应拦截器
 * =========================================================
 */
request.interceptors.response.use(

    response => {

        const data = response.data

        /**
         * SmartOpsAgent 后端统一格式：
         *
         * {
         *   code: 200,
         *   message: "success",
         *   data: {}
         * }
         */

        if (
            data &&
            typeof data === 'object' &&
            Object.prototype.hasOwnProperty.call(
                data,
                'code'
            )
        ) {

            /**
             * 业务成功
             */
            if (data.code === 200) {
                return data
            }


            /**
             * 业务失败
             */
            return Promise.reject(
                createRequestError(
                    data.message ||
                    '业务请求失败',
                    {
                        type: 'BUSINESS_ERROR',
                        code: data.code,
                        response
                    }
                )
            )
        }


        /**
         * 对于没有统一包装的接口，
         * 直接返回原始响应数据。
         *
         * 例如：
         * 第三方接口
         * 文件上传
         * 特殊监控接口
         */
        return data
    },

    error => {

        /**
         * HTTP错误
         */
        if (error.response) {

            const status =
                error.response.status


            switch (status) {

                case 400:
                    return Promise.reject(
                        createRequestError(
                            error.response.data?.message || '请求参数错误',
                            {
                                type: 'HTTP_ERROR',
                                status,
                                response: error.response
                            }
                        )
                    )


                case 401:
                    if (!error.config?.url?.startsWith('/api/auth/')) window.dispatchEvent(new Event('smartops:unauthorized'))

                    return Promise.reject(
                        createRequestError(
                            error.response.data?.message || '登录状态已失效',
                            {
                                type: 'UNAUTHORIZED',
                                status,
                                response: error.response
                            }
                        )
                    )


                case 403:
                    return Promise.reject(
                        createRequestError(
                            error.response.data?.message || '没有权限执行此操作',
                            {
                                type: 'FORBIDDEN',
                                status,
                                response: error.response
                            }
                        )
                    )


                case 404:
                    return Promise.reject(
                        createRequestError(
                            '请求的资源不存在',
                            {
                                type: 'NOT_FOUND',
                                status,
                                response: error.response
                            }
                        )
                    )


                case 409:
                    return Promise.reject(
                        createRequestError(
                            error.response.data?.message || '请求发生冲突',
                            {
                                type: 'CONFLICT',
                                status,
                                response: error.response
                            }
                        )
                    )


                case 428:
                    return Promise.reject(
                        createRequestError(error.response.data?.message || '请重新完成人机验证', {
                            type: 'HUMAN_VERIFICATION_REQUIRED', status, response: error.response
                        })
                    )

                case 429:
                    return Promise.reject(
                        createRequestError(error.response.data?.message || '请求过于频繁，请稍后再试', {
                            type: 'RATE_LIMITED', status, response: error.response
                        })
                    )

                case 422:
                    return Promise.reject(
                        createRequestError(
                            '请求参数无法处理',
                            {
                                type: 'VALIDATION_ERROR',
                                status,
                                response: error.response
                            }
                        )
                    )


                case 500:
                    return Promise.reject(
                        createRequestError(
                            '服务器内部错误',
                            {
                                type: 'SERVER_ERROR',
                                status,
                                response: error.response
                            }
                        )
                    )


                case 502:
                case 503:
                case 504:
                    return Promise.reject(
                        createRequestError(
                            error.response.data?.message || '服务暂时不可用，请稍后重试',
                            {
                                type: 'SERVICE_UNAVAILABLE',
                                status,
                                response: error.response
                            }
                        )
                    )


                default:
                    return Promise.reject(
                        createRequestError(
                            `请求失败（HTTP ${status}）`,
                            {
                                type: 'HTTP_ERROR',
                                status,
                                response: error.response
                            }
                        )
                    )
            }
        }


        /**
         * 请求已发出，但没有收到服务器响应。
         */
        if (error.request) {

            return Promise.reject(
                createRequestError(
                    '无法连接服务器，请检查后端服务是否启动',
                    {
                        type: 'NETWORK_ERROR',
                        originalError: error
                    }
                )
            )
        }


        /**
         * Axios其他错误
         */
        return Promise.reject(
            createRequestError(
                error.message ||
                '网络请求失败',
                {
                    type: 'REQUEST_ERROR',
                    originalError: error
                }
            )
        )
    }
)


/**
 * =========================================================
 * 创建统一请求错误
 * =========================================================
 */
function createRequestError(
    message,
    extra = {}
) {

    const requestError =
        new Error(message)

    Object.assign(
        requestError,
        extra
    )

    return requestError
}


/**
 * =========================================================
 * 常用请求方法
 * =========================================================
 */

export function get(
    url,
    config = {}
) {
    return request.get(
        url,
        config
    )
}


export function post(
    url,
    data = {},
    config = {}
) {
    return request.post(
        url,
        data,
        config
    )
}


export function put(
    url,
    data = {},
    config = {}
) {
    return request.put(
        url,
        data,
        config
    )
}


export function del(
    url,
    config = {}
) {
    return request.delete(
        url,
        config
    )
}


export function patch(
    url,
    data = {},
    config = {}
) {
    return request.patch(
        url,
        data,
        config
    )
}


/**
 * =========================================================
 * 文件上传
 * =========================================================
 */
export function upload(
    url: string,
    file: File | Blob,
    extraData: Record<string, any> = {},
    config: Record<string, any> = {}
) {

    const formData =
        new FormData()

    formData.append(
        'file',
        file
    )


    Object.entries(
        extraData
    ).forEach(
        ([key, value]) => {

            formData.append(
                key,
                value
            )
        }
    )


    return request.post(
        url,
        formData,
        {
            ...config,

            headers: {
                ...(config.headers || {}),
                'Content-Type':
                    'multipart/form-data'
            }
        }
    )
}


/**
 * =========================================================
 * 文件下载
 * =========================================================
 */
export function download(
    url,
    config = {}
) {

    return request.get(
        url,
        {
            ...config,
            responseType: 'blob'
        }
    )
}


/**
 * 导出默认实例
 *
 * 后续可以直接：
 *
 * import request from '@/utils/request'
 *
 * request.get(...)
 */
export default request
