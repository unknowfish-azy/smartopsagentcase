import http from '../utils/request'

export const createKnowledgeLibrary = payload => http.post('/api/knowledge/personal/libraries', payload)
export const listKnowledgeLibraries = () => http.get('/api/knowledge/personal/libraries')
export const reindexKnowledgeLibrary = id => http.post(`/api/knowledge/personal/libraries/${id}/reindex`)
export const importKnowledgeFile = (id, file) => { const data = new FormData(); data.append('file', file); return http.post(`/api/knowledge/personal/libraries/${id}/import`, data, { headers: { 'Content-Type': undefined } }) }
export const exportKnowledgeLibrary = id => http.get(`/api/knowledge/personal/libraries/${id}/export`, { responseType: 'blob' })
export const updateKnowledgeLibrary = (id, payload) => http.patch(`/api/knowledge/personal/libraries/${id}`, payload)
export const archiveKnowledgeLibrary = id => http.post(`/api/knowledge/personal/libraries/${id}/archive`)
export const restoreKnowledgeLibrary = id => http.post(`/api/knowledge/personal/libraries/${id}/restore`)
export const getKnowledgeLibrary = id => http.get(`/api/knowledge/personal/libraries/${id}`)
export const createKnowledgeEntry = (libraryId, payload) => http.post(`/api/knowledge/personal/libraries/${libraryId}/entries`, payload)
export const getKnowledgeEntries = (libraryId, params = {}) => http.get(`/api/knowledge/personal/libraries/${libraryId}/entries`, { params })
export const getKnowledgeEntry = id => http.get(`/api/knowledge/personal/entries/${id}`)
export const archiveKnowledgeEntry = id => http.post(`/api/knowledge/personal/entries/${id}/archive`)
export const deleteKnowledgeEntry = id => http.delete(`/api/knowledge/personal/entries/${id}`)
export const updateKnowledgeEntry = (id, payload) => http.patch(`/api/knowledge/personal/entries/${id}`, payload)
