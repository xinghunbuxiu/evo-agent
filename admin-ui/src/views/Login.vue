<template>
  <div class="min-h-screen bg-slate-50 lg:flex">
    <aside class="relative hidden w-[min(420px,38vw)] shrink-0 flex-col justify-between bg-slate-900 px-10 py-12 text-white lg:flex">
      <div>
        <div class="flex items-center gap-3">
          <span class="text-2xl">🧬</span>
          <div class="leading-tight">
            <div class="text-lg font-semibold">Evo</div>
            <div class="text-[10px] uppercase tracking-[0.18em] text-slate-400">个人公司</div>
          </div>
        </div>
        <h1 class="mt-10 text-3xl font-semibold leading-tight">一个人，一家公司</h1>
        <p class="mt-4 max-w-sm text-sm leading-7 text-slate-300">
          育成师带教岗位成员，财务看经营结果，成长复盘沉淀经验与 Mission 续跑——登录后从公司总览开始。
        </p>
      </div>
      <div class="space-y-3 text-xs text-slate-400">
        <div class="flex items-center gap-2">
          <span class="h-1.5 w-1.5 rounded-full bg-teal-400" />
          左树导航：部门 → 工种 → 员工
        </div>
        <div class="flex items-center gap-2">
          <span class="h-1.5 w-1.5 rounded-full bg-teal-400" />
          节点流水：思考 → 归档全链路
        </div>
        <div class="flex items-center gap-2">
          <span class="h-1.5 w-1.5 rounded-full bg-teal-400" />
          成长与知识：知识库 / 复盘 / Mission
        </div>
      </div>
    </aside>

    <main class="flex flex-1 items-center justify-center px-4 py-10 lg:px-8">
      <div class="w-full max-w-md">
        <div class="mb-8 flex items-center gap-3 lg:hidden">
          <span class="text-2xl">🧬</span>
          <div class="leading-tight">
            <div class="text-base font-semibold text-slate-900">Evo</div>
            <div class="text-[10px] uppercase tracking-[0.16em] text-slate-400">个人公司</div>
          </div>
        </div>

        <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div class="mb-6">
            <div class="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-400">账户</div>
            <h2 class="mt-2 text-2xl font-semibold text-slate-900">
              {{ isRegister ? '创建账户' : '登录控制台' }}
            </h2>
            <p class="mt-2 text-sm leading-6 text-slate-500">
              {{ isRegister ? '注册后可管理工种、员工与收支摘要。' : '使用已有账户进入 Admin 控制台。' }}
            </p>
          </div>

          <nav class="mb-6 flex gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
            <button
              type="button"
              class="flex-1 rounded-lg px-3 py-2 text-sm transition"
              :class="!isRegister
                ? 'bg-white font-medium text-teal-900 shadow-sm ring-1 ring-teal-200'
                : 'text-slate-600 hover:bg-white/70'"
              @click="switchMode('login')"
            >
              登录
            </button>
            <button
              type="button"
              class="flex-1 rounded-lg px-3 py-2 text-sm transition"
              :class="isRegister
                ? 'bg-white font-medium text-teal-900 shadow-sm ring-1 ring-teal-200'
                : 'text-slate-600 hover:bg-white/70'"
              @click="switchMode('register')"
            >
              注册
            </button>
          </nav>

          <form @submit.prevent="handleSubmit" class="space-y-4">
            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">用户名</label>
              <input
                v-model="username"
                type="text"
                placeholder="请输入用户名"
                autocomplete="username"
                class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                required
              >
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">密码</label>
              <input
                v-model="password"
                type="password"
                placeholder="请输入密码"
                autocomplete="current-password"
                class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                required
              >
              <p v-if="isRegister" class="mt-1.5 text-xs text-slate-500">密码至少需要 6 位</p>
            </div>

            <div
              v-if="error"
              class="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700"
            >
              {{ error }}
            </div>
            <div
              v-if="success"
              class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-700"
            >
              {{ success }}
            </div>

            <button
              type="submit"
              class="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-60"
              :disabled="loading"
            >
              {{ loading ? (isRegister ? '注册中...' : '登录中...') : (isRegister ? '注册' : '登录') }}
            </button>
          </form>
        </div>

        <p class="mt-6 text-center text-xs text-slate-400">
          本地默认后端 http://localhost:8000
        </p>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, register } from '../api/auth'

const router = useRouter()
const route = useRoute()

const isRegister = ref(route.meta.mode === 'register')

watch(() => route.meta.mode, (mode) => {
  isRegister.value = mode === 'register'
})

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const success = ref('')

const switchMode = (mode: 'login' | 'register') => {
  error.value = ''
  success.value = ''
  router.push(mode === 'register' ? '/register' : '/login')
}

const handleSubmit = async () => {
  loading.value = true
  error.value = ''
  success.value = ''

  try {
    if (isRegister.value) {
      const data = await register(username.value, password.value)
      if (data.code === 0 && data.success) {
        success.value = data.message || '注册成功！请登录'
        password.value = ''
        setTimeout(() => router.replace('/login'), 1000)
      } else {
        error.value = data.message || '注册失败'
      }
    } else {
      const data = await login(username.value, password.value)
      if (data.code === 0 && data.success) {
        const user = data.data
        if (user.token) {
          localStorage.setItem('token', user.token)
        }
        localStorage.setItem('user', JSON.stringify(user))
        const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
        router.push(redirect)
      } else {
        error.value = data.message || '用户名或密码错误'
      }
    }
  } catch {
    error.value = '网络错误，请检查后端服务是否运行 (http://localhost:8000)'
  } finally {
    loading.value = false
  }
}
</script>
