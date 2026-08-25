import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { defineAsyncComponent } from 'vue'

import App from './App.vue'
import './style.css'

import { getUser } from './api/auth'

const Dashboard = defineAsyncComponent(() => import('./views/Dashboard.vue'))
const Tasks = defineAsyncComponent(() => import('./views/Tasks.vue'))
const Knowledge = defineAsyncComponent(() => import('./views/Knowledge.vue'))
const Login = defineAsyncComponent(() => import('./views/Login.vue'))
const Settings = defineAsyncComponent(() => import('./views/Settings.vue'))
const CompanySettings = defineAsyncComponent(() => import('./views/CompanySettings.vue'))
const Evolution = defineAsyncComponent(() => import('./views/Evolution.vue'))
const MissionRunDetail = defineAsyncComponent(() => import('./views/MissionRunDetail.vue'))
const ChildWorkspace = defineAsyncComponent(() => import('./views/ChildWorkspace.vue'))
const FinanceWorkspace = defineAsyncComponent(() => import('./views/FinanceWorkspace.vue'))
const IntakeWorkspace = defineAsyncComponent(() => import('./views/IntakeWorkspace.vue'))
const TrainerToolsWorkspace = defineAsyncComponent(() => import('./views/TrainerToolsWorkspace.vue'))
const MissionRunsWorkspace = defineAsyncComponent(() => import('./views/MissionRunsWorkspace.vue'))
const OrganizationNode = defineAsyncComponent(() => import('./views/OrganizationNode.vue'))

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', component: Login, meta: { public: true, mode: 'login' } },
  { path: '/register', component: Login, meta: { public: true, mode: 'register' } },
  { path: '/dashboard', component: Dashboard },
  { path: '/organization/intake', component: IntakeWorkspace },
  { path: '/organization/finance', component: FinanceWorkspace },
  { path: '/organization/:nodeId', component: OrganizationNode },
  { path: '/organization/parent/workspace', component: CompanySettings, alias: ['/settings'] },
  { path: '/organization/trainer/:memberId/tools', component: TrainerToolsWorkspace },
  { path: '/organization/knowledge', component: Knowledge, alias: ['/knowledge'] },
  { path: '/organization/evolution', component: Evolution, alias: ['/evolution'] },
  { path: '/organization/tasks', component: Tasks, alias: ['/tasks'] },
  { path: '/organization/missions', component: MissionRunsWorkspace },
  { path: '/organization/missions/:missionRunId', component: MissionRunDetail, alias: ['/missions/:missionRunId'] },
  { path: '/organization/trainer/:memberId?/workspace', component: Settings, alias: ['/settings/advanced'] },
  { path: '/organization/child/:memberId?/workspace', component: ChildWorkspace, alias: ['/children/:memberId?'] },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.path !== from.path || to.fullPath !== from.fullPath) {
      return { top: 0, left: 0 }
    }
    return false
  },
})

let authCheckedAt = 0
let authResolved = false

async function ensureAuthenticated() {
  const now = Date.now()
  if (authResolved && now - authCheckedAt < 15000) {
    return true
  }

  try {
    const response = await getUser()
    if (response.code === 0 && response.data) {
      localStorage.setItem('user', JSON.stringify(response.data))
      if (response.data.token) {
        localStorage.setItem('token', response.data.token)
      }
      authResolved = true
      authCheckedAt = now
      return true
    }
  } catch (error) {
    console.warn('[Router] session check failed', error)
  }

  authResolved = false
  authCheckedAt = now
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  return false
}

router.beforeEach(async (to) => {
  const isPublic = Boolean(to.meta.public)
  const isAuthenticated = await ensureAuthenticated()
  console.log(`[Router] 导航到 ${to.path}, 公开=${isPublic}, 已登录=${isAuthenticated}`)

  if (!isPublic && !isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if (isPublic && isAuthenticated && (to.path === '/login' || to.path === '/register')) {
    return '/dashboard'
  }

  return true
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
