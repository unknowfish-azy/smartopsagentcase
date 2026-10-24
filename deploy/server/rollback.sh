#!/usr/bin/env bash

set -Eeuo pipefail

APP_NAME="smartops-agent"

APP_DIR="${APP_DIR:-/opt/smartops}"

BACKUP_DIR="${BACKUP_DIR:-/opt/smartops-backups}"

RELEASE_DIR="${RELEASE_DIR:-${APP_DIR}/release}"


log() {
    echo "[SmartOps][$(date '+%Y-%m-%d %H:%M:%S')] $*"
}


latest_backup() {

    find "${BACKUP_DIR}" \
        -mindepth 1 \
        -maxdepth 1 \
        -type d \
        | sort \
        | tail -n 1

}


rollback() {

    local backup

    backup="$(latest_backup)"

    if [[ -z "${backup}" ]]; then

        log "没有找到可用的备份"

        exit 1

    fi

    log "发现最近备份：${backup}"


    if [[ ! -d "${backup}/release" ]]; then

        log "备份中不存在 release 目录"

        exit 1

    fi


    local current_backup=""

    if [[ -d "${RELEASE_DIR}" ]]; then

        current_backup="${RELEASE_DIR}.rollback.$(date '+%Y%m%d-%H%M%S')"

        log "暂存当前版本"

        mv \
            "${RELEASE_DIR}" \
            "${current_backup}"

    fi


    log "恢复上一版本"

    cp -a \
        "${backup}/release" \
        "${RELEASE_DIR}"


    log "启动服务"

    cd "${APP_DIR}"

    if [[ -f docker-compose.yml ]]; then

        docker compose up -d

    fi


    log "执行健康检查"

    if curl \
        --silent \
        --fail \
        "http://127.0.0.1/health" \
        >/dev/null; then

        log "回滚成功"

    else

        log "回滚后健康检查失败"

        exit 1

    fi

}


rollback