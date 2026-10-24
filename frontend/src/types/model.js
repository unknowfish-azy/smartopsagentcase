export function createEmptyModelConnection() {
    return {
        id: null,
        name: '',
        provider: '',
        baseUrl: '',
        modelName: '',
        apiKey: '',
        apiKeyMasked: '',
        enabled: true,
        timeoutSeconds: 60
    }
}

export function normalizeModelConnection(item = {}) {
    return {
        id: item.id ?? null,
        userId: item.userId ?? null,
        name: item.name ?? '',
        provider: item.provider ?? '',
        baseUrl: item.baseUrl ?? '',
        modelName: item.modelName ?? '',
        apiKeyMasked: item.apiKeyMasked ?? '',
        enabled: item.enabled ?? true,
        timeoutSeconds: item.timeoutSeconds ?? 60,
        createdAt: item.createdAt ?? null,
        updatedAt: item.updatedAt ?? null
    }
}