import { defineStore } from 'pinia'
import { getStorage, setStorage } from '../utils/storage.js'
import { setVisualMode, visualMode } from '../visual/visualMode.js'
import { personalSystemGroups } from '../navigation/personalSystemNavigation.js'
import {
    resolveExpandedGroupIds,
    sanitizeExpandedGroupIds,
    toggleExpandedGroupId
} from '../navigation/navigationState.js'

const PERSONAL_SYSTEM_NAVIGATION_KEY = 'personal_system_navigation'
const CURRENT_WORKSPACE_KEY = 'current_workspace'
const SIDEBAR_COLLAPSED_KEY = 'sidebar_collapsed'

export const availableWorkspaces = Object.freeze([
    { id: 'default-ops', name: '默认运维知识库', label: 'DEFAULT OPS KNOWLEDGE' }
])

function workspaceStorageKey() {
    const previewUser = localStorage.getItem('smartops_preview_user') || 'anonymous'
    return `${CURRENT_WORKSPACE_KEY}:${previewUser}`
}

function storedWorkspaceId() {
    const stored = getStorage(workspaceStorageKey())
    return availableWorkspaces.some(workspace => workspace.id === stored)
        ? stored
        : availableWorkspaces[0].id
}

function storedExpandedGroups() {
    return sanitizeExpandedGroupIds(
        getStorage(PERSONAL_SYSTEM_NAVIGATION_KEY),
        personalSystemGroups
    )
}

function storedSidebarCollapsed() {
    return getStorage(SIDEBAR_COLLAPSED_KEY) === true
}

export const useAppStore = defineStore(
    'app',
    {
        state: () => ({
            sidebarCollapsed: storedSidebarCollapsed(),
            mobileNavigationOpen: false,
            expandedPersonalSystemGroups: storedExpandedGroups(),
            currentWorkspaceId: storedWorkspaceId(),
            systemName: '智维Agent'
        }),

        getters: {
            currentVisualMode: () => visualMode.value
        },

        actions: {
            setVisualMode(mode) {
                setVisualMode(mode)
            },

            toggleSidebar() {
                this.sidebarCollapsed = !this.sidebarCollapsed
                setStorage(SIDEBAR_COLLAPSED_KEY, this.sidebarCollapsed)
            },

            expandSidebar() {
                this.sidebarCollapsed = false
                setStorage(SIDEBAR_COLLAPSED_KEY, false)
            },

            collapseSidebar() {
                this.sidebarCollapsed = true
                setStorage(SIDEBAR_COLLAPSED_KEY, true)
            },

            setRouteNavigation(routeName) {
                const expanded = resolveExpandedGroupIds(
                    routeName,
                    this.expandedPersonalSystemGroups,
                    personalSystemGroups
                )
                this.expandedPersonalSystemGroups = expanded
                setStorage(PERSONAL_SYSTEM_NAVIGATION_KEY, expanded)
            },

            togglePersonalSystemGroup(groupId, routeName) {
                const expanded = toggleExpandedGroupId(
                    groupId,
                    this.expandedPersonalSystemGroups,
                    personalSystemGroups,
                    routeName
                )
                this.expandedPersonalSystemGroups = expanded
                setStorage(PERSONAL_SYSTEM_NAVIGATION_KEY, expanded)
            },

            openMobileNavigation() {
                this.mobileNavigationOpen = true
            },

            closeMobileNavigation() {
                this.mobileNavigationOpen = false
            },

            toggleMobileNavigation() {
                this.mobileNavigationOpen = !this.mobileNavigationOpen
            },

            setCurrentWorkspace(workspaceId) {
                if (!availableWorkspaces.some(workspace => workspace.id === workspaceId)) return
                this.currentWorkspaceId = workspaceId
                setStorage(workspaceStorageKey(), workspaceId)
            }
        }
    }
)
