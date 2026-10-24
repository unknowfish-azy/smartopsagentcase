const PREFIX = 'smartops_'

export function setStorage(
    key,
    value
) {
    localStorage.setItem(
        PREFIX + key,
        JSON.stringify(value)
    )
}

export function getStorage(key) {

    const value =
        localStorage.getItem(
            PREFIX + key
        )

    if (!value) {
        return null
    }

    try {
        return JSON.parse(value)
    } catch {
        return null
    }
}

export function removeStorage(key) {
    localStorage.removeItem(
        PREFIX + key
    )
}