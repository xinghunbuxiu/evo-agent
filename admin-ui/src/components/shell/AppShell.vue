<template>
  <div class="flex min-h-[calc(100vh-0px)] flex-col bg-slate-50">
    <header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div class="flex h-14 items-center justify-between gap-4 px-4 lg:px-5">
        <div class="flex min-w-0 items-center gap-3">
          <button
            type="button"
            class="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50 lg:hidden"
            @click="mobileNavOpen = true"
          >
            菜单
          </button>
          <div class="flex items-center gap-2">
            <div class="flex h-7 w-7 items-center justify-center rounded-md bg-teal-600 text-[11px] font-semibold text-white">E</div>
            <div class="leading-tight">
              <div class="text-sm font-semibold text-slate-900">Evo</div>
              <div class="text-[11px] text-slate-500">经营控制台</div>
            </div>
          </div>
          <div v-if="breadcrumb.length" class="hidden min-w-0 items-center gap-1 text-xs text-slate-500 md:flex">
            <template v-for="(item, index) in breadcrumb" :key="`crumb-${item.id}`">
              <span v-if="index > 0" class="text-slate-300">/</span>
              <button
                type="button"
                class="truncate hover:text-teal-700"
                @click="selectTreeNode(item)"
              >
                {{ item.label }}
              </button>
            </template>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-60"
            :disabled="loading"
            @click="refreshOverview"
          >
            {{ loading ? '刷新中...' : '刷新' }}
          </button>
          <span v-if="userName" class="hidden text-xs text-slate-500 sm:inline">{{ userName }}</span>
          <button type="button" class="text-xs text-red-500 hover:text-red-600" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <div
      v-if="overviewError"
      class="border-b border-rose-200 bg-rose-50 px-4 py-2 text-center text-xs text-rose-700"
    >
      {{ overviewError }}
      <button type="button" class="ml-2 underline" @click="refreshOverview">重试</button>
    </div>

    <div class="flex min-h-0 flex-1">
      <aside class="hidden w-[260px] shrink-0 border-r border-slate-200 bg-white lg:block">
        <CompanyTreeNav
          :nodes="companyTree"
          :selection-id="selectionId"
          @select="selectTreeNode"
        />
      </aside>

      <main class="min-w-0 flex-1 overflow-auto">
        <slot />
      </main>
    </div>

    <div
      v-if="mobileNavOpen"
      class="fixed inset-0 z-50 lg:hidden"
    >
      <button
        type="button"
        class="absolute inset-0 bg-slate-900/40"
        aria-label="关闭菜单"
        @click="mobileNavOpen = false"
      />
      <aside class="absolute inset-y-0 left-0 flex w-[min(280px,88vw)] flex-col border-r border-slate-200 bg-white shadow-xl">
        <div class="flex h-14 items-center justify-between border-b border-slate-100 px-4">
          <span class="text-sm font-medium text-slate-900">公司导航</span>
          <button type="button" class="text-xs text-slate-500" @click="mobileNavOpen = false">关闭</button>
        </div>
        <CompanyTreeNav
          class="min-h-0 flex-1"
          :nodes="companyTree"
          :selection-id="selectionId"
          @select="handleMobileSelect"
        />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CompanyTreeNav from './CompanyTreeNav.vue'
import { getUser, logout as logoutApi, type UserProfile } from '../../api/auth'
import { getAutonomyStatus, type AutonomyStatus } from '../../api/plugins'
import { getFinanceOverview, type FinanceOverview } from '../../api/finance'
import { getWorkTypes, type WorkTypeItem } from '../../api/workTypes'
import { getWorkNodes } from '../../api/workNodes'
import { buildCompanyTree, companyTreeBreadcrumb, type CompanyTreeNode } from '../../utils/companyTree'
import { buildWorkNodes, type WorkNode } from '../../utils/workNodes'
import { companyConsoleKey } from '../../composables/companyConsole'

const route = useRoute()
const router = useRouter()

const tenantId = ref(localStorage.getItem('tenant_id') || 'default')
const loading = ref(false)
const overviewError = ref('')
const user = ref<UserProfile | null>(null)
const autonomyStatus = ref<AutonomyStatus | null>(null)
const workTypes = ref<WorkTypeItem[]>([])
const serverWorkNodes = ref<WorkNode[]>([])
const financeOverview = ref<FinanceOverview | null>(null)
const mobileNavOpen = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const userName = computed(() => user.value?.name || user.value?.login || '')

const clientWorkNodes = computed(() => buildWorkNodes({
  workTypes: workTypes.value,
  members: autonomyStatus.value?.child_members?.items || [],
  tasks: autonomyStatus.value?.task_center?.items || [],
}))

const workNodes = computed(() => (
  serverWorkNodes.value.length ? serverWorkNodes.value : clientWorkNodes.value
))

const companyTree = computed(() => buildCompanyTree({
  workTypes: workTypes.value,
  members: autonomyStatus.value?.child_members?.items || [],
  tasks: autonomyStatus.value?.task_center?.items || [],
  workNodes: workNodes.value,
  parentLabel: autonomyStatus.value?.parent_profile?.display_name || '公司',
}))

const selectionId = computed(() => {
  const scope = String(route.query.scope || '').trim()
  if (scope === 'work_type' && route.query.wt) return `work_type:${route.query.wt}`
  if (scope === 'member' && route.query.member) return `member:${route.query.member}`
  if (scope === 'node' && route.query.node) return String(route.query.node)
  if (route.path === '/organization/intake' || route.params.nodeId === 'intake') return 'function:intake'
  if (route.path === '/organization/finance' || route.params.nodeId === 'finance') return 'function:finance'
  if (route.path.startsWith('/organization/parent')) return 'settings'
  if (route.path.startsWith('/organization/trainer') && route.path.endsWith('/tools')) return 'function:trainer-tools'
  if (route.path.startsWith('/organization/trainer')) return 'function:trainer'
  if (route.path.includes('/knowledge')) return 'function:knowledge'
  if (route.path.includes('/evolution')) return 'function:evolution'
  if (route.path.includes('/tasks')) return 'function:tasks'
  if (route.path.includes('/missions')) return 'function:missions'
  const childMember = String(route.params.memberId || '').trim()
  if (route.path.startsWith('/organization/child') && childMember) return `member:${childMember}`
  return 'overview'
})

const breadcrumb = computed(() => companyTreeBreadcrumb(companyTree.value, selectionId.value))

const selectTreeNode = (node: CompanyTreeNode) => {
  if ((node.kind === 'link' || node.kind === 'hint') && node.href) {
    router.push(node.href)
    return
  }
  if (node.kind === 'overview') {
    router.push({ path: '/dashboard', query: {} })
    return
  }
  if (node.kind === 'work_type' && node.work_type_id) {
    router.push({ path: '/dashboard', query: { scope: 'work_type', wt: node.work_type_id } })
    return
  }
  if (node.kind === 'member' && node.member_id) {
    router.push({
      path: '/dashboard',
      query: {
        scope: 'member',
        member: node.member_id,
        wt: node.work_type_id || undefined,
      },
    })
    return
  }
  if (node.kind === 'department') {
    router.push({ path: '/dashboard', query: { scope: 'overview' } })
  }
}

const handleMobileSelect = (node: CompanyTreeNode) => {
  mobileNavOpen.value = false
  selectTreeNode(node)
}

const refreshOverview = async () => {
  loading.value = true
  overviewError.value = ''
  try {
    const tid = tenantId.value || 'default'
    const [autonomyResult, financeResult, , workTypesResult, nodesResult] = await Promise.all([
      getAutonomyStatus(tid),
      getFinanceOverview().catch(() => null),
      Promise.resolve(null),
      getWorkTypes().catch(() => null),
      getWorkNodes({ tenant_id: tid }).catch(() => null),
    ])
    if (autonomyResult.code !== 0) {
      throw new Error(autonomyResult.message || '自治状态加载失败')
    }
    autonomyStatus.value = autonomyResult.data || null
    financeOverview.value = financeResult?.data || null
    workTypes.value = workTypesResult?.data?.items || []
    serverWorkNodes.value = nodesResult?.data?.items || []
  } catch (err) {
    overviewError.value = err instanceof Error ? err.message : '控制台数据同步失败'
  } finally {
    loading.value = false
  }
}

const logout = async () => {
  try {
    await logoutApi()
  } finally {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    router.replace('/login')
  }
}

provide(companyConsoleKey, {
  loading,
  overviewError,
  tenantId,
  autonomyStatus,
  workTypes,
  companyTree,
  workNodes,
  financeOverview,
  selectionId,
  refreshOverview,
  selectTreeNode,
})

onMounted(async () => {
  try {
    const data = await getUser()
    if (data.code === 0 && data.data) user.value = data.data
  } catch {
    const cached = localStorage.getItem('user')
    user.value = cached ? JSON.parse(cached) : null
  }
  await refreshOverview()
  refreshTimer = setInterval(() => {
    if (document.visibilityState !== 'visible') return
    void refreshOverview()
  }, 60000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

watch(() => route.fullPath, () => {
  void refreshOverview()
})
</script>
