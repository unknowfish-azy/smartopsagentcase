export function formatPercent(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return '-'
    }

    return `${Number(value).toFixed(1)}%`
}

export function formatDate(value) {

    if (!value) {
        return '-'
    }

    return new Date(value)
        .toLocaleString('zh-CN')
}