import request from '../utils/request.ts'

/**
 * 获取 Java 边缘签发的短时聊天 run 令牌（SEC-01/SEC-02）。
 *
 * 该令牌绑定当前会话主体与一次 run；ai-service 只信任令牌中的 run_id，
 * 客户端自带的 X-Run-ID 不再作为身份。
 */
export function fetchChatRunToken() {
  return request({ url: '/api/chat/run-token', method: 'get' })
}

export default fetchChatRunToken
