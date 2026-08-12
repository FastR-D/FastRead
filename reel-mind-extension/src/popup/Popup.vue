<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getConfiguredBackendUrl, importPaperFromUrl } from '~/logic/api'
import { DEFAULT_BACKEND_URL, settings, settingsReady, upsertTask } from '~/logic/storage'
import type { PaperImportCreated } from '~/logic/types'

const tabUrl = ref('')
const busy = ref(false)
const loading = ref(true)
const message = ref('')
const error = ref('')
const createdTask = ref<PaperImportCreated | null>(null)

const backendUrl = computed({
  get: () => settings.value.backendUrl || DEFAULT_BACKEND_URL,
  set: (value) => {
    settings.value.backendUrl = value.trim().replace(/\/$/, '') || DEFAULT_BACKEND_URL
  },
})

const canImportUrl = computed(() => /^https?:\/\//i.test(tabUrl.value))
const reportUrl = computed(() => {
  if (!createdTask.value?.task_id)
    return ''
  return `${getConfiguredBackendUrl()}/workspace?task_id=${encodeURIComponent(createdTask.value.task_id)}`
})

async function loadActiveTab() {
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true })
    tabUrl.value = tab?.url ?? ''
  }
  catch {
    tabUrl.value = ''
  }
}

async function importCurrentPaper() {
  if (!canImportUrl.value)
    return
  busy.value = true
  message.value = ''
  error.value = ''
  createdTask.value = null
  try {
    createdTask.value = await importPaperFromUrl(tabUrl.value)
    upsertTask({
      taskId: createdTask.value.task_id,
      input: tabUrl.value,
      inputMode: 'url',
      platform: 'paper',
      status: 'PENDING',
      message: '已提交论文导入',
      createdAt: Date.now(),
      updatedAt: Date.now(),
    })
    message.value = `已发送到 FastRead：${createdTask.value.task_id}`
  }
  catch (e) {
    error.value = (e as Error).message || '导入论文失败'
  }
  finally {
    busy.value = false
  }
}

async function openWorkspace() {
  await browser.tabs.create({ url: reportUrl.value || `${backendUrl.value}/workspace` })
}

onMounted(async () => {
  await settingsReady
  await loadActiveTab()
  loading.value = false
})
</script>

<template>
  <main class="w-[380px] bg-slate-50 text-slate-900">
    <header class="border-b border-slate-200 bg-white px-4 py-3">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <h1 class="text-base font-semibold leading-tight">
            FastRead 论文导入
          </h1>
          <p class="mt-1 text-xs text-slate-500">
            把当前页面的论文发送到 FastRead 阅读
          </p>
        </div>
        <span class="rounded-sm border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
          Import
        </span>
      </div>
    </header>

    <section class="space-y-3 p-4">
      <label class="block text-xs font-medium text-slate-600">
        后端地址
        <input
          v-model="backendUrl"
          class="mt-1 h-9 w-full rounded-sm border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-500"
          placeholder="http://127.0.0.1:8483"
        >
      </label>

      <div class="rounded-md border border-slate-200 bg-white p-3">
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm font-semibold">
            当前页面
          </div>
          <span
            class="rounded-sm px-1.5 py-0.5 text-[11px]"
            :class="canImportUrl ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
          >
            {{ canImportUrl ? '可导入' : '不可用' }}
          </span>
        </div>
        <div class="mt-1 truncate font-mono text-xs text-slate-500" :title="tabUrl">
          {{ loading ? '读取当前标签页中...' : (tabUrl || '未读取到当前标签页') }}
        </div>
        <button
          class="mt-3 flex h-10 w-full items-center justify-center rounded-sm bg-slate-950 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          :disabled="busy || !canImportUrl"
          @click="importCurrentPaper"
        >
          {{ busy ? '导入中...' : '发送这篇论文到 FastRead' }}
        </button>
        <p class="mt-2 text-[11px] leading-4 text-slate-400">
          支持论文首页（HTML）与直达 PDF 链接，导入后在 FastRead 中生成阅读报告。
        </p>
      </div>

      <div v-if="message" class="rounded-sm border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
        {{ message }}
      </div>
      <div v-if="error" class="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
        {{ error }}
      </div>

      <button
        class="h-8 w-full rounded-sm border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-100"
        @click="openWorkspace"
      >
        {{ createdTask ? '打开阅读报告' : '打开 FastRead 工作台' }}
      </button>
    </section>
  </main>
</template>
