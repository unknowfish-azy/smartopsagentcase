const MB = 1024 * 1024
const extensions = /\.(png|jpe?g|txt|log|md)$/i

export function attachmentFiles(transfer) {
  const items = Array.from(transfer?.items || [])
  if (items.length) return items.filter(item => item.kind === 'file').map(item => item.getAsFile()).filter(Boolean)
  return Array.from(transfer?.files || [])
}

export function createAttachmentQueue({ createUrl = file => URL.createObjectURL(file), revokeUrl = url => URL.revokeObjectURL(url) } = {}) {
  let generation = 0
  return {
    items: [], error: '', busy: false,
    add(files, source = 'FILE') {
      if (this.busy) return
      this.error = ''
      for (const file of files) {
        const image = /\.(png|jpe?g)$/i.test(file.name)
        if (!extensions.test(file.name) || !file.size || file.size > (image ? 10 : 20) * MB) {
          this.error = '仅支持 PNG/JPEG（10 MB）和 UTF-8 TXT/LOG/MD（20 MB），不接受空文件。'
          continue
        }
        if (this.items.some(item => item.file === file || (item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified))) continue
        if (this.items.length >= 5 || this.items.reduce((total, item) => total + item.file.size, file.size) > 40 * MB) {
          this.error = '一次最多 5 个文件，合计不超过 40 MB。'
          continue
        }
        const preview = image ? createUrl(file) : ''
        this.items.push({ id: crypto.randomUUID(), file, source, preview, status: 'staged', error: '', stored: null })
      }
    },
    remove(id) {
      if (this.busy) return
      const item = this.items.find(value => value.id === id)
      if (item?.preview) revokeUrl(item.preview)
      this.items = this.items.filter(value => value.id !== id)
    },
    clear() {
      generation++
      for (const item of this.items) if (item.preview) revokeUrl(item.preview)
      this.items = []; this.error = ''; this.busy = false
    },
    async upload(send) {
      if (this.busy) throw new Error('附件正在上传')
      const epoch = generation
      this.busy = true
      try {
        for (const item of this.items) {
          if (item.stored) continue
          item.status = 'uploading'; item.error = ''
          try {
            const stored = await send(item.file, item.id, item.source)
            if (epoch !== generation) throw new Error('附件草稿已切换或取消')
            if (!stored?.id) throw new Error('上传响应缺少附件标识')
            item.stored = stored; item.status = 'uploaded'
          } catch (error) {
            if (epoch === generation) { item.status = 'failed'; item.error = error.message || '上传失败' }
            throw error
          }
        }
        if (epoch !== generation) throw new Error('附件草稿已切换或取消')
        return this.items.map(item => item.stored)
      } finally { if (epoch === generation) this.busy = false }
    }
  }
}
