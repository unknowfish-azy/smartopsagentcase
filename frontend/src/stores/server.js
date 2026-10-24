import { defineStore } from 'pinia'
import {
    getServers,
    getServer
} from '../api/server'

export const useServerStore = defineStore(
    'server',
    {
        state: () => ({
            list: [],
            current: null,
            loading: false
        }),

        getters: {
            onlineCount: state =>
                state.list.filter(
                    item => item.status === 'ONLINE'
                ).length,

            warningCount: state =>
                state.list.filter(
                    item => item.status === 'WARNING'
                ).length
        },

        actions: {
            async fetchList() {
                this.loading = true

                try {
                    const result = await getServers()
                    this.list = result.data || []
                } finally {
                    this.loading = false
                }
            },

            async fetchById(id) {
                const result = await getServer(id)
                this.current = result.data
                return this.current
            }
        }
    }
)