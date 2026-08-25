<template>
  <div class="w-full min-w-0 space-y-5 px-4 py-4 lg:px-6 lg:py-6">
    <WorkspacePageHeader
      eyebrow="任务 · 队列"
      title="任务队列"
      description="查看与重放 analyze/reconstruct 等后台任务；产品主线的正式任务在员工工作台与育成师编排页。"
      :loading="loading"
      refresh-label="刷新队列"
      :back-to="{ path: '/dashboard' }"
      back-label="返回公司总览"
      @refresh="loadTasks"
    >
      <template #actions>
        <button
          type="button"
          class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
          @click="showCreateModal = true"
        >
          新建任务
        </button>
        <router-link
          to="/organization/evolution"
          class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          成长控制台
        </router-link>
      </template>
    </WorkspacePageHeader>

    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table class="w-full">
        <thead class="bg-gray-50 border-b">
          <tr class="text-left text-gray-600 text-sm">
            <th class="px-4 py-3 font-medium">任务ID</th>
            <th class="px-4 py-3 font-medium">类型</th>
            <th class="px-4 py-3 font-medium">租户</th>
            <th class="px-4 py-3 font-medium">状态</th>
            <th class="px-4 py-3 font-medium">优先级</th>
            <th class="px-4 py-3 font-medium">进度</th>
            <th class="px-4 py-3 font-medium">创建时间</th>
            <th class="px-4 py-3 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks" :key="task.id" class="border-b last:border-0 hover:bg-gray-50">
            <td class="px-4 py-3 font-mono text-sm">{{ task.id }}</td>
            <td class="px-4 py-3">{{ task.type }}</td>
            <td class="px-4 py-3">{{ task.tenant_id }}</td>
            <td class="px-4 py-3">
              <StatusBadge :status="task.status" />
            </td>
            <td class="px-4 py-3">{{ task.priority }}</td>
            <td class="px-4 py-3 w-32">
              <div class="bg-gray-200 rounded-full h-2">
                <div
                  class="bg-teal-500 h-2 rounded-full transition-all"
                  :style="{ width: task.progress + '%' }"
                />
              </div>
              <span class="text-xs text-gray-500">{{ task.progress }}%</span>
            </td>
            <td class="px-4 py-3 text-sm text-gray-600">
              {{ task.created_at?.slice(0, 19) }}
            </td>
            <td class="px-4 py-3">
              <button
                v-if="task.status === 'pending'"
                @click="cancelTask(task.id)"
                class="text-red-500 hover:text-red-700 text-sm mr-2"
              >
                取消
              </button>
              <button
                @click="viewTask(task)"
                class="text-teal-600 hover:text-teal-800 text-sm"
              >
                详情
              </button>
              <button
                @click="replayTaskItem(task.id)"
                class="ml-2 text-amber-600 hover:text-amber-800 text-sm"
              >
                重放
              </button>
            </td>
          </tr>
          <tr v-if="tasks.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-gray-500">
              暂无任务
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 创建任务弹窗 -->
    <div v-if="showCreateModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 w-full max-w-md">
        <h2 class="text-xl font-bold mb-4">新建分析任务</h2>
        <form @submit.prevent="createTask">
          <div class="mb-4">
            <label class="block text-sm font-medium mb-1">任务类型</label>
            <select v-model="newTask.type" class="w-full border rounded-lg px-3 py-2">
              <option value="analyze">代码分析</option>
              <option value="reconstruct">项目重构</option>
              <option value="sync_cloud">同步云端</option>
            </select>
          </div>
          <div class="mb-4">
            <label class="block text-sm font-medium mb-1">代码路径</label>
            <input
              v-model="newTask.path"
              type="text"
              placeholder="/path/to/bundle.js"
              class="w-full border rounded-lg px-3 py-2"
            />
          </div>
          <div class="mb-4">
            <label class="block text-sm font-medium mb-1">优先级</label>
            <select v-model="newTask.priority" class="w-full border rounded-lg px-3 py-2">
              <option :value="1">低</option>
              <option :value="2">正常</option>
              <option :value="3">高</option>
              <option :value="4">紧急</option>
            </select>
          </div>
          <div class="flex justify-end gap-2">
            <button
              type="button"
              @click="showCreateModal = false"
              class="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              取消
            </button>
            <button
              type="submit"
              class="px-4 py-2 bg-teal-500 text-white rounded-lg hover:bg-teal-600"
            >
              创建
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="selectedTask" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 w-full max-w-lg max-h-[80vh] overflow-auto">
        <h2 class="text-xl font-bold mb-4">任务详情</h2>
        <pre class="bg-gray-50 p-4 rounded-lg text-sm overflow-auto">{{ JSON.stringify(selectedTask, null, 2) }}</pre>
        <div class="flex justify-end mt-4">
          <button
            @click="selectedTask = null"
            class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import WorkspacePageHeader from '../components/shell/WorkspacePageHeader.vue'
import {
  cancelTaskById,
  createTask as createTaskApi,
  listTasks,
  replayTask,
  type TaskItem,
} from '../api/tasks'

const tasks = ref<TaskItem[]>([])
const loading = ref(false)
const showCreateModal = ref(false)
const selectedTask = ref<TaskItem | null>(null)
const newTask = ref({ type: 'analyze', path: '', priority: 2 })

const loadTasks = async () => {
  loading.value = true
  try {
    const res = await listTasks(100)
    tasks.value = Array.isArray(res.data) ? res.data : []
  } finally {
    loading.value = false
  }
}

const createTask = async () => {
  const res = await createTaskApi({
    type: newTask.value.type,
    payload: { path: newTask.value.path },
    priority: newTask.value.priority
  })
  if (res.success) {
    showCreateModal.value = false
    newTask.value = { type: 'analyze', path: '', priority: 2 }
    loadTasks()
  }
}

const cancelTask = async (id: string) => {
  if (!confirm('确定要取消这个任务吗？')) return
  await cancelTaskById(id)
  loadTasks()
}

const replayTaskItem = async (id: string) => {
  const res = await replayTask(id)
  if (res.success) {
    loadTasks()
  }
}

const viewTask = (task: TaskItem) => {
  selectedTask.value = task
}

onMounted(loadTasks)
</script>
