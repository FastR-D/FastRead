import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Navigate, Routes, Route, useNavigate, useSearchParams } from 'react-router-dom'
import { useTaskPolling } from '@/hooks/useTaskPolling.ts'
import { useCheckBackend } from '@/hooks/useCheckBackend.ts'
import { systemCheck } from '@/services/system.ts'
import BackendInitDialog from '@/components/BackendInitDialog'
import StartupBanner from '@/components/SystemDiagnostic/StartupBanner'
import BackendHealthIndicator from '@/components/BackendHealth/BackendHealthIndicator'
import Index from '@/pages/Index.tsx'
import { HomePage } from './pages/HomePage/Home.tsx'
import { useTaskStore } from '@/store/taskStore'
import LibraryPage from '@/pages/LibraryPage'

// 非首屏页面使用 React.lazy 按需加载
const Onboarding = lazy(() => import('@/pages/Onboarding'))
const SearchPage = lazy(() => import('@/pages/SearchPage'))
const SettingPage = lazy(() => import('./pages/SettingPage/index.tsx'))
const ONBOARD_KEY = 'fastread-onboarded'

// 桌面端首启引导守卫：未完成 onboarding 时强制跳到 /onboarding
function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  // 仅在 Tauri 桌面端拦截；纯 web 端不打扰用户
  if (!isTauri) return <>{children}</>
  if (localStorage.getItem(ONBOARD_KEY) !== '1') {
    return <Navigate to="/onboarding" replace />
  }
  return <>{children}</>
}
const Model = lazy(() => import('@/pages/SettingPage/Model.tsx'))
const ProviderForm = lazy(() => import('@/components/Form/modelForm/Form.tsx'))
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'))

function TaskDeepLinkHandler() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const tasks = useTaskStore(state => state.tasks)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const taskId = searchParams.get('task_id')

  useEffect(() => {
    if (!taskId)
      return
    if (!tasks.some(task => task.id === taskId))
      return

    setCurrentTask(taskId)
    navigate('/workspace', { replace: true })
  }, [navigate, setCurrentTask, taskId, tasks])

  return null
}

function App() {
  useTaskPolling(3000) // 每 3 秒轮询一次
  const { loading, initialized } = useCheckBackend()
  const loadSavedTasks = useTaskStore(state => state.loadSavedTasks)

  // 在后端初始化完成后执行系统检查
  useEffect(() => {
    if (initialized) {
      systemCheck()
      loadSavedTasks()
    }
  }, [initialized, loadSavedTasks])

  // 如果后端还未初始化，显示初始化对话框
  if (!initialized) {
    return (
      <>
        <StartupBanner />
        <BackendInitDialog open={loading} />
      </>
    )
  }

  // 后端已初始化，渲染主应用
  return (
    <>
      <StartupBanner />
      <BackendHealthIndicator />
      <BrowserRouter>
        <TaskDeepLinkHandler />
        <Suspense fallback={<div className="flex h-screen items-center justify-center">加载中…</div>}>
          <Routes>
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/" element={<OnboardingGuard><Index /></OnboardingGuard>}>
              <Route index element={<LibraryPage />} />
              <Route path="search" element={<SearchPage />} />
              <Route path="workspace" element={<HomePage />} />
              <Route path="settings" element={<SettingPage />}>
                <Route index element={<Navigate to="model" replace />} />
                <Route path="model" element={<Model />}>
                  <Route path="new" element={<ProviderForm isCreate />} />
                  <Route path=":id" element={<ProviderForm />} />
                </Route>
                <Route path="*" element={<NotFoundPage />} />
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </>
  )
}

export default App
