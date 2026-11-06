import {
    createRouter,
    createWebHistory
} from 'vue-router'

import { routeMetaFor } from '../navigation/routeMetadata.js'
import { sessionRouteDecision } from '../security/portalPolicy.js'
import { clearSession, loadSession } from '../security/session.js'

const routes = [
    { path: '/login', name: 'Login', component: () => import('../views/auth/LoginView.vue'), meta: { public: true } },
    { path: '/account/security', name: 'AccountSecurity', component: () => import('../views/account/AccountSecurityView.vue') },
    {
        path: '/admin', component: () => import('../layouts/AdminLayout.vue'), meta: { roles: ['admin'] },
        children: [
            { path: '', name: 'AdminControlCenter', component: () => import('../views/admin/AdminOverviewView.vue') },
            { path: 'users', name: 'AdminUsers', component: () => import('../views/admin/AdminUsersView.vue') },
            { path: 'governance', name: 'AdminGovernance', component: () => import('../views/admin/AdminGovernanceView.vue') },
            { path: 'teams', name: 'AdminTeams', component: () => import('../views/admin/AdminTeamsView.vue') },
            { path: 'sessions', name: 'AdminSessions', component: () => import('../views/admin/AdminSessionsView.vue') },
            { path: 'audit', name: 'AdminAudit', component: () => import('../views/admin/AdminAuditView.vue') },
            { path: 'approvals', name: 'AdminApprovals', component: () => import('../views/admin/AdminApprovalsView.vue') },
            { path: 'models', name: 'AdminModels', component: () => import('../views/admin/AdminModelGovernanceView.vue') },
            { path: 'security', name: 'AdminMfa', component: () => import('../views/admin/AdminMfaView.vue') },
            { path: 'readiness', name: 'AdminReadiness', component: () => import('../views/admin/AdminReadinessView.vue') }
        ]
    },
    { path: '/portfolio', name: 'PortfolioPreview', component: () => import('../views/portfolio/WorkInProgressView.vue') },
    {
        path: '/',
        component: () => import('../layouts/MainLayout.vue'),
        children: [
            { path: 'teams', name: 'TeamSpaces', component: () => import('../views/team/TeamSpacesView.vue'), meta: { space: 'team', section: 'TEAM SPACE / 团队空间' } },
            { path: 'teams/join/:token', name: 'TeamJoin', component: () => import('../views/team/TeamJoinView.vue'), meta: { space: 'team', section: 'TEAM INVITE / 接受邀请' } },
            { path: 'teams/:teamId', name: 'TeamDetail', component: () => import('../views/team/TeamDetailView.vue'), meta: { space: 'team', section: 'TEAM MEMBERS / 团队成员' } },
            { path: 'teams/:teamId/workspace', name: 'TeamCollaboration', component: () => import('../views/team/TeamCollaborationView.vue'), meta: { space: 'team', section: 'TEAM OPERATIONS / 团队协作' } },
            {
                path: '',
                name: 'Dashboard',
                component: () => import('../views/dashboard/DashboardView.vue'),
                meta: routeMetaFor('Dashboard')
            },
            {
                path: 'chat',
                name: 'Chat',
                component: () => import('../views/chat/ChatView.vue'),
                meta: { ...routeMetaFor('Chat'), section: 'AI CHAT / AI 对话' }
            },
            {
                path: 'servers',
                name: 'ServerList',
                component: () => import('../views/server/ServerListView.vue'),
                meta: routeMetaFor('ServerList')
            },
            {
                path: 'servers/:id',
                name: 'ServerDetail',
                component: () => import('../views/server/ServerDetailView.vue'),
                props: true,
                meta: routeMetaFor('ServerDetail')
            },
            { path: 'health', name: 'HealthCenter', component: () => import('../views/diagnostics/HealthCenterView.vue'), meta: { ...routeMetaFor('HealthCenter'), section: 'SERVICE DIAGNOSTICS / 健康诊断' } },
            { path: 'milestones', name: 'MilestoneHall', component: () => import('../views/celebrate/AchievementsView.vue'), meta: { ...routeMetaFor('MilestoneHall'), section: 'MILESTONE HALL / 里程碑战报' } },
            { path: 'inspector', name: 'InspectorCenter', component: () => import('../views/inspector/InspectorCenterView.vue'), meta: routeMetaFor('InspectorCenter') },
            { path: 'inspector/events/:id', name: 'InspectorDetail', component: () => import('../views/inspector/InspectorDetailView.vue'), meta: routeMetaFor('InspectorDetail') },
            { path: 'inspector/statistics', name: 'InspectorStatistics', component: () => import('../views/inspector/InspectorStatisticsView.vue'), meta: routeMetaFor('InspectorStatistics') },
            { path: 'agent', name: 'AgentCommandCenter', component: () => import('../views/agent/AgentCommandCenterView.vue'), meta: routeMetaFor('AgentCommandCenter') },
            { path: 'agent/trace', name: 'ExecutionTrace', component: () => import('../views/agent/ExecutionTraceView.vue'), meta: routeMetaFor('ExecutionTrace') },
            { path: 'knowledge', name: 'Knowledge', component: () => import('../views/knowledge/KnowledgeView.vue'), meta: routeMetaFor('Knowledge') },
            { path: 'knowledge/personal', name: 'PersonalKnowledge', component: () => import('../views/knowledge/PersonalKnowledgeView.vue'), meta: { ...routeMetaFor('Knowledge'), section: 'PERSONAL KNOWLEDGE / 个人知识库' } },
            { path: 'knowledge/quiz', name: 'KnowledgeQuiz', component: () => import('../views/knowledge/QuizView.vue'), meta: { ...routeMetaFor('Knowledge'), section: 'QUIZ BANK / 运维题库' } },
            { path: 'knowledge/generation', name: 'KnowledgeGeneration', component: () => import('../views/knowledge/GenerationCenterView.vue'), meta: { ...routeMetaFor('Knowledge'), section: 'ARTIFACT GENERATION / 生成中心' } },
            { path: 'knowledge/review', name: 'KnowledgeCandidateReview', component: () => import('../views/knowledge/KnowledgeCandidateReviewView.vue'), meta: { ...routeMetaFor('KnowledgeCandidateReview'), section: 'KNOWLEDGE REVIEW / 知识审核' } },
            { path: 'plugins', name: 'PluginCenter', component: () => import('../views/plugins/PluginCenterView.vue'), meta: { ...routeMetaFor('PluginCenter'), section: 'EXTENSION LAB / 插件中心' } },
            { path: 'skills', name: 'SkillCenter', component: () => import('../views/skills/SkillCenterView.vue'), meta: { ...routeMetaFor('SkillCenter'), section: 'AGENT SKILLS / 技能中心' } },
            { path: 'sentinel', name: 'SentinelDashboard', component: () => import('../views/sentinel/SentinelDashboardView.vue'), meta: { section: 'SENTINEL / 哨兵监控' } },
            { path: 'sentinel/scripts', name: 'ScriptLibrary', component: () => import('../views/sentinel/ScriptLibraryView.vue'), meta: { section: 'SCRIPT LIBRARY / 脚本库' } },
            { path: 'sentinel/alerts', name: 'AlertCenter', component: () => import('../views/sentinel/AlertCenterView.vue'), meta: { section: 'ALERT CENTER / 告警中心' } },
            { path: 'sentinel/guardian', name: 'SentinelGuardian', component: () => import('../views/sentinel/SentinelGuardianView.vue'), meta: { section: 'SENTINEL / 守护 Agent' } },
            { path: 'incidents', name: 'IncidentCenter', component: () => import('../views/incident/IncidentCenterView.vue'), meta: { section: 'INCIDENT CENTER / 工单中心' } },
            { path: 'incidents/:id', name: 'IncidentDetail', component: () => import('../views/incident/IncidentDetailView.vue'), meta: { section: 'INCIDENT CENTER / 工单详情' } },
            { path: 'connections', name: 'Connections', component: () => import('../views/operations/ConnectionsView.vue'), meta: { ...routeMetaFor('Connections'), section: '连接中心 / 远程运维' } },
            { path: 'harbor', name: 'HarborWorkbench', component: () => import('../views/harbor/HarborWorkbenchView.vue'), meta: { ...routeMetaFor('HarborWorkbench'), section: 'HARBOR WORKBENCH / Harbor 工作台' } },
            { path: 'cloud-native', name: 'CloudNativeWorkbench', component: () => import('../views/cloud/CloudNativeWorkbenchView.vue'), meta: { ...routeMetaFor('CloudNativeWorkbench'), section: 'CLOUD NATIVE / 云原生工程' } },
            { path: 'tools/:tool?', name: 'Tools', component: () => import('../views/operations/ToolsView.vue'), meta: { section: 'TOOLS / 运维工具' } },
            { path: 'operations/runs', name: 'OperationRunHistory', component: () => import('../views/operations/RunHistoryView.vue'), meta: { ...routeMetaFor('OperationRunHistory'), section: 'RUN HISTORY / 运行记录' } },
            { path: 'operations/recovery', name: 'RecoveryContracts', component: () => import('../views/operations/RecoveryContractsView.vue'), meta: { ...routeMetaFor('RecoveryContracts'), section: 'RECOVERY CONTRACTS / 恢复契约' } },
            { path: 'model-health', name: 'ModelHealth', redirect: '/model-strength' },
            { path: 'model-strength', name: 'ModelStrength', component: () => import('../views/model/ModelAnalyticsView.vue'), props: { mode: 'strength' }, meta: { ...routeMetaFor('ModelStrength'), section: 'MODEL STRENGTH / 模型强度' } },
            { path: 'token-usage', name: 'TokenUsage', component: () => import('../views/model/ModelAnalyticsView.vue'), props: { mode: 'tokens' }, meta: { ...routeMetaFor('TokenUsage'), section: 'TOKEN USAGE / 用量与额度' } },
            { path: 'architecture', name: 'ArchitectureMap', component: () => import('../views/architecture/ArchitectureMapView.vue'), meta: { ...routeMetaFor('ArchitectureMap'), section: 'ARCHITECTURE / 架构总览', roles: ['admin'] } },

            { path: 'model-gateway', name: 'ModelGateway', component: () => import('../views/model/ModelGatewayView.vue'), meta: { section: 'MODEL GATEWAY / 统一模型网关' } },
            {
                path: '/model-settings',
                name: 'ModelSettings',
                component: () =>
                    import(
                        '../views/model/ModelSettingsView.vue'
                        ),
                meta: {
                    ...routeMetaFor('ModelSettings'),
                    title: '大模型接入'
                }
            }
        ]
    },

    {
        path: '/:pathMatch(.*)*',
        name: 'NotFound',
        component: () => import('../views/error/NotFoundView.vue')
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

router.beforeEach(async (to) => {
    let user
    try { user = await loadSession() } catch { return to.meta.public ? true : { path: '/login', query: { redirect: to.fullPath, reason: 'unavailable' } } }
    if (to.meta.public && !user?.mustChangePassword) return true
    return sessionRouteDecision(user, to)
})

export default router

window.addEventListener('smartops:unauthorized', () => {
    clearSession()
    if (router.currentRoute.value.path !== '/login') router.replace({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
})
