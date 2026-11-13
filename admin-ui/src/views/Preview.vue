<template>
  <div class="min-h-screen bg-slate-50 text-slate-800">
    <header class="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div class="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 sm:px-6">
        <div class="flex items-center gap-3">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-xl text-white">🧬</div>
          <div>
            <div class="text-sm font-semibold tracking-wide text-slate-900">Evo</div>
            <div class="text-[10px] uppercase tracking-[0.18em] text-slate-400">个人公司 · Mission 控制台</div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <span class="hidden rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 sm:inline-flex">只读演示环境</span>
          <a href="/login" class="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50">正式登录</a>
        </div>
      </div>
    </header>

    <div class="mx-auto grid max-w-[1440px] lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside class="border-b border-slate-200 bg-white p-4 lg:min-h-[calc(100vh-64px)] lg:border-b-0 lg:border-r">
        <div class="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">工作空间</div>
        <nav class="grid grid-cols-2 gap-2 lg:grid-cols-1">
          <button v-for="item in navItems" :key="item.id" @click="activeTab = item.id"
            class="flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition"
            :class="activeTab === item.id ? 'bg-teal-50 font-semibold text-teal-800 ring-1 ring-teal-100' : 'text-slate-600 hover:bg-slate-50'">
            <span class="w-5 text-center">{{ item.icon }}</span><span>{{ item.label }}</span>
          </button>
        </nav>
        <div class="mt-8 hidden rounded-xl bg-slate-900 p-4 text-white lg:block">
          <div class="text-xs font-semibold text-teal-300">核心执行闭环</div>
          <div class="mt-3 space-y-2 text-xs text-slate-300">
            <div>01 · 目标与计划</div><div>02 · Worker 执行</div><div>03 · 测试与验证</div><div>04 · 复盘与经验沉淀</div>
          </div>
        </div>
      </aside>

      <main class="min-w-0 p-4 sm:p-6 lg:p-8">
        <div class="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div class="text-xs font-medium text-teal-700">EVO WORKSPACE / PREVIEW</div>
            <h1 class="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{{ currentTitle }}</h1>
            <p class="mt-2 text-sm text-slate-500">通过 Mission 组织任务、调度成员，并将经过验证的结果沉淀为可复用知识。</p>
          </div>
          <div class="text-xs text-slate-400">示例数据 · 不连接真实后端</div>
        </div>

        <template v-if="activeTab === 'overview'">
          <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div v-for="metric in metrics" :key="metric.label" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div class="text-xs text-slate-500">{{ metric.label }}</div>
              <div class="mt-3 flex items-end justify-between">
                <div class="text-3xl font-semibold tracking-tight text-slate-900">{{ metric.value }}</div>
                <span class="text-xs font-medium text-teal-700">{{ metric.note }}</span>
              </div>
            </div>
          </section>
          <section class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.8fr)]">
            <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div class="flex items-center justify-between"><h2 class="font-semibold text-slate-900">Mission 执行看板</h2><span class="text-xs text-slate-400">最近运行</span></div>
              <div class="mt-5 space-y-4">
                <div v-for="mission in missions" :key="mission.id" class="rounded-xl border border-slate-100 p-4">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div><div class="text-sm font-medium text-slate-800">{{ mission.name }}</div><div class="mt-1 text-xs text-slate-400">{{ mission.id }} · {{ mission.owner }}</div></div>
                    <span class="rounded-full px-2.5 py-1 text-[11px] font-medium" :class="mission.tone">{{ mission.status }}</span>
                  </div>
                  <div class="mt-4 h-2 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-teal-600" :style="{ width: mission.progress + '%' }"></div></div>
                  <div class="mt-2 flex justify-between text-[11px] text-slate-400"><span>{{ mission.stage }}</span><span>{{ mission.progress }}%</span></div>
                </div>
              </div>
            </div>
            <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 class="font-semibold text-slate-900">执行链路</h2>
              <div class="mt-5 space-y-0">
                <div v-for="(step, index) in pipeline" :key="step.title" class="relative flex gap-3 pb-5 last:pb-0">
                  <div v-if="index !== pipeline.length - 1" class="absolute left-[13px] top-7 h-full w-px bg-slate-200"></div>
                  <div class="relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal-50 text-xs font-semibold text-teal-800">{{ index + 1 }}</div>
                  <div><div class="text-sm font-medium text-slate-800">{{ step.title }}</div><div class="mt-1 text-xs leading-5 text-slate-500">{{ step.description }}</div></div>
                </div>
              </div>
            </div>
          </section>
          <section class="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="flex items-center justify-between"><h2 class="font-semibold text-slate-900">最近活动</h2><span class="text-xs text-slate-400">演示记录</span></div>
            <div class="mt-4 divide-y divide-slate-100">
              <div v-for="event in events" :key="event.time" class="flex flex-wrap items-center justify-between gap-2 py-3 first:pt-0 last:pb-0">
                <div class="flex items-center gap-3"><span class="h-2 w-2 rounded-full bg-teal-500"></span><span class="text-sm text-slate-700">{{ event.text }}</span></div><span class="text-xs text-slate-400">{{ event.time }}</span>
              </div>
            </div>
          </section>
        </template>

        <template v-else-if="activeTab === 'missions'">
          <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 class="font-semibold text-slate-900">Mission 运行记录</h2>
            <div class="mt-4 overflow-x-auto">
              <table class="w-full min-w-[620px] text-left text-sm">
                <thead class="border-b border-slate-100 text-xs text-slate-400"><tr><th class="py-3 font-medium">Mission</th><th class="py-3 font-medium">负责人</th><th class="py-3 font-medium">当前阶段</th><th class="py-3 font-medium">状态</th></tr></thead>
                <tbody><tr v-for="m in missions" :key="m.id" class="border-b border-slate-50 last:border-0"><td class="py-4 font-medium text-slate-800">{{ m.name }}<div class="mt-1 text-xs font-normal text-slate-400">{{ m.id }}</div></td><td class="py-4 text-slate-600">{{ m.owner }}</td><td class="py-4 text-slate-600">{{ m.stage }}</td><td class="py-4"><span class="rounded-full px-2.5 py-1 text-[11px]" :class="m.tone">{{ m.status }}</span></td></tr></tbody>
              </table>
            </div>
          </div>
          <div class="mt-5 rounded-2xl border border-teal-100 bg-teal-50 p-5"><div class="text-sm font-semibold text-teal-900">安全边界</div><p class="mt-2 text-sm leading-6 text-teal-800">Mission 是唯一决策与调度 authority。演示页面只展示流程样例，不触发 Worker、Broker、Validator 或 Artifact Store 操作。</p></div>
        </template>

        <template v-else-if="activeTab === 'tasks'">
          <div class="grid gap-4 md:grid-cols-3">
            <div v-for="group in taskGroups" :key="group.title" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div class="flex items-center justify-between"><h2 class="text-sm font-semibold text-slate-800">{{ group.title }}</h2><span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{{ group.items.length }}</span></div>
              <div class="mt-4 space-y-3"><div v-for="task in group.items" :key="task.title" class="rounded-xl border border-slate-100 p-3"><div class="text-sm font-medium text-slate-700">{{ task.title }}</div><div class="mt-2 text-xs text-slate-400">{{ task.owner }} · {{ task.due }}</div></div></div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="grid gap-4 md:grid-cols-2">
            <div v-for="asset in knowledge" :key="asset.title" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div class="flex items-start justify-between gap-3"><div><div class="text-sm font-semibold text-slate-900">{{ asset.title }}</div><p class="mt-2 text-sm leading-6 text-slate-500">{{ asset.description }}</p></div><span class="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">{{ asset.state }}</span></div>
              <div class="mt-4 flex flex-wrap gap-2"><span v-for="tag in asset.tags" :key="tag" class="rounded-md bg-slate-100 px-2 py-1 text-[11px] text-slate-500">{{ tag }}</span></div>
              <div class="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-400">{{ asset.source }}</div>
            </div>
          </div>
        </template>

        <footer class="mt-8 border-t border-slate-200 pt-4 text-center text-xs text-slate-400">Evo Admin · Public Preview · 示例内容不代表真实运行状态</footer>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const activeTab = ref('overview')
const navItems = [
  { id: 'overview', label: '公司总览', icon: '⌂' },
  { id: 'missions', label: 'Mission 运行', icon: '◎' },
  { id: 'tasks', label: '任务中心', icon: '▤' },
  { id: 'knowledge', label: '知识与经验', icon: '◇' },
]
const currentTitle = computed(() => navItems.find(item => item.id === activeTab.value)?.label || '公司总览')
const metrics = [
  { label: '运行中的 Mission', value: '03', note: '2 个执行中' },
  { label: '待处理任务', value: '12', note: '4 个待验证' },
  { label: '可用 Worker', value: '08', note: '2 个忙碌' },
  { label: '已验证知识资产', value: '26', note: '+3 本周新增' },
]
const missions = [
  { id: 'MSN-2026-1108', name: '完善 Skill Replay 恢复核验', owner: '研发 Worker A', stage: '验证签名回执', status: '执行中', progress: 72, tone: 'bg-teal-50 text-teal-700' },
  { id: 'MSN-2026-1107', name: '整理失败案例并沉淀经验', owner: '学习 Worker', stage: '复盘与归档', status: '待审核', progress: 88, tone: 'bg-amber-50 text-amber-700' },
  { id: 'MSN-2026-1106', name: 'Admin UI 预览部署', owner: '前端 Worker', stage: '页面验收', status: '已完成', progress: 100, tone: 'bg-emerald-50 text-emerald-700' },
]
const pipeline = [
  { title: '目标与计划', description: '拆解目标、依赖关系与验收标准' },
  { title: 'Worker 执行', description: '按能力和并发安全规则分配成员' },
  { title: '测试与验证', description: '收集证据，独立验证执行结果' },
  { title: '复盘与沉淀', description: '分析偏差，生成 Experience / Skill' },
]
const events = [
  { text: 'Skill Replay 回执核验进入待验证阶段', time: '刚刚' },
  { text: 'Worker Android-A 完成任务并释放占用', time: '18 分钟前' },
  { text: '新增一条失败经验，等待验证', time: '今天 14:32' },
]
const taskGroups = [
  { title: '待处理', items: [{ title: '核验 Broker 缓存回执', owner: '研发 Worker A', due: '高优先级' }, { title: '补充异常路径回归测试', owner: '测试 Worker', due: '今天' }] },
  { title: '进行中', items: [{ title: '整理 Mission 恢复证据', owner: '学习 Worker', due: '执行中' }, { title: '检查 Admin UI 路由', owner: '前端 Worker', due: '执行中' }] },
  { title: '已完成', items: [{ title: '增加恢复状态分类', owner: '研发 Worker B', due: '已验收' }] },
]
const knowledge = [
  { title: 'Skill Replay 不确定结果处理', description: '远端已完成但响应丢失时，保留不确定状态；先查询原请求回执，不盲目重放。', state: '已验证', tags: ['Broker', '幂等', '恢复'], source: '来源：Mission MSN-2026-1108 · Validator 通过' },
  { title: 'Worker Claim 并发安全', description: '一个 Mission 节点占用一个 Worker；关联队列任务全部终态后才释放占用。', state: '已验证', tags: ['Worker', '并发', 'Lease'], source: '来源：并发回归测试 · Review 通过' },
  { title: '场景理解错题本', description: '识别空间时结合真实功能、结构与上下文，不只依赖名称标签。', state: '待复核', tags: ['视觉理解', '场景语义'], source: '来源：人工复盘记录' },
  { title: '知识归档完整性', description: '本地快照与远端归档分别校验摘要，失败时保留可重试状态。', state: '已验证', tags: ['Archive', 'SHA-256'], source: '来源：归档验证记录' },
]
</script>
