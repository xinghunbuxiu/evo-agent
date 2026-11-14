<template>
  <div class="space-y-5">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">Gitee 知识仓分片</h2>
          <p class="mt-1 text-sm text-slate-500">按知识场景分库，按容量扩展编号仓库。封存旧仓仍可查询，新档案转入后续分片。</p>
        </div>
        <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{{ inventory?.total ?? 0 }} repositories</span>
      </div>
      <div class="mt-4 grid gap-3 sm:grid-cols-3">
        <div class="rounded-xl bg-slate-50 px-4 py-3"><div class="text-2xl font-bold">{{ activeCount }}</div><div class="text-xs text-slate-500">可写仓库</div></div>
        <div class="rounded-xl bg-slate-50 px-4 py-3"><div class="text-2xl font-bold">{{ sealedCount }}</div><div class="text-xs text-slate-500">已封存</div></div>
        <div class="rounded-xl bg-slate-50 px-4 py-3"><div class="text-2xl font-bold">{{ provisioningCount }}</div><div class="text-xs text-slate-500">创建中</div></div>
      </div>
      <div class="mt-4 overflow-x-auto">
        <table class="w-full min-w-[720px] text-left text-sm">
          <thead class="border-b border-slate-200 text-xs text-slate-500">
            <tr><th class="px-3 py-2">仓库编号</th><th class="px-3 py-2">知识域</th><th class="px-3 py-2">状态</th><th class="px-3 py-2">容量使用</th><th class="px-3 py-2">文件数</th><th class="px-3 py-2">Gitee 仓库</th></tr>
          </thead>
          <tbody>
            <tr v-for="shard in inventory?.shards || []" :key="shard.repository_id" class="border-b border-slate-100">
              <td class="px-3 py-3 font-semibold text-slate-900">{{ shard.repository_id }}</td>
              <td class="px-3 py-3 text-slate-600">{{ shard.domain }}</td>
              <td class="px-3 py-3"><span class="rounded-full bg-slate-100 px-2 py-1 text-xs">{{ shard.status }}</span></td>
              <td class="px-3 py-3 text-slate-600">{{ shard.capacity_ratio == null ? "未测量" : (Math.round(shard.capacity_ratio * 1000) / 10) + "%" }}</td>
              <td class="px-3 py-3 text-slate-600">{{ shard.usage?.file_count ?? "-" }}</td>
              <td class="px-3 py-3">
                <a v-if="shard.url" :href="shard.url" target="_blank" rel="noopener noreferrer" class="text-sky-700 hover:underline">{{ shard.full_name }}</a>
                <span v-else class="text-slate-400">尚未创建</span>
              </td>
            </tr>
            <tr v-if="!inventory?.shards?.length"><td colspan="6" class="px-3 py-8 text-center text-slate-400">当前租户尚未建立编号知识仓</td></tr>
          </tbody>
        </table>
      </div>
      <p class="mt-3 text-xs text-slate-400">容量数据以最近一次测量为准；写入链路接入前不会自动触发扩容。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { KnowledgeShardInventory } from '../api/knowledge'

const props = defineProps<{ inventory: KnowledgeShardInventory | null }>()
const activeCount = computed(() => Object.values(props.inventory?.domains || {}).reduce((sum, item) => sum + item.active, 0))
const sealedCount = computed(() => Object.values(props.inventory?.domains || {}).reduce((sum, item) => sum + item.sealed, 0))
const provisioningCount = computed(() => Object.values(props.inventory?.domains || {}).reduce((sum, item) => sum + item.provisioning, 0))
</script>
