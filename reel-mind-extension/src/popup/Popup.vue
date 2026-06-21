<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { createVerificationTask, getConfiguredBackendUrl, getDownloaderCookieStatus } from '~/logic/api'
import { syncCookieToBackend } from '~/logic/cookies'
import { DEFAULT_BACKEND_URL, settings, settingsReady, upsertTask } from '~/logic/storage'
import type { DownloaderCookieStatus, VerificationTaskCreated } from '~/logic/types'

const tabUrl = ref('')
const selectedText = ref('')
const busy = ref(false)
const cookieBusy = ref(false)
const loading = ref(true)
const message = ref('')
const error = ref('')
const status = ref<DownloaderCookieStatus | null>(null)
const createdTask = ref<VerificationTaskCreated | null>(null)

const backendUrl = computed({
  get: () => settings.value.backendUrl || DEFAULT_BACKEND_URL,
  set: (value) => {
    settings.value.backendUrl = value.trim().replace(/\/$/, '') || DEFAULT_BACKEND_URL
  },
})

const canVerifyUrl = computed(() => /^https?:\/\//i.test(tabUrl.value))
const manualText = computed(() => selectedText.value.trim())
const reportUrl = computed(() => {
  if (!createdTask.value?.task_id)
    return ''
  return `${getConfiguredBackendUrl()}/workspace?task_id=${encodeURIComponent(createdTask.value.task_id)}`
})

const cookieTone = computed(() => {
  if (status.value?.valid_looking)
    return 'ok'
  if (status.value?.configured)
    return 'warn'
  return 'idle'
})

const cookieText = computed(() => {
  if (status.value?.valid_looking) {
    if (status.value.warning_message)
      return `后端已有 ${status.value.cookie_count} 项 Cookie；${status.value.warning_message}`
    return `后端已有 ${status.value.cookie_count} 项 Cookie`
  }
  if (status.value?.configured)
    return `Cookie 不完整，缺少 ${status.value.missing_keys.join('、') || '关键字段'}`
  return '后端尚未保存抖音 Cookie'
})

const updatedAt = computed(() => {
  if (!status.value?.updated_at)
    return '从未同步'
  const date = new Date(status.value.updated_at)
  if (Number.isNaN(date.getTime()))
    return '时间未知'
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
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

async function refreshCookieStatus() {
  try {
    status.value = await getDownloaderCookieStatus('douyin')
  }
  catch {
    status.value = null
  }
}

async function startUrlVerification() {
  if (!canVerifyUrl.value)
    return
  busy.value = true
  message.value = ''
  error.value = ''
  createdTask.value = null
  try {
    createdTask.value = await createVerificationTask({ url: tabUrl.value })
    upsertTask({
      taskId: createdTask.value.task_id,
      input: tabUrl.value,
      inputMode: 'url',
      platform: 'verification',
      status: 'PENDING',
      message: '已提交联网核实',
      createdAt: Date.now(),
      updatedAt: Date.now(),
    })
    message.value = `已创建联网核实任务 ${createdTask.value.task_id}`
  }
  catch (e) {
    error.value = (e as Error).message || '创建联网核实任务失败'
  }
  finally {
    busy.value = false
  }
}

async function startTextVerification() {
  if (!manualText.value)
    return
  busy.value = true
  message.value = ''
  error.value = ''
  createdTask.value = null
  try {
    createdTask.value = await createVerificationTask({ text: manualText.value })
    upsertTask({
      taskId: createdTask.value.task_id,
      input: manualText.value,
      inputMode: 'text',
      platform: 'verification',
      status: 'PENDING',
      message: '已提交联网核实',
      createdAt: Date.now(),
      updatedAt: Date.now(),
    })
    message.value = `已创建联网核实任务 ${createdTask.value.task_id}`
  }
  catch (e) {
    error.value = (e as Error).message || '创建联网核实任务失败'
  }
  finally {
    busy.value = false
  }
}

async function syncCookie() {
  cookieBusy.value = true
  message.value = ''
  error.value = ''
  try {
    const res = await syncCookieToBackend('douyin')
    if (!res.ok) {
      error.value = res.error || '同步失败'
      return
    }
    message.value = `已捕捉并同步 ${res.count} 项抖音 Cookie`
    await refreshCookieStatus()
  }
  finally {
    cookieBusy.value = false
  }
}

async function openDouyin() {
  await browser.tabs.create({ url: 'https://www.douyin.com/jingxuan' })
}

async function openVerificationReport() {
  const url = reportUrl.value || `${backendUrl.value}/workspace`
  await browser.tabs.create({ url })
}

onMounted(async () => {
  await settingsReady
  await loadActiveTab()
  await refreshCookieStatus()
  loading.value = false
})
</script>

<template>
  <main class="w-[380px] bg-slate-50 text-slate-900">
    <header class="border-b border-slate-200 bg-white px-4 py-3">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <h1 class="text-base font-semibold leading-tight">
            ReelMind 联网核实
          </h1>
          <p class="mt-1 text-xs text-slate-500">
            用 ReelMind 联网核实此内容
          </p>
        </div>
        <span class="rounded-sm border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
          Verify
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
            :class="canVerifyUrl ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
          >
            {{ canVerifyUrl ? '可核实' : '不可用' }}
          </span>
        </div>
        <div class="mt-1 truncate font-mono text-xs text-slate-500" :title="tabUrl">
          {{ tabUrl || '未读取到当前标签页' }}
        </div>
        <button
          class="mt-3 flex h-10 w-full items-center justify-center rounded-sm bg-slate-950 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          :disabled="busy || !canVerifyUrl"
          @click="startUrlVerification"
        >
          {{ busy ? '创建中...' : '核实当前页面 URL' }}
        </button>
      </div>

      <div class="rounded-md border border-slate-200 bg-white p-3">
        <div class="text-sm font-semibold">
          文本核实
        </div>
        <textarea
          v-model="selectedText"
          class="mt-2 min-h-24 w-full resize-y rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm leading-5 outline-none focus:border-slate-500"
          placeholder="粘贴页面选中文本或任意待核实内容"
        />
        <button
          class="mt-2 flex h-9 w-full items-center justify-center rounded-sm border border-slate-300 bg-white text-xs font-semibold text-slate-800 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400"
          :disabled="busy || !manualText"
          @click="startTextVerification"
        >
          核实文本
        </button>
      </div>

      <div class="rounded-md border border-slate-200 bg-white p-3">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-sm font-semibold">
              抖音输入诊断
            </div>
            <div class="mt-1 text-xs leading-5 text-slate-500">
              {{ loading ? '读取状态中...' : cookieText }}
            </div>
          </div>
          <div class="shrink-0 text-right text-xs text-slate-400">
            {{ updatedAt }}
          </div>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-2">
          <button
            class="h-8 rounded-sm border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400"
            :disabled="cookieBusy"
            @click="syncCookie"
          >
            {{ cookieBusy ? '同步中...' : '同步 Cookie' }}
          </button>
          <button class="h-8 rounded-sm border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-100" @click="openDouyin">
            打开抖音精选
          </button>
        </div>
        <div class="mt-2 flex items-center gap-1.5 text-[11px]">
          <span
            class="h-1.5 w-1.5 rounded-full"
            :class="cookieTone === 'ok' ? 'bg-emerald-500' : cookieTone === 'warn' ? 'bg-amber-500' : 'bg-slate-300'"
          />
          <span class="text-slate-500">仅用于 Douyin 输入诊断，不作为核实判定依据。</span>
        </div>
      </div>

      <div v-if="message" class="rounded-sm border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
        {{ message }}
      </div>
      <div v-if="error" class="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
        {{ error }}
      </div>

      <button
        class="h-8 w-full rounded-sm border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-100"
        @click="openVerificationReport"
      >
        {{ createdTask ? '打开核实报告' : '打开 ReelMind 工作台' }}
      </button>
    </section>
  </main>
</template>
