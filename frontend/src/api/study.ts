import http from '../utils/request'

/**
 * OPS-17 学习中心 / 课程知识库。
 *
 * 目录（course / point）是只读语料，个人掌握度走 progress 写入；
 * 所有请求都由后端按当前会话用户隔离，前端不传 userId。
 */

export const getStudyOverview = () => http.get('/api/study/overview')

export const getStudyCourses = () => http.get('/api/study/courses')

export const getStudyCourse = (code: string) => http.get(`/api/study/courses/${encodeURIComponent(code)}`)

export const saveStudyProgress = (pointId: number, mastered: boolean, note?: string) =>
    http.post('/api/study/progress', { pointId, mastered, note: note?.trim() ? note : undefined })

export const resetStudyCourse = (code: string) => http.post(`/api/study/courses/${encodeURIComponent(code)}/reset`)
