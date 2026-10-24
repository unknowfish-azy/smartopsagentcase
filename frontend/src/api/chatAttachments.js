import request from '../utils/request.js'

const value = promise => promise.then(response => response.data)
const base = id => `/api/assistant/conversations/${encodeURIComponent(id)}`

export const chatAttachmentsApi = {
  list: () => value(request.get('/api/assistant/conversations')),
  create: conversation => value(request.post('/api/assistant/conversations', { id: conversation.id, title: conversation.title })),
  detail: id => value(request.get(base(id))),
  rename: (id, title) => value(request.put(base(id), { title })),
  delete: id => value(request.delete(base(id))),
  upload: (id, file, requestId, signal, sourceType = 'FILE') => {
    const data = new FormData()
    data.append('file', file); data.append('requestId', requestId); data.append('sourceType', sourceType)
    return value(request.post(`${base(id)}/attachments`, data, { headers: { 'Content-Type': undefined }, signal, timeout: 120000 }))
  },
  remove: (id, attachmentId) => value(request.delete(`${base(id)}/attachments/${encodeURIComponent(attachmentId)}`)),
  append: (id, data, signal) => value(request.post(`${base(id)}/messages`, data, { signal, timeout: 30000 })),
  content: (id, attachmentId, signal) => request.get(`${base(id)}/attachments/${encodeURIComponent(attachmentId)}/content`, { responseType: 'blob', signal })
}
